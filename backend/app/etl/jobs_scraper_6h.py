"""Production-sized 6-hour job scraper entrypoint for the existing Cloud Run Job.

The Cloud Run job intentionally keeps the existing production name
`placeup-job-scraper-6h`; do not create a duplicate 8-hour scraper.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time

from sqlalchemy import text

from app.db.postgres import PostgresClient
from app.etl.jobs_scraper import run
from app.etl.api_sources.runner import run_api_connectors_to_postgres
from app.etl.purge_jobs_except_today import purge_except_day, purge_outside_window
from app.config import settings
from app.job_taxonomy import (
    all_balanced_taxonomy_scrape_search_terms,
    all_linkedin_style_role_names,
    all_role_backfill_search_terms,
    all_role_names,
    categorize,
)
from app.services.global_visa_rules import COUNTRY_RULES, TARGET_COUNTRIES, resolve_country
from app.utils.terminal_table import render_table

logger = logging.getLogger(__name__)

DIRECT_ATS_CONNECTOR_SOURCES = (
    "greenhouse~lever~ashby~smartrecruiters~career_site_feed~remoteok~remotive~jobicy"
)

# Public/API passes must cover every taxonomy role, not just USAJobs. Keep the
# public-source set env-tunable because provider availability changes.
FREE_OPEN_PUBLIC_SOURCES = os.getenv(
    "SCRAPER_PUBLIC_SOURCES",
    "linkedin~indeed~glassdoor~ziprecruiter~google~usajobs~dice",
)
FREE_OPEN_BOARD_SOURCES = (
    "h1b_sponsor~tier1_ats~remoteok~remotive~arbeitnow~jobicy~weworkremotely~"
    "jobtech~eures~uk_findajob~nhs_jobs~jobbank_ca~ba_jobsuche~france_travail~"
    "mycareersfuture~tyomarkkinatori~nav_arbeidsplassen~monster~jooble~"
    "scrapling_discovery"
)
try:
    BATCH_SIZE = max(2, int(os.getenv("SCRAPER_ROLE_BATCH_SIZE", "8")))
except ValueError:
    BATCH_SIZE = 20
try:
    CANONICAL_ROLE_BATCH_SIZE = max(2, int(os.getenv("SCRAPER_CANONICAL_ROLE_BATCH_SIZE", "5")))
except ValueError:
    CANONICAL_ROLE_BATCH_SIZE = 5
try:
    PUBLIC_BATCH_CONCURRENCY = max(0, int(os.getenv("SCRAPER_PUBLIC_BATCH_CONCURRENCY", "2")))
except ValueError:
    PUBLIC_BATCH_CONCURRENCY = 0
PURGE_EXCEPT_TODAY = os.getenv("SCRAPER_PURGE_EXCEPT_TODAY", "false").strip().lower() not in {"0", "false", "no", "off"}
PURGE_TIMEZONE = os.getenv("SCRAPER_PURGE_TIMEZONE", "America/Chicago").strip() or "America/Chicago"
# Rolling retention is OPT-IN. Default 0 == never delete anything (matches the
# previous safe behavior where SCRAPER_PURGE_EXCEPT_TODAY=false did no purge).
# Set SCRAPER_RETENTION_DAYS=N (>0) to prune only postings older than N days —
# a thin/failed run still can't wipe the board because recent rows are kept.
# The stale-jobs sweeper (separate daily job) already marks >30d as inactive.
try:
    RETENTION_DAYS = max(0, int(os.getenv("SCRAPER_RETENTION_DAYS", "0")))
except ValueError:
    RETENTION_DAYS = 0
ADVISORY_LOCK_KEY = 6412226682826
try:
    COVERAGE_AUDIT_FLOOR = max(0, int(os.getenv("SCRAPER_ROLE_COUNTRY_AUDIT_FLOOR", "70")))
except ValueError:
    COVERAGE_AUDIT_FLOOR = 70
try:
    # Zero disables the application-level deadline. Cloud Run still enforces
    # its platform maximum, while the advisory lock below prevents overlap.
    RUN_BUDGET_SECONDS = max(0, int(os.getenv("SCRAPER_RUN_BUDGET_SECONDS", "0")))
except ValueError:
    RUN_BUDGET_SECONDS = 0
try:
    PUBLIC_MAX_BATCHES_PER_RUN = max(0, int(os.getenv("SCRAPER_PUBLIC_MAX_BATCHES_PER_RUN", "0")))
except ValueError:
    PUBLIC_MAX_BATCHES_PER_RUN = 0
try:
    PUBLIC_BATCH_OFFSET = max(0, int(os.getenv("SCRAPER_PUBLIC_BATCH_OFFSET", "0")))
except ValueError:
    PUBLIC_BATCH_OFFSET = 0
COVERAGE_FLOOR_ENABLED = os.getenv("SCRAPER_COVERAGE_FLOOR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _encoded_terms(terms: list[str]) -> str:
    return "~".join(term.replace(" ", "_") for term in terms)


def _target_locations() -> str:
    locations: list[str] = []
    for country_code in sorted(TARGET_COUNTRIES):
        rule = COUNTRY_RULES.get(country_code)
        name = rule.name if rule else country_code
        locations.append(name.replace(" ", "_"))
    return "~".join(locations)


def _configured_public_sources() -> str:
    sources = [source for source in FREE_OPEN_PUBLIC_SOURCES.strip("~ ").split("~") if source]
    if "usajobs" in sources and (not settings.usajobs_api_key.strip() or not settings.usajobs_email.strip()):
        logger.warning("USAJobs public batches disabled because USAJOBS_API_KEY/USAJOBS_EMAIL are not configured.")
        sources = [source for source in sources if source != "usajobs"]
    return "~".join(sources)


def _merge_sources(*groups: str) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for source in group.strip("~ ").split("~"):
            source = source.strip()
            if source and source not in seen:
                seen.add(source)
                merged.append(source)
    return "~".join(merged)


def _base_args(**overrides) -> argparse.Namespace:
    values = {
        "locations": _target_locations(),
        "max_per_source": 60,
        "max_per_sponsor": 400,
        "h1b_sponsor_concurrency": 10,
        "jobspy_hours_old": 8,
        "jobspy_page_size": 50,
        "jobspy_max_pages": 25,
        "tiers": "T1~T2",
        "schedule_type": "6h",
        "dry_run": False,
        "skip_master_sync": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


async def _run_batched() -> int:
    started_at = time.monotonic()

    def budget_remaining() -> float:
        if RUN_BUDGET_SECONDS == 0:
            return float("inf")
        return RUN_BUDGET_SECONDS - (time.monotonic() - started_at)

    def budget_available(min_remaining: int = 900) -> bool:
        return budget_remaining() > min_remaining

    roles = all_role_names()
    linkedin_style_roles = all_linkedin_style_role_names()
    terms = all_balanced_taxonomy_scrape_search_terms()
    countries = list(sorted(TARGET_COUNTRIES))
    country_locations = _target_locations()
    role_country_pairs = len(roles) * len(countries)
    public_role_batches = [roles[i:i + BATCH_SIZE] for i in range(0, len(roles), BATCH_SIZE)]
    if public_role_batches and PUBLIC_BATCH_OFFSET:
        offset = PUBLIC_BATCH_OFFSET % len(public_role_batches)
        public_role_batches = [*public_role_batches[offset:], *public_role_batches[:offset]]
    if PUBLIC_MAX_BATCHES_PER_RUN:
        public_role_batches = public_role_batches[:PUBLIC_MAX_BATCHES_PER_RUN]
    failures = 0

    logger.info(
        "6h role-country coverage plan: %s canonical roles x %s countries = %s role-country pairs; countries=%s",
        len(roles),
        len(countries),
        role_country_pairs,
        ",".join(countries),
    )

    logger.info("6h scraper running direct H1B/ATS board pass")
    try:
        api_connector_count = await run_api_connectors_to_postgres(
            queries=terms,
            countries=countries,
            sources=os.getenv("API_CONNECTOR_SOURCES", DIRECT_ATS_CONNECTOR_SOURCES),
        )
        logger.info("6h official API/ATS connectors loaded %s jobs", api_connector_count)
    except Exception as exc:
        failures += 1
        logger.warning("6h official API/ATS connector pass failed; continuing with board/public sources: %s", exc)
    board_code = await run(_base_args(
        queries=_encoded_terms(linkedin_style_roles),
        locations=country_locations,
        max_per_source=200,
        sources=FREE_OPEN_BOARD_SOURCES,
        schedule_type="6h-boards",
    ))
    if board_code:
        failures += 1
        logger.warning("6h scraper board pass failed with code %s", board_code)

    public_sources = _configured_public_sources()
    if not public_sources:
        logger.info("6h scraper public source pass disabled")
        return 1 if failures >= 2 else 0

    async def _run_public_batch(index: int, total: int, batch: list[str], *, phase: str, batch_size: int) -> int:
        logger.info(
            "6h scraper %s batch %s/%s publishing %s terms across %s countries (%s role-country attempts)",
            phase,
            index,
            total,
            len(batch),
            len(countries),
            len(batch) * len(countries),
        )
        code = await run(_base_args(
            queries=_encoded_terms(batch),
            locations=country_locations,
            sources=public_sources,
            schedule_type=f"6h-public-{phase}-{index:02d}",
            max_per_source=batch_size,
            skip_master_sync=True,
        ))
        if code:
            logger.warning("6h scraper public %s batch %s/%s failed with code %s", phase, index, total, code)
        return code

    logger.info(
        "6h scraper launching %s budgeted public role batches for %s current roles / %s canonical search names / %s search terms with batch concurrency %s (run budget remaining %.0fs)",
        len(public_role_batches),
        len(roles),
        len(linkedin_style_roles),
        len(terms),
        PUBLIC_BATCH_CONCURRENCY or 1,
        budget_remaining(),
    )
    batch_concurrency = max(1, PUBLIC_BATCH_CONCURRENCY or 1)
    batch_semaphore = asyncio.Semaphore(batch_concurrency)

    async def _run_public_batch_guarded(index: int, batch: list[str]) -> int:
        async with batch_semaphore:
            if not budget_available(min_remaining=900):
                logger.warning(
                    "6h scraper skipping public batch %s/%s because run budget remaining is %.0fs",
                    index,
                    len(public_role_batches),
                    budget_remaining(),
                )
                return 0
            return await _run_public_batch(
                index,
                len(public_role_batches),
                batch,
                phase="roles",
                batch_size=60,
            )

    public_results = await asyncio.gather(*[
        _run_public_batch_guarded(index, batch)
        for index, batch in enumerate(public_role_batches, start=1)
    ])
    failures += sum(1 for code in public_results if code)

    if public_results:
        try:
            client = PostgresClient()
            with client.session() as db:
                from app.etl.master_jobs import rebuild_master_jobs
                rebuild_master_jobs(db=db)
                db.commit()
            logger.info("6h scraper master jobs sync complete after public role batches")
        except Exception as exc:
            failures += 1
            logger.warning("6h scraper master jobs sync after public role batches failed: %s", exc)

    if COVERAGE_FLOOR_ENABLED and budget_available(min_remaining=1800):
        coverage_floor_terms = all_role_backfill_search_terms()
        coverage_floor_sources = _merge_sources(
            public_sources,
            "monster~jooble",
            "remoteok~remotive~arbeitnow~jobicy~weworkremotely",
            "jobtech~eures~uk_findajob~nhs_jobs~jobbank_ca~ba_jobsuche~france_travail~mycareersfuture~tyomarkkinatori~nav_arbeidsplassen",
            "h1b_sponsor~tier1_ats~scrapling_discovery",
        )
        logger.info(
            "6h scraper running coverage-floor backfill: %s role-focused terms across %s countries via %s",
            len(coverage_floor_terms),
            len(countries),
            coverage_floor_sources,
        )
        coverage_floor_code = await run(_base_args(
            queries=_encoded_terms(coverage_floor_terms),
            locations=country_locations,
            sources=coverage_floor_sources,
            max_per_source=140,
            max_per_sponsor=600,
            h1b_sponsor_concurrency=10,
            jobspy_hours_old=336,
            jobspy_page_size=50,
            jobspy_max_pages=50,
            schedule_type="6h-coverage-floor",
        ))
        if coverage_floor_code:
            failures += 1
            logger.warning("6h scraper coverage-floor backfill failed with code %s", coverage_floor_code)
    elif COVERAGE_FLOOR_ENABLED:
        logger.warning("6h scraper skipped coverage-floor backfill because run budget remaining is %.0fs", budget_remaining())

    if PURGE_EXCEPT_TODAY:
        # Destructive, opt-in only. Logged loudly because this deletes every
        # posting not dated "today" and was the cause of positions vanishing
        # between runs. Prefer the rolling-window purge below.
        try:
            counts = purge_except_day(day=None, tz_name=PURGE_TIMEZONE, dry_run=False)
            logger.warning("6h scraper post-run DESTRUCTIVE today-only purge ran: %s", counts)
        except Exception as exc:
            failures += 1
            logger.warning("6h scraper post-run today-only purge failed: %s", exc)
    elif RETENTION_DAYS > 0:
        # Opt-in rolling window: prune only postings older than the window so the
        # board never collapses to a single thin run's output. Disabled (0) by
        # default — nothing is deleted, preserving every scraped position.
        try:
            counts = purge_outside_window(retention_days=RETENTION_DAYS, dry_run=False)
            logger.info("6h scraper post-run rolling-window purge (keep %sd): %s", RETENTION_DAYS, counts)
        except Exception as exc:
            failures += 1
            logger.warning("6h scraper post-run rolling-window purge failed: %s", exc)
    else:
        logger.info("6h scraper post-run purge skipped (no retention window set; nothing deleted).")

    _log_role_country_coverage(floor=COVERAGE_AUDIT_FLOOR)

    total_failure_slots = 2 + max(1, len(public_role_batches))
    return 1 if failures >= total_failure_slots else 0


def _log_role_country_coverage(*, floor: int) -> None:
    """Log the thinnest active role-country cells after the run.

    This is intentionally non-fatal. Provider/API outages should not mark a
    scrape run failed, but the coverage matrix must be visible in Cloud Logs so
    we can tune terms/countries instead of discovering gaps only in the UI.
    """
    if floor <= 0:
        return
    roles = all_role_names()
    counts: dict[tuple[str, str], int] = {
        (role, country): 0
        for role in roles
        for country in TARGET_COUNTRIES
    }
    try:
        client = PostgresClient()
        with client.session() as db:
            rows = db.execute(text("""
                SELECT title, location, country, extra_metadata
                FROM master_jobs
                WHERE status = 'active'
                  AND coalesce(last_seen_at, first_seen_at) >= now() - interval '30 days'
            """)).mappings().all()
    except Exception as exc:
        logger.warning("6h coverage audit skipped: %s", exc)
        return

    for row in rows:
        _category, role = categorize(str(row.get("title") or ""))
        if role not in roles:
            continue
        metadata = row.get("extra_metadata") or {}
        meta_country = metadata.get("visa_country") if isinstance(metadata, dict) else None
        country = (
            resolve_country(str(row.get("country") or ""))
            or resolve_country(str(meta_country or ""))
            or resolve_country(str(row.get("location") or ""))
        )
        if country in TARGET_COUNTRIES:
            counts[(role, country)] = counts.get((role, country), 0) + 1

    weak = [
        {"role": role, "country": country, "count": count}
        for (role, country), count in counts.items()
        if count < floor
    ]
    weak.sort(key=lambda item: (item["count"], item["country"], item["role"]))
    if weak:
        logger.warning(
            "6h role-country coverage audit: %s/%s cells below floor=%s. Lowest cells:\n%s",
            len(weak),
            len(counts),
            floor,
            render_table(weak[:80], headers=["country", "role", "count"]),
        )
    else:
        logger.info("6h role-country coverage audit passed: all %s cells >= %s active jobs", len(counts), floor)


def main() -> int:
    """Run the 6h scrape and ALWAYS exit 0.

    The scheduled run must never be marked "Failed" in Cloud Run for a
    recoverable reason: a brief DB hiccup at startup, a provider outage, or a
    partial source failure are all expected and must not break the every-6h
    cadence. We therefore (a) catch every exception, (b) downgrade any non-zero
    internal code to 0, and (c) log loudly so problems are still visible in
    Cloud Logging. The only things that can still surface as a failed execution
    are infrastructure kills (OOM / platform timeout), which are handled by the
    job's memory budget and --max-retries, not by this process.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        client = PostgresClient()
        with client.session() as db:
            locked = bool(db.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": ADVISORY_LOCK_KEY},
            ).scalar())
            if not locked:
                logger.warning("Another 6h scraper execution is already running; skipping this run.")
                return 0
            try:
                result = asyncio.run(_run_batched())
            finally:
                try:
                    db.execute(
                        text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": ADVISORY_LOCK_KEY},
                    )
                except Exception as unlock_exc:
                    # The advisory lock is session-scoped; closing the session
                    # releases it anyway, so an unlock failure is non-fatal.
                    logger.warning("6h scraper advisory unlock failed (session close releases it): %s", unlock_exc)
        if result:
            logger.error(
                "6h scraper finished with internal code=%s (some passes failed). "
                "Exiting 0 so the every-6h schedule is never marked failed; see warnings above.",
                result,
            )
        return 0
    except Exception as exc:  # noqa: BLE001 - deliberately catch-all
        logger.exception(
            "6h scraper top-level failure (likely DB connect/lock at startup). "
            "Exiting 0 to keep the 6h schedule healthy; investigate via Cloud Logging: %s",
            exc,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
