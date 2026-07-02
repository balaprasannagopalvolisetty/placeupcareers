"""User-facing role-request endpoints.

Lets a signed-in user ask PlaceUp to add coverage for a role that isn't in the
taxonomy yet. Requests land in a queue that admins approve or reject from the
admin console (see app/api/admin.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import user_store
from app.security import current_user_id

router = APIRouter(prefix="/user/role-requests", tags=["Role Requests"])


class RoleRequestCreate(BaseModel):
    role: str = Field(min_length=2, max_length=120)
    country: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=1000)


@router.get("")
async def my_role_requests(user_id: str = Depends(current_user_id)):
    return {"requests": user_store.list_role_requests(user_id=user_id, limit=100)}


@router.post("", status_code=201)
async def create_role_request(payload: RoleRequestCreate, user_id: str = Depends(current_user_id)):
    user = user_store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    role = payload.role.strip()
    if not role:
        raise HTTPException(status_code=400, detail="Role is required")

    # Light dedupe: don't let a user spam the same pending role.
    existing = user_store.list_role_requests(user_id=user_id, status="pending", limit=100)
    if any((r.get("role") or "").strip().lower() == role.lower() for r in existing):
        raise HTTPException(status_code=409, detail="You already have a pending request for this role.")

    record = user_store.create_role_request(
        user_id=user_id,
        email=user.get("email") or "",
        role=role,
        country=payload.country.strip(),
        note=payload.note.strip(),
    )
    user_store.record_event(
        kind="role_request",
        label="Role request submitted",
        user_id=user_id,
        email=user.get("email") or "",
        meta={"role": role, "country": payload.country.strip()},
    )
    return record
