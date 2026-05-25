"""Production-sized 6-hour job scraper entrypoint for Cloud Run Jobs."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.etl.jobs_scraper import run
from app.job_taxonomy import all_taxonomy_scrape_search_terms


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = argparse.Namespace(
        queries="~".join(term.replace(" ", "_") for term in all_taxonomy_scrape_search_terms()),
        locations="United_States~Canada",
        # LinkedIn guest scraping is currently rate-limiting heavily in Cloud
        # Run. Keep the 6h job on reliable sources so each run finishes and
        # writes fresh rows instead of spending hours retrying 429s.
        #
        # tier1_ats hits Greenhouse/Lever/Ashby/SmartRecruiters/Workable/
        # Recruitee directly (no auth, no rate limit, structured JSON) and
        # filters results to the 88 taxonomy roles before they hit the DB.
        # It runs in addition to h1b_sponsor (which covers Workday/BambooHR
        # too) so we get the broadest possible coverage.
        # ZipRecruiter currently blocks Cloud Run egress with Cloudflare WAF
        # 403s. Leaving it in the 6h job wastes retries and pollutes logs,
        # while the reliable sources below still cover broad job-board,
        # verified sponsor ATS, direct career page, and Google Jobs discovery.
        sources="indeed~google~h1b_sponsor~tier1_ats~scrapegraph_discovery",
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
