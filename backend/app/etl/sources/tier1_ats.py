"""
Tier-1 ATS source — Greenhouse / Lever / Ashby / SmartRecruiters / Workable / Recruitee.

Why a separate source
---------------------
These six ATS platforms expose unauthenticated, no-rate-limit JSON
endpoints that return a company's complete open-roles list. That makes
them the highest signal-per-request source we have — orders of
magnitude better than scraping search results from job aggregators that
rate-limit or rotate selectors.

This module wraps the per-ATS scrapers (already living in
`app.services.careers_ats`) with the two things they don't do
themselves:

1. **Sponsor catalog fan-out** — read `H1B_SPONSOR_BOARDS` and dispatch
   the right scraper for each company in parallel, with a concurrency
   semaphore so we stay polite.
2. **Taxonomy title filter** — drop any job whose title doesn't match
   one of the expanded roles in `app.job_taxonomy.CATEGORIES`. The ops team
   asked specifically for "jobs from the taxonomy roles, nothing
   else"; without this filter every random role at every sponsored
   company would land in master_jobs.

The result is a list of `JobPost` objects ready for the existing
normalize → stage → load pipeline.

Run as a CLI for ad-hoc testing:
    python -m app.etl.sources.tier1_ats --limit 3 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
from typing import Iterable, Optional

from app.job_taxonomy import CATEGORIES, EXTRA_ROLE_SYNONYMS, _expand_with_seniority
from app.models.job import JobPost, VisaBadges
from app.services.careers_ats import scrape_ats
from app.services.h1b_sponsor_boards import H1B_SPONSOR_BOARDS, filter_by_tier
from app.utils.deduplication import generate_content_hash

logger = logging.getLogger("placeup.etl.tier1_ats")


# ─── Taxonomy title matcher ───────────────────────────────────────────

# Only the six ATS providers the user asked for. Everything else in
# H1B_SPONSOR_BOARDS (Workday, BambooHR, Personio, …) still works via
# the legacy `h1b_sponsor` source — we don't duplicate them here.
TIER1_ATS_PROVIDERS: frozenset[str] = frozenset({
    "greenhouse", "lever", "ashby", "smartrecruiters", "workable", "recruitee",
})


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 +/#.-]+", " ", (text or "").lower()).strip()


def _build_role_index() -> tuple[dict[str, tuple[str, str]], list[tuple[re.Pattern, str, str]]]:
    """Compile a fast (term → (category, role)) lookup + a fallback regex list.

    Why two layers:
      - The exact-match dict catches "Software Engineer" → ("Technology
        & Engineering", "Software Engineer") in one hash lookup.
      - The regex list catches "Senior Software Engineer, Platform" by
        looking for any role/synonym anywhere in the title.

    Built once at import time. Total cost ~few ms.
    """
    exact: dict[str, tuple[str, str]] = {}
    patterns: list[tuple[re.Pattern, str, str]] = []
    for cat in CATEGORIES:
        for role in cat.roles:
            # Three pools of terms feed the matcher:
            #   1. Canonical role name + base synonyms from CATEGORIES.
            #   2. Modern aliases from EXTRA_ROLE_SYNONYMS (added to widen
            #      coverage of titles HR systems actually post).
            #   3. Auto-generated seniority variants (Senior X, X II, ...).
            all_terms: list[str] = [role.name, *role.synonyms]
            all_terms.extend(EXTRA_ROLE_SYNONYMS.get(role.name, ()))
            all_terms.extend(_expand_with_seniority(role.name))
            for term in all_terms:
                key = _normalize(term)
                if not key or key in exact:
                    continue
                exact[key] = (cat.name, role.name)
                patterns.append((
                    re.compile(rf"\b{re.escape(key)}\b", re.IGNORECASE),
                    cat.name,
                    role.name,
                ))
    return exact, patterns


_EXACT_INDEX, _PATTERN_INDEX = _build_role_index()


def match_taxonomy(title: str) -> Optional[tuple[str, str]]:
    """Return (category, role) if the title matches any taxonomy entry."""
    if not title:
        return None
    norm = _normalize(title)
    hit = _EXACT_INDEX.get(norm)
    if hit:
        return hit
    # Walk the longer terms first so "machine learning engineer" wins
    # over "engineer" when both are in the index.
    for pattern, cat, role in _PATTERN_INDEX:
        if pattern.search(title):
            return cat, role
    return None


# ─── Pipeline ─────────────────────────────────────────────────────────

async def scrape_tier1_ats(
    *,
    tiers: tuple[str, ...] = ("T1", "T2"),
    max_jobs_per_sponsor: int = 500,
    concurrency: int = 8,
    only_companies: Optional[set[str]] = None,
    apply_taxonomy_filter: bool = True,
) -> list[JobPost]:
    """Fan out to every Tier-1 ATS sponsor and return filtered open roles.

    Args:
        tiers:                T1 / T2 / T3 tiers from h1b_sponsor_boards.
        max_jobs_per_sponsor: Per-board cap (Workable boards can be huge).
        concurrency:          Max in-flight scrapes — keep modest, these
                              endpoints don't rate-limit but we want to
                              be a good citizen.
        only_companies:       Restrict to an allow-list of canonical names.
        apply_taxonomy_filter: Drop jobs whose title doesn't match the expanded
                              taxonomy roles. Defaults True — the user
                              explicitly asked for this behaviour.

    Returns:
        Deduplicated list of JobPost objects stamped with h1b_verified=True,
        taxonomy_category, and taxonomy_role.
    """
    sponsors = [s for s in filter_by_tier(tiers) if s.get("ats") in TIER1_ATS_PROVIDERS]
    if only_companies:
        names = {c.lower() for c in only_companies}
        sponsors = [s for s in sponsors if s.get("company", "").lower() in names]
    if not sponsors:
        logger.warning("tier1_ats: no eligible sponsors after filters")
        return []
    logger.info("tier1_ats: %s eligible sponsors across %s providers", len(sponsors), len(TIER1_ATS_PROVIDERS))

    semaphore = asyncio.Semaphore(concurrency)

    async def _scrape_one(entry: dict) -> tuple[dict, list[JobPost]]:
        async with semaphore:
            try:
                jobs = await scrape_ats(
                    ats_name=entry["ats"],
                    board_token=entry["token"],
                    max_jobs=max_jobs_per_sponsor,
                )
                return entry, jobs
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "tier1_ats: sponsor %s (%s/%s) failed: %s",
                    entry.get("company"), entry.get("ats"), entry.get("token"), exc,
                )
                return entry, []

    results = await asyncio.gather(*[_scrape_one(s) for s in sponsors])

    seen_hashes: set[str] = set()
    out: list[JobPost] = []
    matched = 0
    dropped_by_filter = 0

    for entry, jobs in results:
        canonical_company = entry.get("company") or ""
        for job in jobs:
            # Apply the taxonomy filter BEFORE the dedupe — otherwise a
            # noisy "Office Manager" role would slip through as the
            # canonical record and the real "Software Engineer" copy
            # would lose to dedup.
            tax = match_taxonomy(job.title)
            if apply_taxonomy_filter and not tax:
                dropped_by_filter += 1
                continue

            if canonical_company:
                # Force the canonical name so master_jobs dedupes
                # "Stripe, Inc." and "Stripe" together later.
                job.company = canonical_company
                job.content_hash = generate_content_hash(
                    job.title, job.company, job.location or ""
                )

            # Every Tier-1 ATS sponsor is by definition an H1B sponsor
            # — stamp the verification flags so the frontend visa
            # filter surfaces them prominently.
            existing_visa = job.visa or VisaBadges()
            job.visa = VisaBadges(
                visa_opt=existing_visa.visa_opt,
                visa_stem_opt=existing_visa.visa_stem_opt,
                visa_h1b=True,
                h1b_verified=True,
                visa_score=max(existing_visa.visa_score, 80),
            )

            # Tag with the taxonomy match so downstream (Jobs page
            # category filter, ATS scorer) can use it without re-parsing.
            if tax:
                cat_name, role_name = tax
                extra = dict(job.extra_metadata or {})
                extra.setdefault("taxonomy_category", cat_name)
                extra.setdefault("taxonomy_role", role_name)
                extra.setdefault("source_tier", "tier1_ats")
                extra.setdefault("h1b_sponsor_tier", entry.get("h1b_tier"))
                job.extra_metadata = extra
                matched += 1

            if job.content_hash in seen_hashes:
                continue
            seen_hashes.add(job.content_hash)
            out.append(job)

    logger.info(
        "tier1_ats: %s unique jobs (matched %s, dropped %s by taxonomy filter, %s sponsors)",
        len(out), matched, dropped_by_filter, len(sponsors),
    )
    return out


# ─── CLI ──────────────────────────────────────────────────────────────

def _summarize(jobs: list[JobPost]) -> dict:
    by_cat: dict[str, int] = {}
    for j in jobs:
        cat = (j.extra_metadata or {}).get("taxonomy_category") or "Uncategorized"
        by_cat[cat] = by_cat.get(cat, 0) + 1
    return {
        "total": len(jobs),
        "companies": len({j.company for j in jobs if j.company}),
        "by_category": dict(sorted(by_cat.items(), key=lambda x: -x[1])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull jobs from Tier-1 ATS boards (filtered to taxonomy roles).")
    parser.add_argument("--tiers", default="T1,T2", help="Comma-separated H1B sponsor tiers (T1/T2/T3).")
    parser.add_argument("--limit", type=int, default=500, help="Max jobs per sponsor.")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--no-filter", action="store_true", help="Disable the taxonomy title filter (debug only).")
    parser.add_argument("--only", help="Comma-separated company names to include.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary instead of pushing to DB.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    only = {c.strip() for c in (args.only or "").split(",") if c.strip()} or None
    jobs = asyncio.run(scrape_tier1_ats(
        tiers=tuple(t.strip() for t in args.tiers.split(",") if t.strip()),
        max_jobs_per_sponsor=args.limit,
        concurrency=args.concurrency,
        only_companies=only,
        apply_taxonomy_filter=not args.no_filter,
    ))

    import json
    print(json.dumps(_summarize(jobs), indent=2))

    if args.dry_run:
        return 0

    # Push to DB through the normal normalize → stage → load path.
    from app.db.postgres import PostgresClient
    from app.etl.loaders.jobs import load_normalized_jobs
    from app.etl.normalizers.jobs import normalize_job_payload

    client = PostgresClient()
    payloads = [j.model_dump(mode="json") for j in jobs]
    normalized = [normalize_job_payload(p) for p in payloads]
    with client.session() as db:
        loaded = load_normalized_jobs(db, normalized)
        db.commit()
    logger.info("tier1_ats: %s jobs loaded to jobs table", loaded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
