"""Monthly official visa sponsor dataset import."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.config import settings
from app.services.visa_sponsor_importer import import_global_visa_sponsors

logger = logging.getLogger("placeup.etl.import_visa_sponsors")


async def run(*, force_h1b: bool = False) -> dict[str, int]:
    if settings.database_backend != "postgres":
        raise RuntimeError("Visa sponsor import requires DATABASE_BACKEND=postgres.")
    from app.db.postgres import PostgresClient

    db = PostgresClient()
    return await import_global_visa_sponsors(db, force_h1b=force_h1b)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import official global visa sponsor datasets.")
    parser.add_argument("--force-h1b", action="store_true", help="Refresh the bundled/imported US H-1B rows before mirroring.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    counts = asyncio.run(run(force_h1b=args.force_h1b))
    logger.info("Visa sponsor import completed: %s", counts)


if __name__ == "__main__":
    main()
