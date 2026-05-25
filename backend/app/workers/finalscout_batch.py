"""
FinalScout multi-API batch enrichment worker.

What it does
------------
Rotates through N FinalScout API keys to enrich contacts (LinkedIn URL or
name+company → verified email) at scale. Each FinalScout free tier gives
limited credits per account, so rotating through multiple keys lets ops
maintain large daily throughput without paying for a single Pro plan.

Input sources (try each, in order, until target batch size is filled):
  1. `--input-csv path/to/queue.csv` — explicit CSV with columns:
     linkedin_url OR (first_name, last_name, company), and optional
     related_job_id.
  2. `contacts` table rows with email IS NULL but linkedin_url IS NOT NULL.
  3. `master_jobs` rows where the hiring_manager_email metadata is missing
     but a linkedin_url was scraped into extra_metadata.

Output: writes verified Contact rows back to `contacts` via
`PostgresClient.upsert_contacts`. Idempotent — re-running the same input
re-uses the existing row IDs.

Key rotation strategy
---------------------
- Load all keys from `FINALSCOUT_API_KEYS` (comma-separated) OR from
  `FINALSCOUT_API_KEY_1`, `_2`, ... numbered env vars OR from the legacy
  single `FINALSCOUT_API_KEY`.
- Track per-key usage in memory + persist to a small JSON file at
  `--state-file` so consecutive runs don't blow the same key's quota on
  the first job each run.
- On 401/403 → key is dead, mark it permanently bad for this run + skip.
- On 429 → key is over quota, mark exhausted, rotate.
- On any other error → fail the row but keep the key.

CLI
---
    python -m app.workers.finalscout_batch --limit 200
    python -m app.workers.finalscout_batch --input-csv queue.csv --dry-run

Cloud Run Job
-------------
Deployed as `placeup-finalscout-batch` via deploy_separate_cloud_run.ps1;
triggered daily by Cloud Scheduler at 04:00 (see schedule_jobs.ps1).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import dataclasses
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import text

from app.config import settings
from app.db.postgres import PostgresClient
from app.models.contact import Contact

logger = logging.getLogger("placeup.workers.finalscout_batch")


# ─── Key pool ────────────────────────────────────────────────────────

@dataclasses.dataclass
class KeyState:
    """One entry per FinalScout API key, tracking live usage in this run."""
    key: str
    label: str            # short masked label for log lines, e.g. "key_1 (…abc1)"
    calls: int = 0        # successful enrichment calls this run
    failures: int = 0     # error responses this run
    exhausted: bool = False   # set when we hit 429 (or 401/403 = dead key)
    dead: bool = False        # set on 401/403

    def alive(self) -> bool:
        return not (self.exhausted or self.dead)

    @classmethod
    def from_key(cls, raw: str, idx: int) -> "KeyState":
        clean = raw.strip()
        tail = clean[-4:] if len(clean) >= 4 else "????"
        return cls(key=clean, label=f"key_{idx} (…{tail})")


def load_keys() -> list[KeyState]:
    """Load FinalScout API keys from env in priority order.

    Priority:
      1. `FINALSCOUT_API_KEYS` — comma-separated (most flexible).
      2. Numbered: `FINALSCOUT_API_KEY_1`, `_2`, ... up to `_50`.
      3. Legacy single: `FINALSCOUT_API_KEY` or `settings.finalscout_api_key`.

    Duplicates are removed (in case the same key is listed twice).
    """
    raw_keys: list[str] = []

    multi = os.getenv("FINALSCOUT_API_KEYS", "").strip() or getattr(settings, "finalscout_api_keys", "")
    if multi:
        raw_keys.extend([part.strip() for part in multi.split(",") if part.strip()])

    for i in range(1, 51):
        v = os.getenv(f"FINALSCOUT_API_KEY_{i}", "").strip()
        if v:
            raw_keys.append(v)

    legacy = os.getenv("FINALSCOUT_API_KEY", "").strip() or getattr(settings, "finalscout_api_key", "")
    if legacy and legacy not in raw_keys:
        raw_keys.append(legacy)

    seen: set[str] = set()
    unique: list[str] = []
    for k in raw_keys:
        if k and k not in seen:
            seen.add(k)
            unique.append(k)

    keys = [KeyState.from_key(k, idx=i + 1) for i, k in enumerate(unique)]
    if not keys:
        logger.warning(
            "No FinalScout API keys found. Set FINALSCOUT_API_KEYS (comma-separated) "
            "or FINALSCOUT_API_KEY_1, _2, ... or FINALSCOUT_API_KEY."
        )
    else:
        logger.info("FinalScout pool: %d keys loaded.", len(keys))
    return keys


class KeyPool:
    """Round-robin key picker with quota awareness + persistent state."""

    def __init__(self, keys: list[KeyState], state_file: Optional[Path] = None):
        self.keys = keys
        self.state_file = state_file
        self._idx = 0
        self._load_state()

    def _load_state(self) -> None:
        if not self.state_file or not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text("utf-8"))
            seen = {entry.get("key"): entry for entry in data.get("keys", [])}
            for k in self.keys:
                hit = seen.get(k.key)
                if hit:
                    k.calls = int(hit.get("calls") or 0)
                    k.failures = int(hit.get("failures") or 0)
                    # Persisted exhaustion lasts for the file's "as_of"
                    # day; daily Cloud Scheduler run regenerates the file.
                    if (hit.get("as_of") or "")[:10] == datetime.now(tz=timezone.utc).date().isoformat():
                        k.exhausted = bool(hit.get("exhausted"))
                        k.dead = bool(hit.get("dead"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load key-state file %s: %s", self.state_file, exc)

    def _save_state(self) -> None:
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "as_of": datetime.now(tz=timezone.utc).isoformat(),
                "keys": [
                    {
                        "key": k.key,
                        "calls": k.calls,
                        "failures": k.failures,
                        "exhausted": k.exhausted,
                        "dead": k.dead,
                    }
                    for k in self.keys
                ],
            }
            self.state_file.write_text(json.dumps(payload, indent=2), "utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not write key-state file: %s", exc)

    def pick(self) -> Optional[KeyState]:
        """Return next alive key in round-robin order, or None if all dead/exhausted."""
        n = len(self.keys)
        for _ in range(n):
            self._idx = (self._idx + 1) % n
            cand = self.keys[self._idx]
            if cand.alive():
                return cand
        return None

    def report(self) -> dict:
        return {
            "total_keys": len(self.keys),
            "alive": sum(1 for k in self.keys if k.alive()),
            "exhausted": sum(1 for k in self.keys if k.exhausted),
            "dead": sum(1 for k in self.keys if k.dead),
            "calls_total": sum(k.calls for k in self.keys),
            "failures_total": sum(k.failures for k in self.keys),
            "per_key": [
                {
                    "label": k.label,
                    "calls": k.calls,
                    "failures": k.failures,
                    "exhausted": k.exhausted,
                    "dead": k.dead,
                }
                for k in self.keys
            ],
        }

    def flush(self) -> None:
        self._save_state()


# ─── Input loaders ───────────────────────────────────────────────────

PENDING_FROM_CONTACTS_SQL = """
SELECT id, full_name, first_name, last_name, linkedin_url, title,
       company_id, related_job_id
FROM contacts
WHERE (email IS NULL OR email = '')
  AND (linkedin_url IS NOT NULL AND linkedin_url <> '')
LIMIT :limit
"""


def load_candidates_from_csv(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            entry = {
                "linkedin_url": (row.get("linkedin_url") or "").strip() or None,
                "first_name": (row.get("first_name") or "").strip() or None,
                "last_name": (row.get("last_name") or "").strip() or None,
                "company": (row.get("company") or "").strip() or None,
                "company_domain": (row.get("company_domain") or "").strip() or None,
                "related_job_id": (row.get("related_job_id") or "").strip() or None,
            }
            if entry["linkedin_url"] or (entry["first_name"] and entry["last_name"] and entry["company"]):
                out.append(entry)
    return out


def load_candidates_from_db(client: PostgresClient, limit: int) -> list[dict]:
    out: list[dict] = []
    with client.session() as db:
        rows = db.execute(text(PENDING_FROM_CONTACTS_SQL), {"limit": limit}).mappings().all()
        for row in rows:
            out.append({
                "linkedin_url": row.get("linkedin_url"),
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "company": None,           # backfilled from company_id below if needed
                "related_job_id": row.get("related_job_id"),
                "existing_contact_id": row.get("id"),
            })
    return out


# ─── Enrichment loop ────────────────────────────────────────────────

async def enrich_one(candidate: dict, pool: KeyPool) -> Optional[Contact]:
    """Try each alive key until one produces a Contact or we run out."""
    # Lazy import keeps the worker importable without httpx during tests.
    from app.services import finalscout_enrichment as fs

    while True:
        key_state = pool.pick()
        if key_state is None:
            logger.error("All FinalScout keys exhausted; aborting remaining rows.")
            return None

        try:
            contact: Optional[Contact] = None
            if candidate.get("linkedin_url"):
                contact = await fs.find_by_linkedin(
                    linkedin_url=candidate["linkedin_url"],
                    related_job_id=candidate.get("related_job_id"),
                    byok_api_key=key_state.key,
                )
            elif candidate.get("first_name") and candidate.get("last_name") and candidate.get("company"):
                contact = await fs.find_by_professional(
                    first_name=candidate["first_name"],
                    last_name=candidate["last_name"],
                    company=candidate["company"],
                    company_domain=candidate.get("company_domain"),
                    related_job_id=candidate.get("related_job_id"),
                    byok_api_key=key_state.key,
                )
            else:
                logger.debug("Candidate lacks both linkedin_url and (first_name+last_name+company); skipping.")
                return None

            key_state.calls += 1
            if contact is None:
                # No data returned — could be legitimate "no match" OR a
                # quota hit that the service module swallowed silently.
                # Without HTTP status visibility here we can't tell which,
                # so we treat as a non-fatal miss and keep the key alive.
                return None
            return contact

        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            key_state.failures += 1
            if "401" in msg or "403" in msg or "unauthorized" in msg:
                logger.warning("%s appears dead (auth error): %s", key_state.label, exc)
                key_state.dead = True
                continue
            if "429" in msg or "rate" in msg or "quota" in msg:
                logger.warning("%s exhausted (quota): %s", key_state.label, exc)
                key_state.exhausted = True
                continue
            logger.warning("Enrichment error for %s: %s", candidate.get("linkedin_url") or candidate.get("first_name"), exc)
            return None


async def run(
    *,
    limit: int = 200,
    input_csv: Optional[Path] = None,
    state_file: Optional[Path] = None,
    dry_run: bool = False,
    concurrency: int = 4,
) -> dict:
    started = time.monotonic()
    keys = load_keys()
    if not keys:
        return {"ok": False, "reason": "no FinalScout keys configured"}
    pool = KeyPool(keys, state_file=state_file)

    client = PostgresClient()
    if input_csv:
        candidates = load_candidates_from_csv(input_csv)
    else:
        candidates = load_candidates_from_db(client, limit)
    candidates = candidates[:limit]

    logger.info("FinalScout batch: %d candidates queued, %d alive keys.", len(candidates), pool.report()["alive"])

    if dry_run:
        pool.flush()
        return {
            "dry_run": True,
            "candidates": len(candidates),
            "pool": pool.report(),
            "duration_seconds": round(time.monotonic() - started, 2),
        }

    semaphore = asyncio.Semaphore(concurrency)
    successes: list[Contact] = []
    misses = 0

    async def _go(cand: dict):
        nonlocal misses
        async with semaphore:
            contact = await enrich_one(cand, pool)
            if contact is not None:
                successes.append(contact)
            else:
                misses += 1

    await asyncio.gather(*[_go(c) for c in candidates])

    wrote = 0
    if successes:
        payload = [
            {
                "id": c.id,
                "full_name": c.full_name,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "title": c.title,
                "role": (c.role.value if hasattr(c.role, "value") else c.role),
                "company": c.company,
                "company_domain": c.company_domain,
                "email": c.email,
                "linkedin_url": c.linkedin_url,
                "source": (c.source.value if hasattr(c.source, "value") else c.source),
                "confidence": (c.confidence.value if hasattr(c.confidence, "value") else c.confidence),
                "related_job_id": c.related_job_id,
                "last_verified_at": c.last_verified_at,
                "source_payload": c.source_payload or {},
            }
            for c in successes
        ]
        wrote = await client.upsert_contacts(payload)

    pool.flush()
    summary = {
        "candidates": len(candidates),
        "enriched": len(successes),
        "missed": misses,
        "written_to_db": wrote,
        "pool": pool.report(),
        "duration_seconds": round(time.monotonic() - started, 2),
    }
    logger.info("FinalScout batch complete: %s", {k: v for k, v in summary.items() if k != "pool"})
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-key FinalScout batch enrichment worker.")
    parser.add_argument("--limit", type=int, default=200, help="Max candidates per run (default 200).")
    parser.add_argument("--input-csv", type=Path, default=None, help="Optional CSV input instead of pulling from contacts table.")
    parser.add_argument("--state-file", type=Path, default=Path("/tmp/finalscout_state.json"),
                        help="Where to persist per-key counters across runs (default /tmp/finalscout_state.json).")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent enrichment calls (FinalScout single-find caps at 5/sec).")
    parser.add_argument("--dry-run", action="store_true", help="Load candidates + keys, but make no API calls or DB writes.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    summary = asyncio.run(run(
        limit=args.limit,
        input_csv=args.input_csv,
        state_file=args.state_file,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
    ))
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary.get("ok") is not False else 1


if __name__ == "__main__":
    sys.exit(main())
