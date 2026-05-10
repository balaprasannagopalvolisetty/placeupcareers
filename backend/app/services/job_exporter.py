"""
Export scraped jobs to CSV (and Excel when available).
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def export_jobs(jobs: list[dict], export_dir: str = "data/exports") -> dict[str, str]:
    """
    Export job dictionaries to CSV and optionally XLSX.

    Returns a mapping of generated artifact paths.
    """
    if not jobs:
        return {}

    output_dir = Path(export_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = [_flatten_job(job) for job in jobs]
    fieldnames = _collect_fieldnames(rows)

    # Single rolling CSV. We try atomic-rename first (POSIX-clean), but on
    # Windows the destination is locked when the user has it open in Excel,
    # so we fall back to a direct overwrite + finally a timestamped sidecar.
    import os, shutil
    from datetime import datetime as _dt

    artifacts: dict[str, str] = {}
    csv_path = output_dir / "placeup_jobs.csv"
    tmp_path = csv_path.with_suffix(".csv.tmp")
    try:
        with tmp_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        try:
            os.replace(tmp_path, csv_path)            # atomic, POSIX-clean
        except PermissionError:
            try:
                shutil.copyfile(tmp_path, csv_path)   # Excel has it open: overwrite
                tmp_path.unlink(missing_ok=True)
            except PermissionError:
                # Still locked — write a dated sidecar so we never lose data.
                stamped = output_dir / f"placeup_jobs_{_dt.utcnow():%Y%m%dT%H%M%S}.csv"
                shutil.move(str(tmp_path), str(stamped))
                logger.warning(
                    f"placeup_jobs.csv was locked; wrote sidecar to {stamped.name}"
                )
                csv_path = stamped
        artifacts["csv"] = str(csv_path)
    except Exception as exc:
        logger.warning(f"CSV export failed: {exc}")

    # Single rolling XLSX twin (optional). Same lock-tolerant path.
    try:
        import pandas as pd

        xlsx_path = output_dir / "placeup_jobs.xlsx"
        try:
            pd.DataFrame(rows).to_excel(xlsx_path, index=False)
        except PermissionError:
            stamped = output_dir / f"placeup_jobs_{_dt.utcnow():%Y%m%dT%H%M%S}.xlsx"
            pd.DataFrame(rows).to_excel(stamped, index=False)
            xlsx_path = stamped
            logger.warning(f"placeup_jobs.xlsx was locked; wrote sidecar to {stamped.name}")
        artifacts["xlsx"] = str(xlsx_path)
    except Exception as exc:
        logger.info(f"Excel export skipped: {exc}")

    return artifacts


def _collect_fieldnames(rows: list[dict]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                ordered.append(key)
    return ordered


def _flatten_metadata(metadata, prefix: str = "meta") -> dict:
    """Spreadsheet-friendly: flatten one level; deeper nests become JSON."""
    rows: dict = {}
    if not metadata or not isinstance(metadata, dict):
        return rows
    for key, value in metadata.items():
        safe = str(key).replace(" ", "_").replace(".", "_")
        field = f"{prefix}_{safe}"
        if isinstance(value, (dict, list)):
            try:
                rows[field] = json.dumps(value, ensure_ascii=False, default=str)
            except Exception:
                rows[field] = str(value)
        else:
            rows[field] = value
    return rows


def _flatten_job(job: dict) -> dict:
    """Convert a JobPost dict into a flat row suitable for CSV."""
    salary = job.get("salary") or {}
    visa = job.get("visa") or {}
    extra = job.get("extra_metadata") or {}
    base = {
        "id": job.get("id", ""),
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "source": job.get("source", ""),
        "job_url": job.get("job_url", ""),
        "category": job.get("category", ""),
        "experience_level": job.get("experience_level", ""),
        "industry": job.get("industry", ""),
        "is_remote": job.get("is_remote", ""),
        "min_salary": salary.get("min_salary", "") if isinstance(salary, dict) else "",
        "max_salary": salary.get("max_salary", "") if isinstance(salary, dict) else "",
        "visa_opt": visa.get("visa_opt", False) if isinstance(visa, dict) else False,
        "visa_stem_opt": visa.get("visa_stem_opt", False) if isinstance(visa, dict) else False,
        "visa_h1b": visa.get("visa_h1b", False) if isinstance(visa, dict) else False,
        "h1b_verified": visa.get("h1b_verified", False) if isinstance(visa, dict) else False,
        "visa_score": visa.get("visa_score", 0) if isinstance(visa, dict) else 0,
        "posted_at": job.get("posted_at", ""),
        "scraped_at": job.get("scraped_at", ""),
        "description_chars": len(str(job.get("description", "") or "")),
    }
    base.update(_flatten_metadata(extra, prefix="meta"))
    return base
