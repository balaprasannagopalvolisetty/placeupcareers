"""Deterministic fetching and text extraction. Costs zero model tokens by design."""
from __future__ import annotations
import re, html, json, urllib.request, urllib.error

_TAG = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.S | re.I)
_ANY = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


def fetch(url: str, timeout: int, ua: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(2_000_000)
            enc = r.headers.get_content_charset() or "utf-8"
            return r.status, raw.decode(enc, "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:                                   # noqa: BLE001 - reported, not swallowed
        return 0, f"__FETCH_ERROR__ {type(e).__name__}: {e}"


def to_text(body: str, kind: str = "html") -> str:
    """Strip to readable text. Deliberately crude and dependency-free - the model
    never sees markup, so precision here is a pure token saving."""
    if body.startswith("__FETCH_ERROR__"):
        return body
    if kind == "json":
        try:
            data = json.loads(body)
            return _reddit_titles(data) if "children" in json.dumps(data)[:200] else json.dumps(data)[:20000]
        except Exception:                                    # noqa: BLE001
            return body[:20000]
    t = _TAG.sub(" ", body)
    t = _ANY.sub("\n", t)
    t = html.unescape(t)
    t = _WS.sub(" ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    t = _NL.sub("\n\n", t)
    return t.strip()


def _reddit_titles(data: dict) -> str:
    out = []
    for c in data.get("data", {}).get("children", []):
        d = c.get("data", {})
        out.append(f"[{d.get('score', 0)}] {d.get('title', '')} :: {(d.get('selftext') or '')[:300]}")
    return "\n".join(out)


def price_candidates(text: str) -> list[str]:
    """Cheap deterministic pricing extraction. Catches most changes with no model call."""
    hits = re.findall(r"(?:US)?\$\s?\d{1,4}(?:\.\d{2})?\s?(?:/\s?(?:mo|month|yr|year))?", text)
    seen, out = set(), []
    for h in hits:
        h = _WS.sub("", h)
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:25]
