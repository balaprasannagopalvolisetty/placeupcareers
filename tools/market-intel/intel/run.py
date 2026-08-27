#!/usr/bin/env python3
"""PlaceUp market-intelligence loop.

Runs unattended. Fires often, costs nothing when nothing is due, spends tokens only
on material that actually changed, and reschedules itself when Claude says stop.

  python -m intel.run watch      # fetch fast tier, detect change, extract facts
  python -m intel.run analyze    # comparative analysis of what changed
  python -m intel.run strategy   # positioning + marketing plan refresh
  python -m intel.run auto       # decide what is due and do it (what the timer calls)
  python -m intel.run status     # zero-token health report
"""
from __future__ import annotations
import json, os, pathlib, sys, time, datetime as dt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from intel import claude, fetch                              # noqa: E402
from intel.store import Store                                # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = pathlib.Path(os.environ.get("INTEL_STATE", ROOT / "state")).expanduser()
PROMPTS = ROOT / "prompts"


# ---------------------------------------------------------------- config
def _yaml(path: pathlib.Path) -> dict:
    try:
        import yaml
    except ImportError:                                      # pragma: no cover
        raise SystemExit(
            "PyYAML is required. Run install.sh, or: .venv/bin/pip install pyyaml")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise SystemExit(f"config error in {path.name}: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"config error in {path.name}: expected a mapping at the top level")
    return data


CFG = _yaml(ROOT / "config" / "settings.yml")
TGT = _yaml(ROOT / "config" / "targets.yml")
BUD = CFG["budget"]
RT = CFG["runtime"]


def repo_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("PLACEUP_REPO", ROOT.parents[1])).resolve()


def out_dir() -> pathlib.Path:
    d = repo_root() / RT["output_dir"]
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- budget
class Budget:
    def __init__(self, store: Store):
        self.store = store
        self.spent_run = 0
        self.spent_day = store.tokens_last_24h()

    def allows(self, need: int = 1500) -> bool:
        return (self.spent_run + need <= BUD["per_run_output_tokens"]
                and self.spent_day + need <= BUD["daily_output_tokens"])

    def charge(self, n: int) -> None:
        self.spent_run += n
        self.spent_day += n

    def overrun(self) -> bool:
        """A model can exceed the requested output cap. Detect it after the fact and
        hold, rather than discovering it in tomorrow's bill."""
        return (self.spent_run > BUD["per_run_output_tokens"]
                or self.spent_day > BUD["daily_output_tokens"])


# ---------------------------------------------------------------- helpers
def targets(tier: str) -> list[tuple[str, str, str, str]]:
    out = []
    for group in ("competitors", "signals"):
        for e in TGT.get(group, []) or []:
            if not isinstance(e, dict) or e.get("tier") != tier:
                continue
            for u in e.get("urls", []) or []:
                out.append((e["name"], u, e.get("kind", "html"), tier))
    return out


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


def _schedule(store: Store, when: float, why: str) -> None:
    store.set("resume_at", when)
    store.set("resume_reason", why)
    (STATE / "resume_at").write_text(str(int(when)))


def _due(store: Store, key: str, period_seconds: float) -> bool:
    return time.time() - float(store.get(key, 0)) >= period_seconds


# ---------------------------------------------------------------- passes
def watch(store: Store, bud: Budget) -> str:
    """Fetch, hash, and extract facts only from pages that actually changed."""
    changed, checked, errors = [], 0, 0
    for name, url, kind, tier in targets("fast"):
        checked += 1
        status, body = fetch.fetch(url, RT["http_timeout_seconds"], RT["user_agent"])
        text = fetch.to_text(body, kind)
        if text.startswith("__FETCH_ERROR__") or status >= 400 or len(text) < 200:
            errors += 1
            store.upsert_doc(url, name, tier, kind, text[:500], status or 599)
            store.add_fact(name, "fetch_status", f"{status or 'error'} at {url}", url)
            continue
        if store.upsert_doc(url, name, tier, kind, text, status):
            changed.append((name, url, text))
        prices = fetch.price_candidates(text)
        if prices:
            store.add_fact(name, "prices_seen", ", ".join(prices), url)

    extracted = 0
    for name, url, text in changed:
        if not bud.allows():
            _schedule(store, time.time() + 3600, "per-run budget reached during watch")
            break
        try:
            r = claude.ask(
                _prompt("extract").replace("{{ENTITY}}", name)
                                  .replace("{{URL}}", url)
                                  .replace("{{TEXT}}", text[:BUD["max_chars_per_doc"]]),
                model=CFG["models"]["extract"], max_output_tokens=700)
        except claude.UsageLimit as e:
            _schedule(store, e.resume_at, f"usage limit during watch: {e.detail[:200]}")
            raise
        bud.charge(r.output_tokens)
        for kind_, value in _parse_facts(r.text):
            store.add_fact(name, kind_, value, url)
        extracted += 1

    store.set("last_watch", time.time())
    return f"checked {checked}, changed {len(changed)}, extracted {extracted}, errors {errors}"


def _parse_facts(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        line = line.strip().lstrip("-* ").strip()
        if ":" in line and len(line) < 400:
            k, v = line.split(":", 1)
            k = k.strip().lower().replace(" ", "_")
            if k and v.strip() and len(k) < 40:
                out.append((k, v.strip()))
    return out[:20]


def analyze(store: Store, bud: Budget) -> str:
    since = float(store.get("last_analyze", 0)) or time.time() - 14 * 86400
    changed = store.changed_since(since)
    if not changed:
        store.set("last_analyze", time.time())
        return "nothing changed since last analysis - no tokens spent"
    if len(changed) == 1 and len(changed[0]["text"] or "") < 400:
        store.set("last_analyze", time.time())
        return "only trivial change - not worth a model call"

    facts = store.latest_facts()
    corpus = "\n".join(
        f"## {r['entity']} - {r['url']}\n{(r['text'] or '')[:BUD['max_chars_per_doc']]}"
        for r in changed[:BUD["max_docs_per_call"]])
    known = "\n".join(f"- {f['entity']} | {f['kind']}: {f['value']}" for f in facts)[:6000]

    if not bud.allows(3000):
        _schedule(store, time.time() + 3600, "budget reached before analysis")
        return "budget exhausted - analysis queued"

    try:
        r = claude.ask(
            _prompt("analyze").replace("{{PRODUCT}}", json.dumps(TGT["product"]))
                              .replace("{{KNOWN}}", known)
                              .replace("{{CHANGED}}", corpus),
            model=CFG["models"]["analyze"], max_output_tokens=2200)
    except claude.UsageLimit as e:
        _schedule(store, e.resume_at, f"usage limit during analyze: {e.detail[:200]}")
        raise
    bud.charge(r.output_tokens)

    path = out_dir() / f"{dt.date.today():%Y-%m-%d}-competitive-analysis.md"
    path.write_text(f"# Competitive analysis - {dt.date.today()}\n\n"
                    f"_Generated unattended. Sources: {len(changed)} changed documents._\n\n"
                    + r.text + "\n")
    (out_dir() / "LATEST-analysis.md").write_text(path.read_text())
    store.set("last_analyze", time.time())
    return f"analysed {len(changed)} changed docs -> {path.name}"


SUBSTANTIVE = {"positioning", "target_user", "pricing_tiers", "free_tier", "key_features",
               "visa_or_sponsorship", "countries", "data_sources", "proof", "new_since",
               "weakness_signal", "prices_seen"}


def strategy(store: Store, bud: Budget) -> str:
    facts = [f for f in store.latest_facts() if f["kind"] in SUBSTANTIVE]
    if len({f["entity"] for f in facts}) < 2:
        return ("not enough competitor facts yet - need at least 2 entities with real "
                "extracted content. Run watch until fetches succeed.")
    if not bud.allows(3500):
        _schedule(store, time.time() + 7200, "budget reached before strategy")
        return "budget exhausted - strategy queued"

    known = "\n".join(f"- {f['entity']} | {f['kind']}: {f['value']}" for f in facts)[:9000]
    latest = (out_dir() / "LATEST-analysis.md")
    prior = latest.read_text()[:4000] if latest.exists() else "none yet"

    try:
        r = claude.ask(
            _prompt("strategy").replace("{{PRODUCT}}", json.dumps(TGT["product"]))
                               .replace("{{FACTS}}", known)
                               .replace("{{PRIOR}}", prior),
            model=CFG["models"]["strategy"], max_output_tokens=3000)
    except claude.UsageLimit as e:
        _schedule(store, e.resume_at, f"usage limit during strategy: {e.detail[:200]}")
        raise
    bud.charge(r.output_tokens)

    path = out_dir() / f"{dt.date.today():%Y-%m-%d}-positioning-and-marketing.md"
    path.write_text(f"# Positioning and marketing plan - {dt.date.today()}\n\n" + r.text + "\n")
    (out_dir() / "LATEST-strategy.md").write_text(path.read_text())
    store.set("last_strategy", time.time())
    return f"strategy refreshed -> {path.name}"


# ---------------------------------------------------------------- driver
def auto(store: Store, bud: Budget) -> str:
    resume_at = float(store.get("resume_at", 0))
    if resume_at and time.time() < resume_at:
        mins = int((resume_at - time.time()) / 60)
        return f"holding until {dt.datetime.fromtimestamp(resume_at):%H:%M} ({mins}m) - {store.get('resume_reason','')[:80]}"
    store.set("resume_at", 0)

    if bud.spent_day >= BUD["daily_output_tokens"]:
        _schedule(store, time.time() + 3600, "daily token budget spent")
        return f"daily budget spent ({bud.spent_day} tokens) - holding 1h"

    done = []
    if _due(store, "last_watch", CFG["cadence"]["watch_hours"] * 3600):
        done.append("watch: " + watch(store, bud))
    if (not bud.overrun() and _due(store, "last_analyze", CFG["cadence"]["analyze_days"] * 86400)
            and bud.allows(3000)):
        done.append("analyze: " + analyze(store, bud))
    if (not bud.overrun() and _due(store, "last_strategy", CFG["cadence"]["strategy_days"] * 86400)
            and bud.allows(3500)):
        done.append("strategy: " + strategy(store, bud))
    if bud.overrun():
        _schedule(store, time.time() + 3600, "run exceeded token budget")
        done.append("budget overrun - holding 1h")
    return " | ".join(done) if done else "nothing due - 0 tokens"


def status(store: Store, _bud: Budget) -> str:
    def ago(k):
        t = float(store.get(k, 0))
        return "never" if not t else f"{(time.time()-t)/3600:.1f}h ago"
    resume = float(store.get("resume_at", 0))
    lines = [
        f"tokens last 24h : {store.tokens_last_24h()} / {BUD['daily_output_tokens']}",
        f"last watch      : {ago('last_watch')}",
        f"last analyze    : {ago('last_analyze')}",
        f"last strategy   : {ago('last_strategy')}",
        f"holding until   : {dt.datetime.fromtimestamp(resume):%Y-%m-%d %H:%M}" if resume > time.time() else "holding until   : not holding",
        f"tracked entities: {len({f['entity'] for f in store.latest_facts()})}",
        f"claude cli      : {'found' if claude.available() else 'MISSING'}",
        f"reports         : {out_dir()}",
    ]
    return "\n".join(lines)


def main() -> int:
    try:
        STATE.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[intel] cannot create state dir {STATE}: {e}\n"
              "        Set INTEL_STATE to a writable local path.", file=sys.stderr)
        return 1
    os.environ.setdefault("INTEL_BACKOFF_MINUTES", str(RT["default_backoff_minutes"]))
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "auto").lower()
    try:
        store = Store(STATE / "intel.db")
    except Exception as e:                                   # noqa: BLE001
        print(f"[intel] cannot open state database at {STATE}: {e}\n"
              "        SQLite needs a real local filesystem - a mounted network or\n"
              "        Windows share will fail here. Set INTEL_STATE to a local path,\n"
              "        e.g. INTEL_STATE=$HOME/.local/state/placeup-intel",
              file=sys.stderr)
        return 1
    bud = Budget(store)
    fn = {"watch": watch, "analyze": analyze, "strategy": strategy,
          "auto": auto, "status": status}.get(cmd)
    if not fn:
        print(__doc__)
        return 2
    rid = store.start_run(cmd)
    try:
        msg = fn(store, bud)
    except claude.UsageLimit as e:
        store.finish_run(rid, bud.spent_run, "limited", e.detail)
        print(f"[intel] usage limit - resuming at "
              f"{dt.datetime.fromtimestamp(e.resume_at):%Y-%m-%d %H:%M}", file=sys.stderr)
        return claude.EX_TEMPFAIL
    except Exception as e:                                   # noqa: BLE001
        store.finish_run(rid, bud.spent_run, "error", f"{type(e).__name__}: {e}")
        print(f"[intel] error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    store.finish_run(rid, bud.spent_run, "ok", msg)
    print(f"[intel] {cmd}: {msg} (+{bud.spent_run} output tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
