"""Production-sized 6-hour job scraper entrypoint for Cloud Run Jobs."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.etl.jobs_scraper import run
from app.job_taxonomy import all_role_backfill_search_terms


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = argparse.Namespace(
        # Focused role-by-role terms: every canonical position is included,
        # with the most useful aliases, without exploding every fragile portal
        # into thousands of requests.
        queries="~".join(term.replace(" ", "_") for term in all_role_backfill_search_terms()),
        locations="United_States~Canada",
        # Attempt every requested source. Each provider is isolated so a WAF,
        # quota, or selector change only marks that source as zero/errored;
        # the rest of the 6h run still writes fresh rows.
        #
        # JobSpy covers LinkedIn, Indeed, ZipRecruiter, Glassdoor, and Google.
        # Native/API sources cover USAJOBS and Dice. Scrapling adds HTML
        # fallback coverage for Monster, Jooble, Google/LinkedIn public pages,
        # and direct career pages from the H1B company list. H1B/tier1 ATS
        # pulls complete company career boards where structured APIs exist.
        sources=(
            "linkedin~indeed~ziprecruiter~glassdoor~google~"
            "usajobs~dice~monster~jooble~"
            "h1b_sponsor~tier1_ats~scrapling_discovery~scrapegraph_discovery"
        ),
        max_per_source=60,
        max_per_sponsor=400,
        h1b_sponsor_concurrency=10,
        jobspy_hours_old=720,
        jobspy_page_size=50,
        jobspy_max_pages=25,
        tiers="T1~T2",
        schedule_type="6h",
        dry_run=False,
    )
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
