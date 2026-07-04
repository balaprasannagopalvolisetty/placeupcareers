"""Cloud Run Job: backfill global visa-friendly labels on jobs / master_jobs.

Recently ingested rows (and every row written before the global visa upgrade)
can be missing the global visa metadata (``visa_country``, ``visa_programs``,
``english_friendly``, ``sponsor_verified``, ...) that the Jobs page filters
on. This job re-runs :func:`classify_global_visa` over stored rows and also
re-verifies each employer against the ``visa_sponsors`` / ``h1b_sponsors``
registries, then updates the visa columns + ``extra_metadata`` in place.

Run inside the existing backend image (it has the Cloud SQL socket + deps):

    python -m app.etl.visa_label_backfill                 # only rows missing labels
    python -m app.etl.visa_label_backfill --all           # relabel every row
    python -m app.etl.visa_label_backfill --since 2026-06-01
    python -m app.etl.visa_label_backfill --dry-run

Safe to re-run: updates are idempotent and existing positive signals
(visa_score, legacy H1B booleans, sponsor_verified) are only ever OR-ed /
max-ed, never downgraded.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.postgres import PostgresClient
from app.db.schema import Company, H1BSponsor, Job, MasterJob, VisaSponsor
from app.services.employer_normalizer import normalize_employer
from app.services.global_visa_rules import classify_global_visa

logger = logging.getLogger("placeup.etl.visa_label_backfill")

# extra_metadata keys owned by this job (mirrors app/etl/normalizers/jobs.py)
VISA_META_KEYS = (
    "visa_country",
    "visa_country_name",
    "visa_programs",
    "visa_program_names",
    "sponsor_verified",
    "sponsor_source",
    "english_friendly",
)

# Map US program codes emitted by classify_global_visa onto the legacy
# boolean columns so old API filters keep working.
_LEGACY_FLAG_BY_PROGRAM = {
    "h1b": "visa_h1b",
    "opt": "visa_opt",
    "stem_opt": "visa_stem_opt",
}

BATCH_SIZE = 500
DESCRIPTION_CHARS = 20_000  # plenty for keyword scoring, caps memory


def load_sponsor_registry(db: Session) -> dict[str, dict[str, str]]:
    """{country_code: {normalized_employer_name: source_name}}"""
    registry: dict[str, dict[str, str]] = {}

    for name, country, source in db.execute(
        select(VisaSponsor.normalized_name, VisaSponsor.country, VisaSponsor.source_name)
    ):
        key = normalize_employer(name)
        if key:
            registry.setdefault((country or "").upper(), {}).setdefault(key, source or "visa_sponsors")

    us = registry.setdefault("US", {})
    for (name,) in db.execute(select(H1BSponsor.employer_name)):
        key = normalize_employer(name)
        if key:
            us.setdefault(key, "uscis_h1b")

    total = sum(len(v) for v in registry.values())
    logger.info("Sponsor registry loaded: %s employers across %s countries", total, len(registry))
    return registry


def compute_update(
    row: Job | MasterJob,
    company_name: str,
    registry: dict[str, dict[str, str]],
) -> dict | None:
    """Return column updates for ``row``, or None when nothing changes."""
    meta = dict(row.extra_metadata) if isinstance(row.extra_metadata, dict) else {}

    country_hint = (row.country or meta.get("visa_country") or "") or None
    already_verified = bool(row.h1b_verified) or bool(meta.get("sponsor_verified"))
    sponsor_source = meta.get("sponsor_source")

    classification = classify_global_visa(
        title=row.title or "",
        company=company_name or "",
        description=(row.description or "")[:DESCRIPTION_CHARS],
        location=row.location or "",
        country_code=country_hint,
        sponsor_verified=already_verified,
        sponsor_source=sponsor_source,
    )
    country = classification["country_code"]

    # Registry re-verification: if the employer is a listed sponsor for the
    # job's country, upgrade to sponsor_verified and re-classify so the
    # sponsor bonus is included in the score/programs.
    if not already_verified and country and company_name:
        employer_key = normalize_employer(company_name)
        match_source = registry.get(country, {}).get(employer_key) if employer_key else None
        if match_source:
            classification = classify_global_visa(
                title=row.title or "",
                company=company_name or "",
                description=(row.description or "")[:DESCRIPTION_CHARS],
                location=row.location or "",
                country_code=country_hint,
                sponsor_verified=True,
                sponsor_source=match_source,
            )

    new_meta = meta | {
        "visa_country": classification["country_code"],
        "visa_country_name": classification["country_name"],
        "visa_programs": classification["visa_programs"],
        "visa_program_names": classification["visa_program_names"],
        "sponsor_verified": bool(classification["sponsor_verified"]),
        "sponsor_source": classification["sponsor_source"],
        "english_friendly": bool(classification["english_friendly"]),
    }

    updates: dict = {}
    if new_meta != meta:
        updates["extra_metadata"] = new_meta

    new_score = max(int(row.visa_score or 0), int(classification.get("score") or 0))
    if new_score != int(row.visa_score or 0):
        updates["visa_score"] = new_score

    if classification["country_code"] == "US":
        for program_code, column in _LEGACY_FLAG_BY_PROGRAM.items():
            if program_code in classification["visa_programs"] and not getattr(row, column):
                updates[column] = True
        if classification["sponsor_verified"] and not row.h1b_verified:
            updates["h1b_verified"] = True

    if not (row.country or "").strip() and classification["country_code"]:
        updates["country"] = classification["country_code"]

    return updates or None


def _iter_batches(db: Session, model, *, only_missing: bool, since: datetime | None):
    last_id = ""
    while True:
        stmt = (
            select(model)
            .where(model.id > last_id)
            .order_by(model.id)
            .limit(BATCH_SIZE)
        )
        if only_missing:
            stmt = stmt.where(text("(extra_metadata->>'visa_country') IS NULL"))
        if since is not None:
            stmt = stmt.where(model.first_seen_at >= since)
        rows = db.execute(stmt).scalars().all()
        if not rows:
            return
        yield rows
        last_id = rows[-1].id


def _company_names(db: Session, rows: list[Job]) -> dict:
    ids = {row.company_id for row in rows if getattr(row, "company_id", None)}
    if not ids:
        return {}
    return dict(db.execute(select(Company.id, Company.name).where(Company.id.in_(ids))).all())


def backfill_table(
    client: PostgresClient,
    model,
    registry_cache: dict,
    *,
    only_missing: bool,
    since: datetime | None,
    dry_run: bool,
) -> tuple[int, int]:
    scanned = updated = 0
    label = model.__tablename__
    with client.session() as db:
        if "registry" not in registry_cache:
            registry_cache["registry"] = load_sponsor_registry(db)
        registry = registry_cache["registry"]

        for rows in _iter_batches(db, model, only_missing=only_missing, since=since):
            names = _company_names(db, rows) if model is Job else {}
            for row in rows:
                scanned += 1
                company_name = (
                    names.get(row.company_id, "") if model is Job else (row.company or "")
                )
                updates = compute_update(row, company_name, registry)
                if not updates:
                    continue
                updated += 1
                if dry_run:
                    if updated <= 10:
                        logger.info("[dry-run] %s %s -> %s", label, row.id, {
                            k: v for k, v in updates.items() if k != "extra_metadata"
                        } | ({"visa_programs": updates["extra_metadata"].get("visa_programs")} if "extra_metadata" in updates else {}))
                    continue
                for key, value in updates.items():
                    setattr(row, key, value)
            if not dry_run:
                db.commit()
            if scanned % 5000 < BATCH_SIZE:
                logger.info("%s: scanned=%s updated=%s", label, scanned, updated)
        if dry_run:
            db.rollback()
    logger.info("%s done: scanned=%s updated=%s%s", label, scanned, updated, " (dry-run)" if dry_run else "")
    return scanned, updated


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Backfill global visa labels on stored jobs.")
    parser.add_argument("--all", action="store_true", help="Relabel every row (default: only rows missing visa_country).")
    parser.add_argument("--since", type=str, default=None, help="Only rows first seen on/after this ISO date (e.g. 2026-06-01).")
    parser.add_argument("--tables", type=str, default="jobs,master_jobs", help="Comma list: jobs,master_jobs")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing.")
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since) if args.since else None
    only_missing = not args.all
    models = {"jobs": Job, "master_jobs": MasterJob}
    targets = [models[t.strip()] for t in args.tables.split(",") if t.strip() in models]
    if not targets:
        logger.error("No valid tables in --tables=%s", args.tables)
        return 2

    client = PostgresClient()
    registry_cache: dict = {}
    total_scanned = total_updated = 0
    for model in targets:
        scanned, updated = backfill_table(
            client,
            model,
            registry_cache,
            only_missing=only_missing,
            since=since,
            dry_run=args.dry_run,
        )
        total_scanned += scanned
        total_updated += updated

    logger.info("Backfill complete: scanned=%s updated=%s", total_scanned, total_updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
