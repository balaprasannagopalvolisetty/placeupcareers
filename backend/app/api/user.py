"""
PlaceUp Career — User profile, preferences, notifications & resume metadata.
All endpoints require a valid JWT bearer token.
"""
import logging
import re
import uuid as _uuid
import base64
import html
import io
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import settings
from app.db import user_store
from app.models.user import (
    DashboardSummary,
    DashboardSummaryAlert,
    NotificationItem,
    ResumeMetadata,
    UserApplication,
    UserPreferences,
    UserProfile,
)
from app.dependencies import get_db
from app.security import current_user_id, hash_password, verify_password

log = logging.getLogger(__name__)
router = APIRouter(prefix="/user", tags=["User"])

MAX_RESUME_BYTES = 10 * 1024 * 1024
ALLOWED_RESUME_EXT = {"pdf", "docx"}
TAILOR_DAILY_LIMIT = 25


class TailorQueueRequest(BaseModel):
    job_id: str
    title: str = ""
    company: str = ""
    location: str = ""
    job_url: str = ""
    description: str = ""
    match_score: int = 0


class TailorGenerateRequest(BaseModel):
    format: str = "doc"


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
    score = int(row.get("score") or 0)
    parsed_text = (row.get("parsed_text") or "").strip()
    if parsed_text:
        try:
            from app.services.ats_scorer import score_resume_quality
            score = int(round(float(score_resume_quality(parsed_text))))
        except Exception as exc:
            log.warning("Resume score refresh failed for %s: %s", row.get("id"), exc)
    return ResumeMetadata(
        id=row["id"],
        name=row.get("name") or "resume.pdf",
        uploaded_at=uploaded_dt,
        score=score,
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
        target_roles=list(raw.get("target_roles") or [])[:25],
        target_locations=list(raw.get("target_locations") or []),
    )


_DATE_RANGE_RE = re.compile(
    r"(?:19|20)\d{2}\s*(?:[–—\-]|to)+\s*(?:(?:19|20)\d{2}|present|current|now)", re.I
)
_COMPANY_HINT_RE = re.compile(
    r"\b(Inc|LLC|Ltd|Corp|Corporation|Technologies|Technology|Systems|Solutions|Labs|Group|"
    r"Consulting|Services|Software|Bank|Capital|Health|University|Institute|Global|Networks)\b\.?",
    re.I,
)


def _extract_past_companies(experience_lines: list[str]) -> list[str]:
    """Best-effort extraction of employer names from resume experience lines.

    Targets lines that carry a date range (the usual 'Company — Title, 2021-2023'
    shape) or a corporate suffix, then keeps the leading name segment.
    """
    companies: list[str] = []
    seen: set[str] = set()
    for ln in experience_lines or []:
        line = (ln or "").strip()
        if not line or len(line) > 140:
            continue
        if not (_DATE_RANGE_RE.search(line) or _COMPANY_HINT_RE.search(line)):
            continue
        cleaned = _DATE_RANGE_RE.sub("", line).strip(" ,|·•—–-")
        seg = re.split(r"\s*[|,•·]\s*|\s+[–—]\s+|\s+-\s+", cleaned)[0].strip(" .")
        # Skip segments that read like job titles rather than employers
        if not seg or len(seg) < 3 or len(seg) > 60:
            continue
        if re.search(r"\b(engineer|developer|manager|analyst|intern|consultant|lead|architect|designer|scientist|administrator|specialist)\b", seg, re.I) and not _COMPANY_HINT_RE.search(seg):
            continue
        key = seg.lower()
        if key in seen:
            continue
        seen.add(key)
        companies.append(seg)
        if len(companies) >= 8:
            break
    return companies


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


def _active_resume_row(user_id: str) -> Optional[dict]:
    resumes = user_store.list_resumes(user_id)
    return next((r for r in resumes if r.get("active")), None) or (resumes[0] if resumes else None)


def _clean_resume_lines(text: str, limit: int = 70) -> list[str]:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" -\t")
        if len(line) < 3:
            continue
        if line.lower() in {"resume", "curriculum vitae"}:
            continue
        lines.append(line)
        if len(lines) >= limit:
            break
    if not lines and text:
        lines = textwrap.wrap(re.sub(r"\s+", " ", text).strip(), width=100)[:limit]
    return lines


def _tailor_keywords(resume_text: str, job_text: str) -> tuple[list[str], list[str]]:
    try:
        from app.utils.text_processing import compute_keyword_overlap, extract_relevant_keywords, extract_skills_from_text
        resume_terms = list(dict.fromkeys(extract_skills_from_text(resume_text) + extract_relevant_keywords(resume_text, top_n=45)))
        job_terms = list(dict.fromkeys(extract_skills_from_text(job_text) + extract_relevant_keywords(job_text, top_n=45)))
        matched, missing, _ = compute_keyword_overlap(resume_terms, job_terms)
        return matched[:12], missing[:16]
    except Exception:
        words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", job_text)]
        stop = {"the", "and", "with", "for", "you", "are", "job", "work", "team", "role", "will"}
        ranked: list[str] = []
        for word in words:
            if word not in stop and word not in ranked:
                ranked.append(word)
        lower_resume = resume_text.lower()
        matched = [w for w in ranked if w in lower_resume][:12]
        missing = [w for w in ranked if w not in lower_resume][:16]
        return matched, missing


def _candidate_name(user: dict, resume_text: str) -> str:
    first = str(user.get("first_name") or "").strip()
    last = str(user.get("last_name") or "").strip()
    if first or last:
        return " ".join(part for part in (first, last) if part).strip()
    for raw in (resume_text or "").splitlines()[:8]:
        line = re.sub(r"\s+", " ", raw).strip()
        if 3 <= len(line) <= 60 and not re.search(r"@|https?://|\d{3}|\bresume\b", line, re.I):
            return line
    return "Candidate Name"


def _compact_line(value: str, *, max_len: int = 180) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" -\t")
    return value[: max_len - 1].rstrip() + "." if len(value) > max_len else value


def _professional_bullets(lines: list[str], target_keywords: list[str], *, limit: int = 10) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    for line in lines:
        clean = _compact_line(line, max_len=210)
        if len(clean) < 12:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        if target_keywords and not any(term.lower() in key for term in target_keywords[:12]):
            clean = f"{clean.rstrip('.')} with emphasis on {target_keywords[len(bullets) % len(target_keywords)]}."
        bullets.append(clean)
        if len(bullets) >= limit:
            break
    if not bullets:
        bullets = [
            "Delivered role-relevant technical work with measurable ownership, cross-functional communication, and production-quality execution.",
            "Applied structured problem solving, documentation, and stakeholder collaboration to support business-critical outcomes.",
        ]
    return bullets


def _build_tailored_resume_payload(
    resume_text: str,
    resume_json: dict,
    job: dict,
    matched: list[str],
    missing: list[str],
    user: dict,
) -> dict:
    title = job.get("title") or "Target Role"
    company = job.get("company") or "Target Company"
    location = job.get("location") or ""
    contact = resume_json.get("contact") if isinstance(resume_json, dict) else {}
    contact = contact if isinstance(contact, dict) else {}
    links = [str(v).strip() for v in (contact.get("links") or []) if str(v).strip()]
    contact_items = [
        contact.get("email") or user.get("email"),
        contact.get("phone") or user.get("phone"),
        *links[:2],
    ]
    skills = list(dict.fromkeys([
        *matched[:10],
        *missing[:12],
        *[str(v).strip() for v in (resume_json.get("skills") or []) if str(v).strip()],
    ]))
    target_keywords = list(dict.fromkeys([*matched[:10], *missing[:14]]))
    role_terms = ", ".join(target_keywords[:8]) if target_keywords else str(title)
    summary = (
        f"{title} candidate aligned to {company} with strengths in {role_terms}. "
        "Prepared to contribute through clear ownership, secure execution, measurable delivery, and fast collaboration with engineering and business partners."
    )
    experience_lines = resume_json.get("experience") or _clean_resume_lines(resume_text, limit=36)
    project_lines = resume_json.get("projects") or []
    education_lines = resume_json.get("education") or []
    cert_lines = resume_json.get("certifications") or []
    return {
        "name": _candidate_name(user, resume_text),
        "contact": [str(item).strip() for item in contact_items if str(item or "").strip()],
        "target": f"{title} | {company}{(' | ' + location) if location else ''}",
        "summary": summary,
        "skills": skills[:28],
        "experience": _professional_bullets([str(v) for v in experience_lines], target_keywords, limit=11),
        "projects": _professional_bullets([str(v) for v in project_lines], target_keywords, limit=4) if project_lines else [],
        "education": [_compact_line(str(v), max_len=160) for v in education_lines[:5] if _compact_line(str(v), max_len=160)],
        "certifications": [_compact_line(str(v), max_len=160) for v in cert_lines[:4] if _compact_line(str(v), max_len=160)],
        "keywords": target_keywords[:18],
    }


def _doc_bytes(resume: dict, title: str) -> bytes:
    def p(value: str) -> str:
        return html.escape(str(value or ""))

    def bullets(items: list[str]) -> str:
        return "\n".join(f"<li>{p(item)}</li>" for item in items)

    section_blocks = [
        ("PROFESSIONAL SUMMARY", f"<p>{p(resume['summary'])}</p>"),
        ("TECHNICAL SKILLS", f"<p>{p(', '.join(resume['skills']))}</p>"),
        ("PROFESSIONAL EXPERIENCE", f"<ul>{bullets(resume['experience'])}</ul>"),
    ]
    if resume.get("projects"):
        section_blocks.append(("PROJECTS", f"<ul>{bullets(resume['projects'])}</ul>"))
    if resume.get("education"):
        section_blocks.append(("EDUCATION", f"<ul>{bullets(resume['education'])}</ul>"))
    if resume.get("certifications"):
        section_blocks.append(("CERTIFICATIONS", f"<ul>{bullets(resume['certifications'])}</ul>"))
    section_blocks.append(("TARGET KEYWORDS", f"<p>{p(', '.join(resume['keywords']))}</p>"))
    sections_html = "\n".join(
        f"<h2>{heading}</h2>\n{body}"
        for heading, body in section_blocks
    )
    document = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    @page {{ margin: 0.55in; }}
    body {{ font-family: Georgia, 'Times New Roman', serif; color: #111; line-height: 1.25; margin: 0; font-size: 10.5pt; }}
    h1 {{ font-family: Arial, sans-serif; font-size: 18pt; text-align: center; letter-spacing: 0.5px; margin: 0; }}
    .contact {{ text-align: center; font-family: Arial, sans-serif; font-size: 8.5pt; margin: 4px 0 10px; }}
    .target {{ text-align: center; font-family: Arial, sans-serif; font-size: 8.5pt; color: #333; margin-bottom: 12px; }}
    h2 {{ font-family: Arial, sans-serif; font-size: 9.5pt; letter-spacing: 0.8px; border-bottom: 1px solid #111; margin: 11px 0 5px; padding-bottom: 2px; }}
    p {{ margin: 0 0 5px; }}
    ul {{ margin: 0 0 4px 17px; padding: 0; }}
    li {{ margin: 0 0 3px; }}
  </style>
</head>
<body>
  <h1>{p(resume['name'])}</h1>
  <div class="contact">{p(' | '.join(resume['contact']))}</div>
  <div class="target">{p(resume['target'])}</div>
  {sections_html}
</body>
</html>"""
    return document.encode("utf-8")


def _simple_pdf_bytes(resume: dict) -> bytes:
    lines = [
        resume.get("name") or "Candidate Name",
        " | ".join(resume.get("contact") or []),
        resume.get("target") or "",
        "",
        "PROFESSIONAL SUMMARY",
        resume.get("summary") or "",
        "",
        "TECHNICAL SKILLS",
        ", ".join(resume.get("skills") or []),
        "",
        "PROFESSIONAL EXPERIENCE",
        *[f"- {item}" for item in (resume.get("experience") or [])],
    ]
    pages = [lines[i:i + 42] for i in range(0, len(lines), 42)] or [[resume.get("name") or "Resume"]]
    objects: list[bytes] = [
        b"",  # catalog placeholder
        b"",  # pages placeholder
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids: list[int] = []

    def esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    for page in pages:
        stream_lines = ["BT", "/F1 10 Tf", "50 760 Td", "14 TL"]
        for idx, line in enumerate(page):
            if idx:
                stream_lines.append("T*")
            stream_lines.append(f"({esc(line[:110])}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", "replace")
        content_id = len(objects) + 1
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        page_id = len(objects) + 1
        kids.append(page_id)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )

    objects[0] = f"<< /Type /Catalog /Pages 2 0 R >>".encode()
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{kid} 0 R' for kid in kids)}] /Count {len(kids)} >>".encode()
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{idx} 0 obj\n".encode())
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(pdf)


def _pdf_bytes(resume: dict, title: str) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            leftMargin=0.55 * inch,
            rightMargin=0.55 * inch,
            topMargin=0.45 * inch,
            bottomMargin=0.45 * inch,
            title=title,
        )
        base = getSampleStyleSheet()
        styles = {
            "name": ParagraphStyle("Name", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=17, leading=20, alignment=TA_CENTER, spaceAfter=2),
            "contact": ParagraphStyle("Contact", parent=base["Normal"], fontName="Helvetica", fontSize=8.2, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#333333"), spaceAfter=5),
            "target": ParagraphStyle("Target", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#555555"), spaceAfter=8),
            "section": ParagraphStyle("Section", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=11, alignment=TA_LEFT, spaceBefore=7, spaceAfter=2),
            "body": ParagraphStyle("Body", parent=base["Normal"], fontName="Times-Roman", fontSize=10, leading=12, spaceAfter=3),
            "bullet": ParagraphStyle("Bullet", parent=base["Normal"], fontName="Times-Roman", fontSize=9.7, leading=11.2, leftIndent=12, firstLineIndent=-8, spaceAfter=1.5),
        }

        def safe(value: str) -> str:
            return html.escape(str(value or "")).replace("\n", "<br/>")

        def section(story: list, heading: str) -> None:
            story.append(Paragraph(safe(heading), styles["section"]))
            story.append(HRFlowable(width="100%", thickness=0.7, color=colors.black, spaceBefore=0, spaceAfter=4))

        def add_bullets(story: list, items: list[str]) -> None:
            for item in items:
                story.append(Paragraph(f"- {safe(item)}", styles["bullet"]))

        story: list = [
            Paragraph(safe(resume.get("name")), styles["name"]),
            Paragraph(safe(" | ".join(resume.get("contact") or [])), styles["contact"]),
            Paragraph(safe(resume.get("target")), styles["target"]),
        ]
        section(story, "PROFESSIONAL SUMMARY")
        story.append(Paragraph(safe(resume.get("summary")), styles["body"]))
        section(story, "TECHNICAL SKILLS")
        story.append(Paragraph(safe(", ".join(resume.get("skills") or [])), styles["body"]))
        section(story, "PROFESSIONAL EXPERIENCE")
        add_bullets(story, resume.get("experience") or [])
        if resume.get("projects"):
            section(story, "PROJECTS")
            add_bullets(story, resume.get("projects") or [])
        if resume.get("education"):
            section(story, "EDUCATION")
            add_bullets(story, resume.get("education") or [])
        if resume.get("certifications"):
            section(story, "CERTIFICATIONS")
            add_bullets(story, resume.get("certifications") or [])
        section(story, "TARGET KEYWORDS")
        story.append(Paragraph(safe(", ".join(resume.get("keywords") or [])), styles["body"]))
        story.append(Spacer(1, 0.01 * inch))
        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        log.warning("ReportLab tailored PDF generation failed, using fallback: %s", exc)
        return _simple_pdf_bytes(resume)


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
    # Revoke all other refresh-token sessions so a stolen old password
    # can't keep an attacker logged in elsewhere.
    try:
        user_store.revoke_user_sessions(user_id)
    except Exception:
        pass
    return {"ok": True}


@router.delete("/account")
async def delete_account(payload: dict = Body(...), user_id: str = Depends(current_user_id)):
    """Permanently delete the caller's account + every record we hold.

    Requires the current password as a final safeguard so a stolen
    bearer token can't wipe an account without also knowing the
    user's password.

    Honours the deletion promise in /privacy: "Deletion removes active
    records immediately; backups roll off within 30 days."
    """
    confirm = (payload or {}).get("password") or ""
    user = user_store.get_user_by_id(user_id)
    if not user:
        # Pretend success — don't leak whether the account existed.
        return {"ok": True, "deleted": {}}
    # If the account was created via OAuth and has no password set,
    # require the confirmation phrase "DELETE" instead so the user
    # still has to actively type something.
    password_hash = user.get("password_hash") or ""
    if password_hash:
        if not verify_password(confirm, password_hash):
            raise HTTPException(status_code=401, detail="Password does not match")
    else:
        if confirm.strip() != "DELETE":
            raise HTTPException(
                status_code=400,
                detail="Type DELETE to confirm permanent removal of your account.",
            )
    counts = user_store.delete_user(user_id)
    log.info("Account deleted: user_id=%s counts=%s", user_id, counts)
    return {"ok": True, "deleted": counts}


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


@router.get("/dashboard-summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    user_id: str = Depends(current_user_id),
    db=Depends(get_db),
):
    """Compact data bundle for the dashboard overview cards/activity feed."""
    resumes = user_store.list_resumes(user_id)
    active_resume = next((r for r in resumes if r.get("active")), None) or (resumes[0] if resumes else None)
    resume_score = int((active_resume or {}).get("score") or 0)
    if active_resume and (active_resume.get("parsed_text") or "").strip():
        try:
            from app.services.ats_scorer import score_resume_quality
            resume_score = int(round(float(score_resume_quality(active_resume.get("parsed_text") or ""))))
        except Exception as exc:
            log.warning("Dashboard summary resume score fallback failed for %s: %s", user_id, exc)

    # Keep the overview fast. A broad COUNT(*) over the production jobs table
    # can delay resume/application cards even though those cards are user data.
    total_jobs = 0

    try:
        total_applications = user_store.count_user_applications(user_id)
    except Exception as exc:
        log.warning("Dashboard summary application count failed: %s", exc)
        total_applications = 0

    recent_alerts: list[DashboardSummaryAlert] = []
    for alert in user_store.list_alerts(user_id, limit=6):
        recent_alerts.append(DashboardSummaryAlert(
            id=str(alert.get("id")),
            title=alert.get("title") or "Update",
            company=alert.get("company") or "",
            match_score=int(alert.get("match_score") or 0),
            message=alert.get("message"),
            time=_humanize(alert.get("created_at")),
            unread=bool(alert.get("unread")),
        ))

    return DashboardSummary(
        resume_score=resume_score,
        has_resume=bool(active_resume),
        active_resume_name=(active_resume or {}).get("name"),
        total_resumes=len(resumes),
        total_jobs=total_jobs,
        total_applications=total_applications,
        recent_alerts=recent_alerts,
    )


@router.post("/applications")
async def save_user_application(payload: UserApplication = Body(...), user_id: str = Depends(current_user_id)):
    """Store whether a user applied or skipped a job for analytics."""
    try:
        return user_store.upsert_user_application(user_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/applications")
async def list_user_applications(user_id: str = Depends(current_user_id)):
    return user_store.list_user_applications(user_id)


@router.get("/tailor-queue")
async def list_tailor_queue(user_id: str = Depends(current_user_id)):
    items = user_store.list_tailor_queue(user_id)
    used_today = user_store.count_tailor_requests_today(user_id)
    return {
        "items": items,
        "used_today": used_today,
        "daily_limit": TAILOR_DAILY_LIMIT,
        "remaining_today": max(0, TAILOR_DAILY_LIMIT - used_today),
    }


@router.post("/tailor-queue")
async def add_tailor_queue_item(payload: TailorQueueRequest = Body(...), user_id: str = Depends(current_user_id)):
    try:
        item = user_store.upsert_tailor_queue_item(
            user_id,
            payload.model_dump(),
            daily_limit=TAILOR_DAILY_LIMIT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    used_today = user_store.count_tailor_requests_today(user_id)
    return {
        "item": item,
        "used_today": used_today,
        "daily_limit": TAILOR_DAILY_LIMIT,
        "remaining_today": max(0, TAILOR_DAILY_LIMIT - used_today),
    }


@router.post("/tailor-queue/{queue_id}/generate")
async def generate_tailored_resume(
    queue_id: str,
    payload: TailorGenerateRequest = Body(default=TailorGenerateRequest()),
    db=Depends(get_db),
    user_id: str = Depends(current_user_id),
):
    item = user_store.get_tailor_queue_item(user_id, queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Tailor queue item not found")
    active_resume = _active_resume_row(user_id)
    resume_text = (active_resume or {}).get("parsed_text") or ""
    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="Upload or re-upload an active resume before tailoring.")
    resume_json = (active_resume or {}).get("parsed_json") or {}
    if not isinstance(resume_json, dict) or not (resume_json.get("sections") or resume_json.get("experience") or resume_json.get("summary")):
        try:
            from app.services.resume_parser import resume_text_to_json
            resume_json = resume_text_to_json(
                resume_text,
                metadata={
                    "filename": (active_resume or {}).get("name"),
                    "derived_for_tailor": True,
                },
            )
        except Exception as exc:
            log.warning("Tailor resume_json derivation failed for %s: %s", user_id, exc)
            resume_json = {}

    job = None
    try:
        job = await db.get_job(str(item.get("job_id") or ""))
    except Exception as exc:
        log.warning("Tailor queue job lookup failed for %s: %s", item.get("job_id"), exc)
    job_data = dict(job or {})
    for key in ("job_id", "title", "company", "location", "job_url", "description", "match_score"):
        if not job_data.get(key):
            job_data[key] = item.get(key)

    job_text = f"{job_data.get('title') or ''}\n{job_data.get('description') or ''}".strip()
    matched, missing = _tailor_keywords(resume_text, job_text)
    user = user_store.get_user_by_id(user_id) or {}
    tailored_resume = _build_tailored_resume_payload(resume_text, resume_json, job_data, matched, missing, user)
    projected_score = max(95, min(98, int(item.get("match_score") or 0) + max(12, len(missing[:10]))))
    title = f"{job_data.get('title') or 'Tailored Resume'} - {job_data.get('company') or 'PlaceUp'}"
    requested = (payload.format or "doc").lower().strip()
    is_pdf = requested == "pdf"
    ext = "pdf" if is_pdf else "doc"
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{title}_ATS_{projected_score}.{ext}")[:140]
    content = _pdf_bytes(tailored_resume, title) if is_pdf else _doc_bytes(tailored_resume, title)
    content_type = "application/pdf" if is_pdf else "application/msword"

    user_store.update_tailor_queue_item(user_id, queue_id, {
        "status": "generated",
        "ats_score": projected_score,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keyword_targets": missing[:12],
        "last_format": ext,
        "filename": filename,
        "summary": f"Tailored for {title}",
    })
    return {
        "queue_id": queue_id,
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode("ascii"),
        "ats_score": projected_score,
        "matched_keywords": matched,
        "keyword_targets": missing[:12],
    }


@router.get("/resumes", response_model=list[ResumeMetadata])
async def list_user_resumes(user_id: str = Depends(current_user_id)):
    return [_to_resume_meta(r) for r in user_store.list_resumes(user_id)]


@router.post("/resumes/upload", response_model=ResumeMetadata)
async def upload_user_resume(
    file: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
    user_id: str = Depends(current_user_id),
):
    filename = file.filename or "resume.pdf"
    existing_resumes = user_store.list_resumes(user_id)
    if len(existing_resumes) >= 5:
        raise HTTPException(status_code=400, detail="Resume limit reached. Delete an old resume before uploading another.")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ALLOWED_RESUME_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

    try:
        from app.services.ats_scorer import score_resume_quality
        from app.services.resume_parser import parse_resume_file, resume_text_to_json
        parsed = await parse_resume_file(content, filename)
        parsed_text = (parsed.get("text") or "").strip()
        if len(parsed_text) < 30:
            raise HTTPException(
                status_code=400,
                detail="Could not extract readable text from this resume. Please upload a text-based PDF or DOCX.",
            )
        score = int(round(float(score_resume_quality(parsed_text))))
        parsed_json = resume_text_to_json(
            parsed_text,
            metadata={
                "filename": filename,
                "format": parsed.get("format"),
                "word_count": parsed.get("word_count"),
                "page_count": parsed.get("page_count"),
                "score": score,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.warning(f"Resume parsing/scoring failed: {exc}")
        raise HTTPException(status_code=400, detail=f"Resume parsing failed: {exc}")

    # Resume text is stored in Firestore via create_resume(parsed_text=...).
    # No local file storage needed — Cloud Run containers are ephemeral.

    row = user_store.create_resume(
        user_id,
        name=filename,
        score=score,
        size_bytes=len(content),
        active=True,
        storage_path=None,
        parsed_text=parsed_text,
        parsed_json=parsed_json,
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
    if not active:
        return {"has_resume": False, "skills": [], "keywords": [], "missing_keywords": []}

    try:
        from app.utils.text_processing import extract_keywords, extract_skills_from_text
        text = (active.get("parsed_text") or "").strip()
        if not text:
            return {
                "has_resume": True,
                "error": "This older resume record does not have stored parsed text. Please re-upload your resume so it can be saved to your private user profile.",
                "skills": [],
                "keywords": [],
                "missing_keywords": [],
            }
        resume_json = active.get("parsed_json") or {}
        # Resumes uploaded before parsed_json existed have only parsed_text.
        # Derive the structured document on the fly so the Profile page's
        # Active Resume view and Past Companies always render.
        if not (resume_json.get("sections") or resume_json.get("experience") or resume_json.get("summary")):
            try:
                from app.services.resume_parser import resume_text_to_json
                resume_json = resume_text_to_json(
                    text,
                    metadata={
                        "filename": active.get("name"),
                        "score": active.get("score"),
                        "derived_at_read": True,
                    },
                )
            except Exception as derive_exc:  # noqa: BLE001 — keep flat fallback working
                log.warning("On-the-fly resume_json derivation failed for %s: %s", user_id, derive_exc)
        skills = resume_json.get("skills") or extract_skills_from_text(text)
        keywords = resume_json.get("keywords") or extract_keywords(text, top_n=40)
    except Exception as e:
        log.warning("Active resume parse lookup failed for %s: %s", user_id, e)
        return {
            "has_resume": True,
            "error": "Resume text is not available. Please re-upload your resume so it can be saved to your private user profile.",
            "skills": [],
            "keywords": [],
        }

    # Diff against the user's target roles to suggest "Quick Wins".
    prefs = user_store.get_preferences(user_id)
    target_roles = prefs.get("target_roles") or []
    suggestions = _build_resume_quick_wins(text, skills, keywords, target_roles)

    return {
        "has_resume": True,
        "name": active.get("name"),
        "score": active.get("score"),
        "skills": sorted(set(skills)),
        "keywords": keywords[:30],
        "resume_json": resume_json,
        "quick_wins": suggestions,
        "target_roles": target_roles,
        "past_companies": _extract_past_companies(resume_json.get("experience") or []),
    }
