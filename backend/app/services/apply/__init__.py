"""PlaceUp Career — automated application (apply-orchestration) subsystem.

See `MASTER_DOCUMENTATION.md` › "Automated Application System" for the full
architecture. Public surface:

    from app.services.apply import (
        resolve_tier, get_adapter, ATS_TIERS,
        orchestrator, apply_queue,
    )
"""
from app.services.apply.tiers import ATS_TIERS, resolve_tier, tier_for_ats
from app.services.apply.base import ApplyResult, get_adapter, register_adapter, TIER_A_ADAPTERS
# Import the adapters module at package load so every Tier A adapter registers
# itself into TIER_A_ADAPTERS. Without this, tier routing could see an empty
# registry and mis-route a Tier A job to the browser path.
from app.services.apply import adapters_tier_a  # noqa: F401,E402

__all__ = [
    "ATS_TIERS",
    "resolve_tier",
    "tier_for_ats",
    "ApplyResult",
    "get_adapter",
    "register_adapter",
    "TIER_A_ADAPTERS",
]
