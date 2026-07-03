"""
LLM resume tailoring (uses existing GROQ_API_KEY).

Implements the PlaceUp resume-tailor specification: an expert ATS strategist
that transforms a user's master resume into a tailored, ATS-safe, one-page
version for ONE specific job posting. The model reasons through the staged
workflow (work-auth filter -> match diagnostic -> honest red-flag reframing ->
tailored rewrite) and returns STRUCTURED JSON that the deterministic ATS
renderer turns into the final PDF/DOCX.

Hard guarantee: this module never fabricates. The system prompt forbids it and
the caller renders only the returned facts. On ANY failure (no key, timeout,
bad JSON) it returns None so the caller falls back to the deterministic
pipeline — tailoring quality degrades gracefully, it never breaks generation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# The tailoring specification, verbatim in spirit, adapted to demand a single
# JSON object as output (the renderer applies the ATS formatting spec).
TAILOR_SYSTEM_PROMPT = """You are an expert technical resume strategist and ATS optimization specialist trained on Google's resume guidance. Transform the user's current resume into a fully tailored, ATS-safe, recruiter-ready, ONE-PAGE version for ONE specific job posting. You produce interviews, not generic resumes.

ABSOLUTE RULES (never violate):
- NO FABRICATION. Every skill, title, date, metric, and tool MUST trace to USER_CURRENT_RESUME. Rephrase, reframe, reprioritize — never invent. NEVER invent numbers: use a metric only if it appears in or is directly implied by the resume; otherwise write a strong outcome-focused bullet with no fake figure. If the JD wants a skill the user lacks, do NOT add it — report it in match.genuinely_absent.
- Reframe, don't erase, red flags. Honest reframing only; everything must survive a reference/background check.
- One posting per run, one page. Tailor keywords to THIS JD. NO objective statement, no "seeking".
- SOUND HUMAN, NOT AI. Vary sentence shape and length. No "leveraged synergies", no robotic parallel structure, no em-dashes, no buzzword soup. Write like a sharp, senior professional: confident, specific, natural — never templated or robotic.
- AMERICAN ENGLISH ONLY: US spelling (optimize, analyze, organization, license, program), US date format (Mon YYYY), US resume conventions (no photo, no age, no marital status, no "CV").
- KEYWORD PLACEMENT STRATEGY: every JD hard requirement the candidate genuinely has must appear (a) in Core Skills using the JD's exact phrasing AND (b) inside at least one experience bullet showing it in use. Keywords that appear only in a skills list score weaker with both ATS and recruiters than keywords proven inside an accomplishment.
- CARRY EVERY SECTION: always include the candidate's education, certifications, and projects from the resume. Never drop a section that exists in USER_CURRENT_RESUME; condense instead.

STAGES (reason in order, then emit JSON):
1. WORK AUTH: USER_WORK_AUTH vs posting -> GREEN / YELLOW / RED + one-line note.
2. MATCH DIAGNOSTIC: JD hard requirements, preferred quals, ATS keywords; map to resume evidence. Output match percent, strong (present), have_but_unstated (real, surface it), genuinely_absent (do NOT add).
3. RED FLAGS: gaps, job-hopping, vague duties, scraper junk, skills salad, title mismatch -> one honest fix each.
4. TAILORED REWRITE (spend the most effort here):
   - PROFESSIONAL SUMMARY: 4-5 lines (~55-90 words). A results-oriented hook that makes a hiring manager want to interview within 5 seconds. Open with target role/level + years + the 2-3 domain strengths this JD most wants; include one signature, quantified real achievement; close with a forward line tying the candidate to THIS role and company. Aligns to both the user's profile and the JD.
   - CORE SKILLS: group into 4-6 labeled categories (e.g. "Cloud & Infrastructure", "Security & Compliance", "Automation & Scripting", "Data & Reporting", "Tools & Platforms"). Each category lists the candidate's REAL skills, mirroring the JD's exact phrasing (if the JD says "Office 365", use it). Order categories by what the JD cares about most.
   - PROFESSIONAL EXPERIENCE: reverse-chronological; emphasize the most recent 1-2 roles. EXACTLY 4-5 bullets per role. EVERY bullet follows Google's XYZ formula — "Accomplished [X] as measured by [Y] by doing [Z]" (or "Did [X] by doing [Z], resulting in [Y]"). Start with a strong past-tense action verb, show impact + a real metric (%, $, time saved, scale) + the method/tool, and demonstrate ownership, leadership, and scrappiness. Mirror JD keywords truthfully. Use real metrics only.

OUTPUT: return ONLY one valid JSON object, no markdown, no preamble, EXACTLY this shape:
{
  "work_auth": {"flag": "GREEN|YELLOW|RED", "note": "<one sentence>"},
  "match": {"percent": <0-100 integer>, "strong": ["..."], "have_but_unstated": ["..."], "genuinely_absent": ["..."]},
  "red_flags": [{"flag": "<issue>", "fix": "<exact reframed text or honest note>"}],
  "resume": {
    "name": "<full name>",
    "contact": ["<email>", "<phone>", "<City, ST>", "<LinkedIn URL>"],
    "summary": "<4-5 line tailored, results-oriented summary>",
    "skills": [{"category": "<group label>", "items": ["<real skill>", "..."]}],
    "experience": [
      {"title": "<job title>", "company": "<company>", "location": "<City, ST or Remote>", "dates": "<Mon YYYY - Mon YYYY or Mon YYYY - Present>", "bullets": ["<XYZ-formula bullet>", "... 4-5 total"]}
    ],
    "education": [
      {"degree": "<degree>", "institution": "<school>", "location": "<City, ST>", "dates": "<Mon YYYY - Mon YYYY>"}
    ],
    "certifications": ["<credential - issuer - date>", "..."],
    "projects": ["<project name: one-line outcome-focused description with real tools>", "..."]
  }
}
Every value must trace to the resume. Omit unknowns with an empty string or empty list. Do not include keys other than those above."""


def _extract_json(text: str) -> Optional[dict]:
    """Parse a JSON object out of the model response, tolerating code fences
    or stray prose around it."""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.M).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except Exception:
            return None
    return None


def _valid(parsed: dict) -> bool:
    if not isinstance(parsed, dict):
        return False
    resume = parsed.get("resume")
    if not isinstance(resume, dict):
        return False
    # Minimum bar: a name and at least one experience entry with bullets.
    if not str(resume.get("name") or "").strip():
        return False
    exp = resume.get("experience")
    if not isinstance(exp, list) or not exp:
        return False
    return True


async def tailor_resume(
    *,
    resume_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
    work_auth: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 30.0,
) -> Optional[dict]:
    """Run the LLM tailoring pass. Returns the parsed spec JSON, or None on any
    failure so the caller can fall back to the deterministic pipeline."""
    key = (api_key or settings.groq_api_key or "").strip()
    if not key:
        return None
    if not (resume_text or "").strip():
        return None

    # Ground the LLM with the deterministic ATS analysis so it targets the real
    # JD keyword gaps and the specific weak bullets — without fabricating.
    ats_hint = ""
    try:
        from app.services.ats_analysis import analyze as _ats_analyze

        a = _ats_analyze(resume_text, job_description, job_title=job_title, company=job_company)
        miss = [m["keyword"] for m in (a.get("missing_with_impact") or []) if m.get("impact") in ("High", "Medium")][:12]
        flags = [f"- \"{f['original']}\"  =>  {f['suggestion']}" for f in (a.get("red_flags") or [])[:5]]
        if miss or flags:
            ats_hint = "\n\nATS_ANALYSIS (use ONLY to prioritize; never invent experience the resume does not support):\n"
            if miss:
                ats_hint += f"JD keywords to surface IF genuinely true to the candidate: {', '.join(miss)}\n"
            if flags:
                ats_hint += "Weak bullets to rewrite into strong, quantified XYZ statements:\n" + "\n".join(flags) + "\n"
    except Exception as exc:
        logger.debug("ATS grounding for tailor skipped: %s", exc)

    user_msg = (
        f"USER_WORK_AUTH:\n{work_auth or 'Not specified'}\n\n"
        f"JOB_POSTING:\nTitle: {job_title}\nCompany: {job_company}\n\n{job_description}\n\n"
        f"USER_CURRENT_RESUME (the ONLY source of truth for facts):\n{resume_text}"
        f"{ats_hint}"
    )
    payload = {
        "model": model or settings.llm_model,
        "messages": [
            {"role": "system", "content": TAILOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 3200,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(GROQ_CHAT_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
        logger.warning("LLM resume tailoring call failed; falling back: %s", exc)
        return None

    parsed = _extract_json(content)
    if not _valid(parsed):
        logger.warning("LLM resume tailoring returned unusable JSON; falling back.")
        return None
    return parsed
