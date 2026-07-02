"""Sweep ALL known sponsor companies and harvest their full job boards.

Coverage strategy: the visa_sponsors table holds the OFFICIAL government
sponsor registries for every PlaceUp target country (UK Home Office register,
NL IND recognized sponsors, IE permits, ... ) and h1b_sponsors holds every US
H-1B petitioner. That is the complete universe of employers who can actually
sponsor our users. This worker walks that universe company by company:

    sponsor company -> probe public ATS boards -> ingest EVERY open position
    (first-party description + direct apply link) -> sync master_jobs.

Progress is checkpointed in board_sweep_state (created on first run), so each
scheduled execution continues where the last one stopped and re-visits
companies after RESWEEP_DAYS. Run it forever on a schedule and coverage
converges to "all sponsor companies with a public ATS board".

Usage:
    python -m app.workers.board_discovery_sweep --limit 600 --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import time
from typing import Any

from sqlalchemy import text

from app.db.postgres import PostgresClient
from app.services.company_career_resolver import get_board_postings

logger = logging.getLogger("placeup.workers.board_discovery_sweep")

RESWEEP_DAYS = 30
UPSERT_BATCH = 2000
MASTER_REBUILD_EVERY_LOADED = 500
MIN_ALPHA_CHARS = 3

_LEGAL_ENTITY_NOISE_RE = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|company|co|plc|gmbh|llp|lp)\b\.?",
    re.I,
)

STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS board_sweep_state (
    company_key text PRIMARY KEY,
    employer_name text NOT NULL,
    country text,
    swept_at timestamptz NOT NULL DEFAULT now(),
    postings_found integer NOT NULL DEFAULT 0
)
"""

CANDIDATE_SQL = """
WITH sponsors AS (
    SELECT employer_name, country, 0 AS weight, lower(trim(employer_name)) AS company_key
    FROM visa_sponsors
    WHERE coalesce(employer_name, '') <> ''
    UNION
    SELECT employer_name, 'US' AS country, total_petitions AS weight, lower(trim(employer_name)) AS company_key
    FROM h1b_sponsors
    WHERE coalesce(employer_name, '') <> '' AND total_petitions >= 1
),
pending AS (
    SELECT DISTINCT ON (s.company_key) s.employer_name, s.country, s.weight, s.company_key
    FROM sponsors s
    LEFT JOIN board_sweep_state st ON st.company_key = s.company_key
    WHERE st.company_key IS NULL
       OR st.swept_at < now() - make_interval(days => :resweep_days)
    ORDER BY s.company_key, s.weight DESC
)
SELECT employer_name, country, company_key
FROM pending
-- Real employers first: numbered shell companies ("1295416 Alberta Ltd")
-- almost never run ATS boards, and alphabetical order front-loaded
-- thousands of them (first sweep batch: 600 checked, 0 boards). High-volume
-- H-1B petitioners lead, then everything else shuffled.
ORDER BY (employer_name ~ '^[0-9]'), weight DESC, random()
LIMIT :limit
"""

MARK_SQL = """
INSERT INTO board_sweep_state (company_key, employer_name, country, swept_at, postings_found)
VALUES (:company_key, :employer_name, :country, now(), :postings_found)
ON CONFLICT (company_key) DO UPDATE
SET swept_at = now(), postings_found = EXCLUDED.postings_found
"""


def _candidates(limit: int) -> list[dict[str, Any]]:
    client = PostgresClient()
    with client.session() as db:
        db.execute(text(STATE_TABLE_SQL))
        rows = db.execute(text(CANDIDATE_SQL), {"limit": limit, "resweep_days": RESWEEP_DAYS}).mappings().all()
    return [dict(r) for r in rows]


def _is_credible_company_name(name: str) -> bool:
    """Reject sponsor rows that are poor ATS/search targets."""
    clean = _LEGAL_ENTITY_NOISE_RE.sub(" ", name or "")
    alpha = re.sub(r"[^A-Za-z]", "", clean)
    digits = re.sub(r"\D", "", clean)
    compact = re.sub(r"[^A-Za-z0-9]", "", clean)
    if len(alpha) < MIN_ALPHA_CHARS:
        return False
    if digits and len(digits) >= len(alpha):
        return False
    if compact.isdigit():
        return False
    return True


async def run(limit: int, concurrency: int, dry_run: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    companies = _candidates(limit)
    logger.info("Board sweep: %s sponsor companies in this batch", len(companies))

    semaphore = asyncio.Semaphore(concurrency)
    write_lock = asyncio.Lock()
    client = PostgresClient()
    seen_ids: set[str] = set()
    boards_found = 0
    skipped_noisy_names = 0
    loaded = 0
    rebuilt = 0
    last_rebuild_loaded = 0

    async def persist_company_result(state_row: dict[str, Any], payloads: list[dict]) -> None:
        """Checkpoint one company immediately so timeout/interruption does not lose work."""
        nonlocal loaded, rebuilt, last_rebuild_loaded
        if dry_run:
            return
        async with write_lock:
            company_loaded = 0
            if payloads:
                for i in range(0, len(payloads), UPSERT_BATCH):
                    company_loaded += await client.upsert_jobs_batch(payloads[i:i + UPSERT_BATCH])
                loaded += company_loaded
            with client.session() as db:
                db.execute(text(MARK_SQL), state_row)
            if loaded and loaded - last_rebuild_loaded >= MASTER_REBUILD_EVERY_LOADED:
                try:
                    from app.etl.master_jobs import rebuild_master_jobs
                    rebuilt = rebuild_master_jobs(client)
                    last_rebuild_loaded = loaded
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Master rebuild during board sweep failed: %s", exc)
            if company_loaded:
                logger.info(
                    "Board sweep checkpointed %s postings for %r (loaded_total=%s)",
                    company_loaded,
                    state_row.get("employer_name"),
                    loaded,
                )

    async def probe(company_row: dict[str, Any]) -> None:
        nonlocal boards_found, skipped_noisy_names
        async with semaphore:
            name = str(company_row.get("employer_name") or "").strip()
            if not _is_credible_company_name(name):
                skipped_noisy_names += 1
                state_row = {
                    "company_key": company_row.get("company_key"),
                    "employer_name": name[:380],
                    "country": company_row.get("country"),
                    "postings_found": 0,
                }
                await persist_company_result(state_row, [])
                logger.debug("Board sweep skipped noisy sponsor name: %r", name)
                return
            postings = []
            # ALWAYS also web-search the company's official careers portal —
            # even when an ATS board was found. Boards are often partial (one
            # division / one region) while the company's own portal (Workday,
            # Eightfold like apply.hp.com, embedded ATS) carries everything.
            # Duplicates are deduped by job id here and by canonical key in
            # the loader, so the merge is safe.
            try:
                from app.services.careers_page_ingest import collect_postings_for_company
                meta, extra = await collect_postings_for_company(name)
                if extra:
                    postings.extend(extra)
                    logger.info(
                        "Board sweep discovered %s postings for %r via %s/%s",
                        len(extra),
                        name,
                        (meta or {}).get("ats"),
                        (meta or {}).get("token"),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Search-based careers discovery failed for %r: %s", name, exc)
            # ALSO probe the standard ATS APIs every time (not only when the
            # search missed): companies often run a partial board on one
            # platform and a fuller portal elsewhere. The pid/seen_ids and
            # loader canonical-key dedupe make the merge safe.
            try:
                board_postings = await get_board_postings(name)
                if board_postings:
                    postings.extend(board_postings)
            except Exception as exc:  # noqa: BLE001
                logger.debug("ATS board probe failed for %r: %s", name, exc)
            count = 0
            company_payloads: list[dict] = []
            for posting in postings:
                pid = str(getattr(posting, "id", "") or "")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                try:
                    company_payloads.append(posting.model_dump(mode="python"))
                    count += 1
                except Exception:  # noqa: BLE001
                    continue
            if count:
                boards_found += 1
            state_row = {
                "company_key": company_row.get("company_key"),
                "employer_name": name[:380],
                "country": company_row.get("country"),
                "postings_found": count,
            }
            await persist_company_result(state_row, company_payloads)

    await asyncio.gather(*(probe(row) for row in companies))

    if loaded and not dry_run:
        try:
            from app.etl.master_jobs import rebuild_master_jobs
            rebuilt = rebuild_master_jobs(client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Master rebuild after board sweep failed: %s", exc)

    summary = {
        "companies_checked": len(companies),
        "skipped_noisy_names": skipped_noisy_names,
        "boards_with_postings": boards_found,
        "postings_loaded": loaded,
        "master_rows_synced": rebuilt,
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    logger.info("Board discovery sweep finished: %s", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=600)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    summary = asyncio.run(run(args.limit, args.concurrency, dry_run=args.dry_run))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
