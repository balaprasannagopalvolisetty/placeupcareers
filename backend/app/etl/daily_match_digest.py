"""Cloud Run job entrypoint for 9 AM daily top-match emails."""

from __future__ import annotations

import asyncio
import json
import logging

from app.services.daily_match_digest import send_daily_match_digests

logging.basicConfig(level=logging.INFO)


async def main():
    result = await send_daily_match_digests()
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
