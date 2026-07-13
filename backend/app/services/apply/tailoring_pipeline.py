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
from typing import Optional

log = logging.getLogger("placeup.apply.tailor")


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


def _score(resume_text: str, job: dict) -> tuple[int, int]:
    """Return (match_score, ats_score) from the existing scorers."""
    match_score = int(job.get("match_score") or 0)
    ats_score = 0
    jd = job.get("description") or job.get("job_description") or ""
    try:
        from app.services.match_engine import score_match  # type: ignore

        match_score = int(score_match(resume_text, jd) or match_score)  # pragma: no cover
    except Exception:
        pass
    try:
        from app.services.ats_scorer import score_ats  # type: ignore

        ats_score = int(score_ats(resume_text, jd) or 0)  # pragma: no cover
    except Exception:
        pass
    return match_score, ats_score


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

    # Cache hit? Reuse per (user, company).
    if store is not None:
        try:
            cached = store.get_tailored_docs(uid, company)  # type: ignore
            if cached:
                log.info("tailoring cache hit for %s/%s", uid, company)
                return cached
        except Exception:
            pass

    jd_signals = extract_jd_signals(job)
    match_score, ats_score = _score(resume_text, job)

    resume_url: Optional[str] = None
    cover_letter_url: Optional[str] = None
    diff: Optional[dict] = None

    try:
        from app.services.resume_tailor_llm import tailor_resume

        spec = await tailor_resume(
            resume_text=resume_text,
            job_title=title,
            job_company=company,
            job_description=jd,
            work_auth=str(profile.get("visa_status") or profile.get("work_authorization") or ""),
        )
        if spec:
            diff = {"tailored_spec": spec}
            # Rendering to an ATS-safe PDF/DOCX + upload to Cloud Storage is the
            # production step; the store handles persistence and returns URLs.
            if store is not None:
                try:
                    urls = store.render_and_store_tailored(uid, company, spec, generate_cover_letter)  # type: ignore
                    resume_url = urls.get("resume_url")
                    cover_letter_url = urls.get("cover_letter_url")
                except Exception as exc:
                    log.debug("tailored render/store skipped: %s", exc)
    except Exception as exc:
        log.warning("tailoring LLM step failed: %s", exc)

    result = {
        "user_id": uid,
        "company": company,
        "resume_url": resume_url,
        "cover_letter_url": cover_letter_url,
        "jd_signals": jd_signals,
        "match_score": match_score,
        "ats_score": ats_score,
        "diff": diff,
    }
    if store is not None:
        try:
            store.save_tailored_docs(uid, company, result)  # type: ignore
        except Exception:
            pass
    return result
