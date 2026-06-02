from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.config import settings
from app.services.h1b_sponsor_boards import by_ats


ADZUNA_COUNTRIES = [c.strip().lower() for c in settings.adzuna_countries.split(",") if c.strip()]


@dataclass(frozen=True)
class AtsRegistry:
    greenhouse: list[str] = field(default_factory=list)


def _env_tokens(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [token.strip() for token in raw.replace(";", ",").split(",") if token.strip()]


def load_registry() -> AtsRegistry:
    """Registry pattern for public ATS tokens.

    Add tokens by environment/Secret Manager first:
      GREENHOUSE_BOARD_TOKENS=stripe,airbnb,...

    The existing GREENHOUSE_BOARD_TOKENS setting is reused first. If it is not
    configured, the production job falls back to the curated active H-1B sponsor
    Greenhouse boards already maintained by the ATS pipeline.
    """
    greenhouse = _env_tokens("GREENHOUSE_BOARD_TOKENS")
    if not greenhouse and settings.greenhouse_board_tokens:
        greenhouse = [t.strip() for t in settings.greenhouse_board_tokens.split(",") if t.strip()]
    if not greenhouse:
        greenhouse = [
            str(entry.get("token")).strip()
            for entry in by_ats("greenhouse")
            if entry.get("token")
        ]
    greenhouse = list(dict.fromkeys(greenhouse))
    return AtsRegistry(greenhouse=greenhouse)
