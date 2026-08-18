"""Taxonomy evolution report.

The role taxonomy must follow the real market, in both directions:

* ADD candidates — job titles collected from ATS platforms that map to none
  of the current taxonomy roles. High-volume unknown titles are exactly the
  roles users are missing; this worker clusters them (normalized title) and
  reports the top candidates with live counts and example titles.

* REMOVE candidates — taxonomy roles that currently collect ZERO active open
  positions across all 32 countries. They cost scrape budget every run and
  clutter the filter dropdown without serving anyone.

The taxonomy itself lives in code (app/job_taxonomy.py + job_taxonomy_extra.py)
so additions stay reviewed: this worker produces the concrete list, logs it,
prints JSON, and emails ops. Run daily/weekly as a Cloud Run Job:

    python -m app.workers.taxonomy_evolution --top 60
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import logging
import re
from collections import Counter, defaultdict

from sqlalchemy import text

from app.db.postgres import PostgresClient
from app.job_taxonomy import CATEGORIES, categorize

logger = logging.getLogger("placeup.taxonomy_evolution")

_BATCH = 5000

# Strip noise so "Senior Backend Engineer (Remote) - II" and
# "Backend Engineer" cluster together.
_NOISE = re.compile(
    r"\b(senior|sr\.?|junior|jr\.?|staff|principal|lead|associate|entry[- ]level|"
    r"mid[- ]level|intern(ship)?|graduate|new grad|remote|hybrid|onsite|on-site|"
    r"contract(or)?|full[- ]time|part[- ]time|temporary|urgent(ly)? hiring|"
    r"i{1,3}|iv|v|\d{1,2})\b",
    re.I,
)
_PAREN = re.compile(r"[\(\[].*?[\)\]]")
_SEP = re.compile(r"\s*[-–|,/]\s*")


def _normalize_title(title: str) -> str:
    value = _PAREN.sub(" ", str(title or ""))
    value = _SEP.split(value)[0]  # keep the leading role phrase, drop location/team suffixes
    value = _NOISE.sub(" ", value)
    value = re.sub(r"[^a-z&+ ]", " ", value.lower())
    value = re.sub(r"\s+", " ", value).strip()
    return value


def run(*, top: int = 60, min_count: int = 25) -> dict:
    client = PostgresClient()
    role_counts: Counter[str] = Counter()
    unknown_counts: Counter[str] = Counter()
    unknown_examples: dict[str, str] = {}
    unknown_countries: dict[str, set] = defaultdict(set)
    scanned = 0

    with client.session() as db:
        offset = 0
        while True:
            rows = db.execute(text(
                "SELECT title, country FROM master_jobs WHERE status = 'active' "
                "ORDER BY id LIMIT :lim OFFSET :off"
            ), {"lim": _BATCH, "off": offset}).mappings().all()
            if not rows:
                break
            for row in rows:
                scanned += 1
                title = str(row["title"] or "")
                _category, role = categorize(title)
                if role != "Other":
                    role_counts[role] += 1
                    continue
                key = _normalize_title(title)
                if len(key) < 4:
                    continue
                unknown_counts[key] += 1
                unknown_examples.setdefault(key, title[:120])
                if row["country"]:
                    unknown_countries[key].add(str(row["country"]))
            offset += _BATCH

    all_roles = [role.name for cat in CATEGORIES for role in cat.roles]
    dead_roles = sorted(role for role in all_roles if role_counts.get(role, 0) == 0)
    add_candidates = [
        {
            "normalized_title": key,
            "active_jobs": count,
            "example_title": unknown_examples.get(key, ""),
            "countries": sorted(unknown_countries.get(key, set()))[:12],
        }
        for key, count in unknown_counts.most_common(top)
        if count >= min_count
    ]

    report = {
        "scanned_active_jobs": scanned,
        "taxonomy_roles": len(all_roles),
        "roles_with_inventory": sum(1 for role in all_roles if role_counts.get(role, 0) > 0),
        "remove_candidates_zero_inventory": dead_roles,
        "add_candidates_unknown_titles": add_candidates,
    }
    logger.info("Taxonomy evolution report: %s add candidates, %s zero-inventory roles",
                len(add_candidates), len(dead_roles))
    _email_report(report)
    return report


def _email_report(report: dict) -> None:
    """Send the report to ops so taxonomy updates get made. Never raises."""
    import os

    recipient = os.getenv("TAXONOMY_REPORT_EMAIL", "operations@placeupcareer.com").strip()
    if not recipient:
        return
    try:
        from app.services.email import send_email

        body = json.dumps(report, indent=2)[:60000]
        send_email(
            recipient,
            "[PlaceUp taxonomy] Add/remove role candidates",
            html=f"<pre style='font-family:monospace'>{html_lib.escape(body)}</pre>",
            text=body,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Taxonomy report email failed: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Report taxonomy add/remove candidates from live inventory.")
    parser.add_argument("--top", type=int, default=60, help="Max unknown-title candidates to report")
    parser.add_argument("--min-count", type=int, default=25, help="Minimum live jobs for an add candidate")
    args = parser.parse_args()
    print(json.dumps(run(top=args.top, min_count=args.min_count), indent=2))
