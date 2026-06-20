"""Optional LLM refine layer for ATS / match analysis.

When an LLM key is configured (OpenRouter free model preferred, else Groq, else
OpenAI) this overlays the deterministic ats_analysis result with a recruiter-
grade pass: cleaner matched / missing keywords, ranked by impact, and concrete
bullet rewrites — copied verbatim from the resume, never fabricated.

It is FULLY OPTIONAL and SAFE:
  * Disabled with ATS_LLM_ENABLED=0 (default "auto" = on when a key exists).
  * Any error (no key, timeout, bad JSON, model refusal) returns the
    deterministic result unchanged — the endpoint never breaks or slows past
    the timeout.
  * Results are cached (content hash) so re-opening a job is instant.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a senior technical recruiter and ATS (applicant tracking system) "
    "specialist. Compare ONE resume to ONE job description and return a precise, "
    "honest assessment. Rules: (1) NEVER invent skills or experience — a matched "
    "keyword MUST literally appear in the resume; (2) missing keywords MUST be "
    "real requirements from the job description that are absent from the resume; "
    "(3) prefer concrete hard skills, tools, certifications and domain terms "
    "(e.g. PLC, HMI, SIEM, Kubernetes, switchgear) over generic words like "
    "'data', 'team', 'support', 'communication'; (4) bullet feedback must quote "
    "the resume bullet VERBATIM in 'original' and give a stronger rewrite. "
    "Return ONLY a JSON object, no prose, with EXACTLY these keys: "
    '{"match_score": <0-100 int>, "verdict": "Strong match|Good match|Partial '
    'match|Needs work", "summary": "<2-3 sentence recruiter take>", '
    '"matched_keywords": ["<skill present in BOTH>", ...], '
    '"missing_keywords": [{"keyword": "<JD skill absent from resume>", "impact": '
    '"High|Medium|Low"}, ...], "bullet_feedback": [{"original": "<verbatim '
    'resume bullet>", "suggestion": "<stronger, quantified rewrite>", "impact": '
    '"High|Medium|Low"}, ...]}'
)


def _provider() -> Optional[tuple[str, str, str, dict]]:
    """(url, api_key, model, extra_headers) for the first configured provider."""
    enabled = os.getenv("ATS_LLM_ENABLED", "auto").strip().lower()
    if enabled in {"0", "false", "off", "no", "disabled"}:
        return None
    if (settings.openrouter_api_key or "").strip():
        model = os.getenv("ATS_LLM_MODEL", "").strip() or "meta-llama/llama-3.3-70b-instruct:free"
        url = settings.openrouter_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "HTTP-Referer": settings.openrouter_referer or "https://placeupcareer.com",
            "X-Title": "PlaceUp ATS",
        }
        return (url, settings.openrouter_api_key.strip(), model, headers)
    if (settings.groq_api_key or "").strip():
        return ("https://api.groq.com/openai/v1/chat/completions", settings.groq_api_key.strip(), settings.llm_model, {})
    if (settings.openai_api_key or "").strip():
        model = os.getenv("ATS_LLM_MODEL", "").strip() or "gpt-4o-mini"
        return ("https://api.openai.com/v1/chat/completions", settings.openai_api_key.strip(), model, {})
    return None


def llm_available() -> bool:
    return _provider() is not None


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.M).strip()
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


async def _call_llm(resume_text: str, jd: str, title: str, company: str, *, timeout: float = 18.0) -> Optional[dict]:
    prov = _provider()
    if not prov:
        return None
    url, key, model, extra_headers = prov
    user = (
        f"JOB TITLE: {title}\nCOMPANY: {company}\n\n"
        f"JOB DESCRIPTION:\n{(jd or '')[:6000]}\n\n"
        f"CANDIDATE RESUME:\n{(resume_text or '')[:6000]}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **extra_headers}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
        logger.warning("ATS LLM call failed; using deterministic analysis: %s", exc)
        return None
    parsed = _extract_json(content)
    return parsed if isinstance(parsed, dict) else None


def _impact(val: object) -> str:
    s = str(val or "Medium").strip().title()
    return s if s in ("High", "Medium", "Low") else "Medium"


def _merge(base: dict, llm: dict) -> dict:
    try:
        from app.services.ats_analysis import _category_of, categorize_keywords

        matched = [str(k).strip() for k in (llm.get("matched_keywords") or []) if str(k).strip()][:40]
        missing: list[tuple[str, str]] = []
        for m in (llm.get("missing_keywords") or []):
            if isinstance(m, dict):
                kw = str(m.get("keyword") or "").strip()
                imp = _impact(m.get("impact"))
            else:
                kw, imp = str(m).strip(), "Medium"
            if kw:
                missing.append((kw, imp))
        missing = missing[:24]

        bullets: list[dict] = []
        for b in (llm.get("bullet_feedback") or [])[:8]:
            if not isinstance(b, dict):
                continue
            orig = str(b.get("original") or "").strip()
            sug = str(b.get("suggestion") or "").strip()
            if not orig or not sug:
                continue
            bullets.append({
                "original": orig[:300],
                "suggestion": sug[:400],
                "category": str(b.get("category") or "Stronger bullet"),
                "impact": _impact(b.get("impact")),
            })

        out = dict(base)
        if matched:
            out["matched_keywords"] = categorize_keywords(matched)
            out["matched_count"] = len(matched)
        if missing:
            out["missing_keywords"] = categorize_keywords([k for k, _ in missing])
            out["missing_with_impact"] = [{"keyword": k, "impact": i, "category": _category_of(k)} for k, i in missing]
            out["missing_count"] = len(missing)
        if bullets:
            out["red_flags"] = bullets
        try:
            llm_score = max(0.0, min(100.0, float(llm.get("match_score"))))
            base_ms = float(base.get("match_score") or 0)
            out["match_score"] = round((base_ms + llm_score) / 2)
        except (TypeError, ValueError):
            pass
        verdict = str(llm.get("verdict") or "").strip()
        if verdict in ("Strong match", "Good match", "Partial match", "Needs work"):
            out["recommendation"] = verdict
        summary = str(llm.get("summary") or "").strip()
        if summary:
            out["summary"] = summary[:600]
        out["analysis_source"] = "llm"
        return out
    except Exception as exc:
        logger.warning("ATS LLM merge failed; using deterministic analysis: %s", exc)
        return base


async def maybe_refine(resume_text: str, job_description: str, job_title: str, company: str, base: dict) -> dict:
    """Overlay the deterministic `base` with an LLM pass when available; else
    return `base` unchanged. Cached by content hash so repeat views are instant."""
    if not _provider():
        return base
    cache_get = cache_set = None
    key = None
    try:
        from app.services.cache import cache_get_json, cache_set_json

        cache_get, cache_set = cache_get_json, cache_set_json
        raw = "||".join([job_title or "", company or "", (job_description or "")[:4000], (resume_text or "")[:4000]])
        key = "atsllm:" + hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()
    except Exception:
        key = None
    if key and cache_get:
        cached = cache_get(key)
        if isinstance(cached, dict):
            return _merge(base, cached)
    llm = await _call_llm(resume_text, job_description, job_title, company)
    if not isinstance(llm, dict):
        return base
    if key and cache_set:
        try:
            cache_set(key, llm, ttl=21600)
        except Exception:
            pass
    return _merge(base, llm)
