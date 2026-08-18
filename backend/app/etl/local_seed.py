"""Idempotently load bundled sponsor reference data into local PostgreSQL."""
from __future__ import annotations

import logging
import subprocess
import sys

from sqlalchemy import text

from app.db.postgres import PostgresClient

log = logging.getLogger("placeup.local_seed")


def _count(table: str) -> int:
    database = PostgresClient()
    with database.session() as session:
        exists = session.execute(text("SELECT to_regclass(:table)"), {"table": f"public.{table}"}).scalar()
        if not exists:
            return 0
        return int(session.execute(text(f'SELECT count(*) FROM "{table}"')).scalar() or 0)


def _run(module: str, *args: str) -> None:
    command = [sys.executable, "-m", module, *args]
    log.info("Running local seed: %s", " ".join(command))
    subprocess.run(command, check=True)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if _count("h1b_sponsors") == 0:
        _run("app.etl.import_h1b_sponsors", "--force")
    else:
        log.info("H-1B sponsor data already present; skipping import")
    if _count("visa_sponsors") == 0:
        _run("app.etl.import_visa_sponsors", "--force-h1b")
    else:
        log.info("Global visa sponsor data already present; skipping import")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
