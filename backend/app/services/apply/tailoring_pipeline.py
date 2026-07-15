"""
Resume & cover-letter tailoring pipeline (doc section D).

Steps:
    1. Pull the JD (from the job) and the user's base resume + profile.
    2. Extract JD signals (skills, keywords, seniority, must-haves) — cheap.
    3. Tailor the resume: re-order/re-phrase bullets to the JD using ONLY true
       facts from the base resume (no fabrication). Reuses the existing
       `resume_tailor_llm.tailor_resume` + `ats_analysis`.
    4. Generate a cover letter.
    5. Score against the existing match/ATS scorers and build a diff for review.
    6. Cache tailored artifacts per (user, company) so re-applications reuse work.

This module is the single `run_tailoring` entry point the orchestrator injects
as `tailor_fn`. It degrades gracefully: if the LLM/key is unavailable it still
returns scores from the deterministic scorers so the apply flow never blocks.
"""
from __future__ import annotations

import logging
import json
from typing import Optional

log = logging.getLogger("placeup.apply.tailor")
TAILORING_PIPELINE_VERSION = 2


def extract_jd_signals(job: dict) -> dict:
    """Cheap JD-signal extraction using the existing deterministic analyzer.
    Kept model-agnostic; a Flash-Lite call can replace this later."""
    jd = job.get("description") or job.get("job_description") or ""
    title = job.get("title") or ""
    company = job.get("company") or ""
    signals = {"keywords": [], "seniority": "", "must_haves": []}
    try:
        from app.services.ats_analysis import analyze as _ats_analyze

        a = _ats_analyze("", jd, job_title=title, company=company)
        signals["keywords"] = [
            m.get("keyword") for m in (a.get("missing_with_impact") or []) if m.get("keyword")
        ][:20]
    except Exception as exc:
        log.debug("jd signal extraction skipped: %s", exc)
    return signals


async def _score(resume_text: str, job: dict) -> tuple[int, int]:
    """Return (match_score, ats_score) from the existing async scorers.

    Uses the real service entry points: `match_engine.compute_match_score`
    (returns MatchResult.overall_match_score) and
    `ats_scorer.score_resume_against_job` (returns ATSResult.overall_score).
    The previous version imported non-existent `score_match`/`score_ats`, so
    every ats_score silently fell back to 0.
    """
    match_score = int(job.get("match_score") or 0)
    ats_score = 0
    jd = job.get("description") or job.get("job_description") or ""
    title = job.get("title") or ""
    company = job.get("company") or ""
    if not (resume_text or "").strip() or not jd.strip():
        return match_score, ats_score
    try:
        from app.services.match_engine import compute_match_score

        result = await compute_match_score(resume_text, jd, job_title=title)
        match_score = int(getattr(result, "overall_match_score", match_score) or match_score)
    except Exception as exc:
        log.debug("match score failed: %s", exc)
    try:
        from app.services.ats_scorer import score_resume_against_job

        result = await score_resume_against_job(resume_text, jd, job_title=title, company=company)
        ats_score = int(round(float(getattr(result, "overall_score", 0) or 0)))
    except Exception as exc:
        log.debug("ats score failed: %s", exc)
    return match_score, ats_score


def _deterministic_resume_spec(resume_text: str, profile: dict, job: dict) -> dict:
    """Build a truthful, renderable resume spec when the LLM is unavailable.

    This does not rewrite or invent content. It parses the user's source resume
    and only reorders known skills so JD-relevant evidence appears first.
    """
    from app.services.resume_parser import resume_text_to_json

    parsed = resume_text_to_json(resume_text)
    header = [str(value).strip() for value in (parsed.get("header") or []) if str(value).strip()]
    full_name = str(profile.get("full_name") or profile.get("name") or "").strip()
    if not full_name:
        full_name = " ".join(
            str(profile.get(key) or "").strip()
            for key in ("first_name", "last_name")
        ).strip()
    name = full_name or (header[0] if header else "")

    parsed_contact = parsed.get("contact") or {}
    contact = [
        profile.get("email") or parsed_contact.get("email"),
        profile.get("phone") or parsed_contact.get("phone"),
        profile.get("location") or profile.get("current_location"),
        profile.get("linkedin_url"),
        *(parsed_contact.get("links") or []),
    ]
    contact = list(dict.fromkeys(str(value).strip() for value in contact if str(value or "").strip()))

    jd_lower = str(job.get("description") or job.get("job_description") or "").lower()
    skills = [str(value).strip() for value in (parsed.get("skills") or []) if str(value).strip()]
    skills.sort(key=lambda value: (0 if value.lower() in jd_lower else 1, value.lower()))
    experience = [entry for entry in (parsed.get("experience_details") or []) if isinstance(entry, dict)]
    education = [
        value if isinstance(value, dict) else {"degree": str(value), "institution": "", "location": "", "dates": ""}
        for value in (parsed.get("education") or [])
        if str(value).strip()
    ]
    return {
        "resume": {
            "name": name,
            "contact": contact,
            "summary": str(parsed.get("summary") or "").strip(),
            "skills": [{"category": "Relevant Skills", "items": skills[:40]}] if skills else [],
            "experience": experience,
            "education": education,
            "certifications": [str(value) for value in (parsed.get("certifications") or []) if str(value).strip()],
            "projects": [str(value) for value in (parsed.get("projects") or []) if str(value).strip()],
        }
    }


def _resume_spec_to_text(spec: dict) -> str:
    resume = (spec or {}).get("resume") or spec or {}
    return "\n".join([
        str(resume.get("name") or ""),
        str(resume.get("summary") or ""),
        json.dumps(resume.get("skills") or [], ensure_ascii=False),
        json.dumps(resume.get("experience") or [], ensure_ascii=False),
        json.dumps(resume.get("education") or [], ensure_ascii=False),
        json.dumps(resume.get("certifications") or [], ensure_ascii=False),
        json.dumps(resume.get("projects") or [], ensure_ascii=False),
    ])


def _deterministic_cover_letter(spec: dict, job: dict) -> str:
    """Truth-only cover-letter fallback assembled from the parsed resume."""
    resume = (spec or {}).get("resume") or {}
    name = str(resume.get("name") or "").strip()
    title = str(job.get("title") or "this position").strip()
    company = str(job.get("company") or "your organization").strip()
    summary = str(resume.get("summary") or "").strip()
    skills: list[str] = []
    for group in resume.get("skills") or []:
        if isinstance(group, dict):
            skills.extend(str(value).strip() for value in (group.get("items") or []) if str(value).strip())
    jd_lower = str(job.get("description") or job.get("job_description") or "").lower()
    relevant = [skill for skill in skills if skill.lower() in jd_lower][:4] or skills[:4]
    evidence = f" My background includes {', '.join(relevant)}." if relevant else ""
    summary_sentence = f" {summary}" if summary else ""
    return (
        f"Dear Hiring Team,\n\nI am applying for the {title} role at {company}.{evidence}{summary_sentence}\n\n"
        "I would welcome the opportunity to discuss how my documented experience can support the responsibilities of this role. "
        "Thank you for your time and consideration.\n\nSincerely,\n"
        f"{name}"
    ).strip()


async def run_tailoring(
    *,
    uid: str,
    job: dict,
    profile: dict,
    resume_id: Optional[str],
    generate_cover_letter: bool,
    store=None,
    resume_text: str = "",
) -> dict:
    """Entry point injected into the orchestrator as `tailor_fn`.

    `store` (optional) supplies resume text + tailored-doc caching in
    production. In tests it can be omitted and `resume_text` passed directly.
    """
    company = job.get("company") or ""
    title = job.get("title") or ""
    jd = job.get("description") or job.get("job_description") or ""

    # Resolve base resume text.
    if not resume_text and store is not None:
        try:
            resume_text = store.get_resume_text(uid, resume_id) or ""  # type: ignore
        except Exception as exc:
            log.debug("resume text lookup failed: %s", exc)

    position_key = str(
        job.get("id")
        or job.get("job_id")
        or job.get("external_id")
        or title
    )

    # Cache hit? Reuse only for this exact user/company/position.
    if store is not None:
        try:
            cached = store.get_tailored_docs(uid, company, position_key)  # type: ignore
            cache_has_cover = bool(cached and (cached.get("cover_letter_url") or cached.get("cover_letter")))
            if (
                cached
                and cached.get("pipeline_version") == TAILORING_PIPELINE_VERSION
                and cached.get("resume_url")
                and (not generate_cover_letter or cache_has_cover)
            ):
                log.info("tailoring cache hit for %s/%s", uid, company)
                return cached
        except Exception:
            pass

    jd_signals = extract_jd_signals(job)
    base_match_score, base_ats_score = await _score(resume_text, job)
    match_score, ats_score = base_match_score, base_ats_score

    resume_url: Optional[str] = None
    cover_letter_url: Optional[str] = None
    documents: dict = {}
    diff: Optional[dict] = None
    cover_text: Optional[str] = None
    spec: Optional[dict] = None
    tailoring_method = "none"

    # OpenClaw is an optional, private service boundary. It is never hosted in
    # the API process; failure or an invalid truth-grounded response falls
    # through to the established LLM/deterministic pipeline.
    try:
        from app.services.apply.openclaw_tailor import tailor_with_openclaw

        openclaw_result = await tailor_with_openclaw(
            resume_text=resume_text,
            job=job,
            profile=profile,
        )
        if openclaw_result:
            spec = openclaw_result["resume_spec"]
            cover_text = openclaw_result.get("cover_letter") or None
            tailoring_method = "openclaw"
    except Exception as exc:
        log.warning("OpenClaw integration skipped: %s", exc)

    try:
        from app.services.resume_tailor_llm import tailor_resume

        spec = spec or await tailor_resume(
            resume_text=resume_text,
            job_title=title,
            job_company=company,
            job_description=jd,
            work_auth=str(profile.get("visa_status") or profile.get("work_authorization") or ""),
        )
        if spec and tailoring_method == "none":
            tailoring_method = "llm"
    except Exception as exc:
        log.warning("tailoring LLM step failed: %s", exc)

    if not spec and resume_text.strip():
        try:
            spec = _deterministic_resume_spec(resume_text, profile, job)
            tailoring_method = "deterministic"
        except Exception as exc:
            log.warning("deterministic tailoring fallback failed: %s", exc)

    if spec:
        if generate_cover_letter and not cover_text:
            try:
                from app.services.resume_tailor_llm import generate_cover_letter as _gen_cover

                cover_text = await _gen_cover(
                    resume_text=resume_text,
                    job_title=title,
                    job_company=company,
                    job_description=jd,
                    candidate_name=str((spec.get("resume") or {}).get("name") or ""),
                    work_auth=str(profile.get("visa_status") or profile.get("work_authorization") or ""),
                )
            except Exception as exc:
                log.debug("cover-letter generation skipped: %s", exc)
            if not cover_text:
                cover_text = _deterministic_cover_letter(spec, job)

        tailored_text = _resume_spec_to_text(spec)
        if tailored_text.strip():
            match_score, ats_score = await _score(tailored_text, job)
        diff = {
            "tailored_spec": spec,
            "tailoring_method": tailoring_method,
            "score_before": {"match": base_match_score, "ats": base_ats_score},
            "score_after": {"match": match_score, "ats": ats_score},
        }
        if cover_text:
            diff["cover_letter"] = cover_text

        if store is not None:
            try:
                urls = store.render_and_store_tailored(  # type: ignore
                    uid,
                    company,
                    spec,
                    cover_text,
                    position_key,
                )
                resume_url = urls.get("resume_url")
                cover_letter_url = urls.get("cover_letter_url")
                documents = {k: v for k, v in urls.items() if v}
            except Exception as exc:
                log.debug("tailored render/store skipped: %s", exc)

    result = {
        "user_id": uid,
        "pipeline_version": TAILORING_PIPELINE_VERSION,
        "company": company,
        "resume_url": resume_url,
        "cover_letter_url": cover_letter_url,
        "documents": documents,
        "cover_letter": cover_text,
        "jd_signals": jd_signals,
        "match_score": match_score,
        "ats_score": ats_score,
        "diff": diff,
    }
    if store is not None:
        try:
            store.save_tailored_docs(uid, company, result, position_key)  # type: ignore
        except Exception:
            pass
    return result
