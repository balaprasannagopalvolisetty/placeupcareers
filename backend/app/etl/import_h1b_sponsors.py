"""Import curated H1B sponsor data into the configured backend database."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.config import settings
from app.services.h1b_excel_importer import import_h1b_excel

logger = logging.getLogger("placeup.etl.import_h1b_sponsors")


async def run(force: bool = False) -> int:
    if settings.database_backend != "postgres":
        raise RuntimeError("H1B sponsor import now requires DATABASE_BACKEND=postgres.")
    from app.db.postgres import PostgresClient

    db = PostgresClient()

    return await import_h1b_excel(db, force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import PlaceUp H1B sponsor data.")
    parser.add_argument("--force", action="store_true", help="Update sponsor rows even when data already exists.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    written = asyncio.run(run(force=args.force))
    logger.info("H1B sponsor import completed. Rows written: %s", written)


if __name__ == "__main__":
    main()
