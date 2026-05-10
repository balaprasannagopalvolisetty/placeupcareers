"""
PlaceUp Career — User profile, preferences, notifications & resume metadata.
All endpoints require a valid JWT bearer token.
"""
import logging
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status

from app.db import user_store
from app.models.user import (
    NotificationItem,
    ResumeMetadata,
    UserPreferences,
    UserProfile,
)
from app.security import current_user_id, hash_password, verify_password

log = logging.getLogger(__name__)
router = APIRouter(prefix="/user", tags=["User"])

MAX_RESUME_BYTES = 10 * 1024 * 1024
ALLOWED_RESUME_EXT = {"pdf", "docx", "doc"}


def _user_to_profile(user: dict) -> UserProfile:
    updated_raw = user.get("updated_at")
    try:
        updated_dt = datetime.fromisoformat(updated_raw) if updated_raw else datetime.now(timezone.utc)
    except Exception:
        updated_dt = datetime.now(timezone.utc)
    return UserProfile(
        id=user["id"],
        first_name=user["first_name"],
        last_name=user["last_name"],
        email=user["email"],
        phone=user.get("phone"),
        location=user.get("location"),
        visa_status=user.get("visa_status"),
        experience_years=user.get("experience_years"),
        current_role=user.get("current_role"),
        plan=user.get("plan") or "Pro",
        summary=user.get("summary"),
        linkedin_url=user.get("linkedin_url"),
        github_url=user.get("github_url"),
        portfolio_url=user.get("portfolio_url"),
        updated_at=updated_dt,
    )


def _humanize(iso: Optional[str]) -> str:
    if not iso:
        return "just now"
    try:
        ts = datetime.fromisoformat(iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        s = int(delta.total_seconds())
        if s < 60: return f"{s}s ago"
        if s < 3600: return f"{s // 60}m ago"
        if s < 86400: return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return "recently"


def _to_resume_meta(row: dict) -> ResumeMetadata:
    uploaded = row.get("uploaded_at")
    try:
        uploaded_dt = datetime.fromisoformat(uploaded) if isinstance(uploaded, str) else datetime.now(timezone.utc)
    except Exception:
        uploaded_dt = datetime.now(timezone.utc)
    return ResumeMetadata(
        id=row["id"],
        name=row.get("name") or "resume.pdf",
        uploaded_at=uploaded_dt,
        score=int(row.get("score") or 0),
        size_bytes=int(row.get("size_bytes") or 0),
        active=bool(row.get("active")),
    )


def _to_prefs(raw: dict) -> UserPreferences:
    return UserPreferences(
        job_preferences=raw.get("job_preferences") or "",
        notification_new_jobs=bool(raw.get("notification_new_jobs", True)),
        notification_daily_digest=bool(raw.get("notification_daily_digest", True)),
        notification_weekly_summary=bool(raw.get("notification_weekly_summary", False)),
        notification_ats_updates=bool(raw.get("notification_ats_updates", True)),
        notification_marketing_emails=bool(raw.get("notification_marketing_emails", False)),
        visa_status=raw.get("visa_status"),
        experience_level=raw.get("experience_level"),
        target_roles=list(raw.get("target_roles") or [])[:5],
        target_locations=list(raw.get("target_locations") or []),
    )


def _build_resume_quick_wins(text: str, skills: list[str], keywords: list[str], target_roles: list[str]) -> list[dict]:
    lower_text = text.lower()
    lower_skills = {s.lower() for s in skills}
    wins: list[dict] = []

    if "react" in lower_skills and "react 18" not in lower_text:
        wins.append({"kw": "React 18", "tip": "Specify your React version if you used React 18.", "impact": "High"})
    if "certification" not in lower_text and "certifications" not in lower_text:
        wins.append({"kw": "Certifications", "tip": "Add a certifications section if you hold relevant credentials.", "impact": "Medium"})
    if "github.com" not in lower_text and "github" not in lower_text:
        wins.append({"kw": "GitHub", "tip": "Add a GitHub profile link so hiring teams can review your work.", "impact": "Medium"})
    if " ai " in f" {lower_text} " and "artificial intelligence" not in lower_text:
        wins.append({"kw": "Artificial Intelligence", "tip": "Spell out acronyms at first mention, for example AI to Artificial Intelligence.", "impact": "Medium"})

    try:
        from app.job_taxonomy import CATEGORIES
        selected = {role.lower() for role in target_roles}
        wanted: set[str] = set()
        for cat in CATEGORIES:
            for role in cat.roles:
                if role.name.lower() in selected:
                    wanted.update(s.lower() for s in role.synonyms if len(s) > 3)
        have = lower_skills | {k.lower() for k in keywords}
        for kw in sorted(wanted - have)[:5]:
            wins.append({"kw": kw, "tip": f"Add '{kw}' where it honestly matches your experience.", "impact": "Medium"})
    except Exception:
        pass

    return wins[:8]


@router.get("/profile", response_model=UserProfile)
async def get_profile(user_id: str = Depends(current_user_id)):
    user = user_store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _user_to_profile(user)


@router.put("/profile", response_model=UserProfile)
async def update_profile(profile: UserProfile = Body(...), user_id: str = Depends(current_user_id)):
    fields = profile.model_dump(exclude_unset=True, exclude_none=True)
    fields.pop("id", None)
    fields.pop("email", None)
    fields.pop("updated_at", None)
    updated = user_store.update_user_profile(user_id, fields)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _user_to_profile(updated)


@router.put("/password")
async def change_password(payload: dict = Body(...), user_id: str = Depends(current_user_id)):
    current = (payload or {}).get("current_password") or ""
    new = (payload or {}).get("new_password") or ""
    if len(new) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    user = user_store.get_user_by_id(user_id)
    if not user or not verify_password(current, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    user_store.set_user_password(user_id, hash_password(new))
    return {"ok": True}


@router.get("/preferences", response_model=UserPreferences)
async def get_preferences(user_id: str = Depends(current_user_id)):
    return _to_prefs(user_store.get_preferences(user_id))


@router.put("/preferences", response_model=UserPreferences)
async def update_preferences(preferences: UserPreferences = Body(...), user_id: str = Depends(current_user_id)):
    raw = user_store.update_preferences(user_id, preferences.model_dump(exclude_unset=False))
    return _to_prefs(raw)


@router.get("/notifications", response_model=list[NotificationItem])
async def list_notifications(user_id: str = Depends(current_user_id)):
    alerts = user_store.list_alerts(user_id, limit=10)
    items: list[NotificationItem] = []
    for a in alerts:
        match = a.get("match_score") or 0
        if match:
            text = f"New match: {a.get('title')} @ {a.get('company')} ({match}%)"
        else:
            text = a.get("message") or a.get("title") or "Update"
        items.append(NotificationItem(
            id=str(a.get("id")), text=text,
            time=_humanize(a.get("created_at")),
            unread=bool(a.get("unread")),
        ))
    return items


@router.get("/resumes", response_model=list[ResumeMetadata])
async def list_user_resumes(user_id: str = Depends(current_user_id)):
    return [_to_resume_meta(r) for r in user_store.list_resumes(user_id)]


@router.post("/resumes/upload", response_model=ResumeMetadata)
async def upload_user_resume(
    file: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
    user_id: str = Depends(current_user_id),
):
    filename = file.filename or "resume.pdf"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ALLOWED_RESUME_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

    storage_root = Path(__file__).resolve().parent.parent.parent / "data" / "resumes" / user_id
    storage_path = None
    try:
        storage_root.mkdir(parents=True, exist_ok=True)
        storage_path = storage_root / f"{_uuid.uuid4().hex[:12]}_{filename}"
        storage_path.write_bytes(content)
    except Exception as exc:
        log.warning(f"Resume file persistence failed: {exc}")
        storage_path = None

    score = 0
    try:
        from app.services.ats_scorer import score_resume_quality
        from app.services.resume_parser import parse_resume_file
        parsed = await parse_resume_file(content, filename)
        score = int(round(float(score_resume_quality(parsed.get("text", "")))))
    except Exception as exc:
        log.warning(f"Resume scoring failed (non-fatal): {exc}")
        score = 0

    existing = user_store.list_resumes(user_id)
    for resume in existing:
        user_store.delete_resume(user_id, resume["id"])

    row = user_store.create_resume(
        user_id,
        name=filename,
        score=score,
        size_bytes=len(content),
        active=True,
        storage_path=str(storage_path) if storage_path else None,
    )
    return _to_resume_meta(row)


@router.post("/resumes/{resume_id}/activate", response_model=ResumeMetadata)
async def activate_user_resume(resume_id: str, user_id: str = Depends(current_user_id)):
    row = user_store.set_active_resume(user_id, resume_id)
    if not row:
        raise HTTPException(status_code=404, detail="Resume not found")
    return _to_resume_meta(row)


@router.delete("/resumes/{resume_id}")
async def delete_user_resume(resume_id: str, user_id: str = Depends(current_user_id)):
    deleted = user_store.delete_resume(user_id, resume_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {"deleted": resume_id}


@router.get("/resume/parsed")
async def get_parsed_active_resume(user_id: str = Depends(current_user_id)):
    """Return the parsed active resume — skills, experience, education,
    keywords. Powers the Profile page Skills strip and the dynamic
    Resume Quick Wins panel."""
    resumes = user_store.list_resumes(user_id)
    active = next((r for r in resumes if r.get("active")), None) or (resumes[0] if resumes else None)
    if not active or not active.get("storage_path"):
        return {"has_resume": False, "skills": [], "keywords": [], "missing_keywords": []}

    try:
        from app.services.resume_parser import parse_resume_file
        from app.utils.text_processing import extract_keywords, extract_skills_from_text
        with open(active["storage_path"], "rb") as fh:
            content = fh.read()
        parsed = await parse_resume_file(content, active.get("name") or "resume.pdf")
        text = parsed.get("text") or ""
        skills = extract_skills_from_text(text)
        keywords = extract_keywords(text, top_n=40)
    except Exception as e:
        return {"has_resume": True, "error": str(e), "skills": [], "keywords": []}

    # Diff against the user's target roles → suggest "Quick Wins".
    prefs = user_store.get_preferences(user_id)
    target_roles = prefs.get("target_roles") or []
    suggestions = _build_resume_quick_wins(text, skills, keywords, target_roles)

    return {
        "has_resume": True,
        "name": active.get("name"),
        "score": active.get("score"),
        "skills": sorted(set(skills)),
        "keywords": keywords[:30],
        "quick_wins": suggestions,
        "target_roles": target_roles,
    }
