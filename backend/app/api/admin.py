"""Private admin API for operations staff.

Routes require a signed-in user whose email is allowlisted in ADMIN_EMAILS or
whose stored plan is "Admin". The frontend route is intentionally hidden from
normal navigation, but backend authorization is the real protection.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.config import settings
from app.db import user_store
from app.security import current_user_id

router = APIRouter(prefix="/admin", tags=["Admin"])


def _admin_email_set() -> set[str]:
    return {email.strip().lower() for email in settings.admin_emails.split(",") if email.strip()}


async def require_admin_user(user_id: str = Depends(current_user_id)) -> dict:
    user = user_store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    email = str(user.get("email") or "").lower()
    plan = str(user.get("plan") or "").lower()
    if email in _admin_email_set() or plan == "admin":
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/summary")
async def admin_summary(_: dict = Depends(require_admin_user)):
    users = user_store.list_users(limit=1000)
    plan_counts: dict[str, int] = {}
    for user in users:
        plan = str(user.get("plan") or "Unknown")
        plan_counts[plan] = plan_counts.get(plan, 0) + 1
    return {
        "users": len(users),
        "plans": plan_counts,
        "payments": {
            "configured": bool(
                settings.payment_basic_checkout_url
                and settings.payment_pro_checkout_url
                and settings.payment_elite_checkout_url
            ),
            "provider": "hosted_checkout",
        },
        "finalscout": {
            "multi_key_configured": bool(settings.finalscout_api_keys or settings.finalscout_api_key),
        },
    }


@router.get("/users")
async def admin_users(
    limit: int = Query(default=200, ge=1, le=1000),
    _: dict = Depends(require_admin_user),
):
    rows = user_store.list_users(limit=limit)
    return {
        "users": [
            {
                "id": row.get("id"),
                "email": row.get("email"),
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "plan": row.get("plan") or "Pro",
                "visa_status": row.get("visa_status"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            for row in rows
        ]
    }


@router.get("/payments")
async def admin_payments(_: dict = Depends(require_admin_user)):
    return {
        "payments": [],
        "note": "Payment provider webhooks are not connected yet; hosted checkout links are configured via environment variables.",
    }


@router.post("/finalscout/upload-csv")
async def admin_finalscout_csv(
    file: UploadFile = File(...),
    limit: int = Query(default=200, ge=1, le=2000),
    dry_run: bool = Query(default=False),
    concurrency: int = Query(default=4, ge=1, le=8),
    _: dict = Depends(require_admin_user),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV must be 5 MB or smaller")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        from app.workers.finalscout_batch import run as run_finalscout_batch

        return await run_finalscout_batch(
            limit=limit,
            input_csv=tmp_path,
            state_file=Path("/tmp/finalscout_admin_state.json"),
            dry_run=dry_run,
            concurrency=concurrency,
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
