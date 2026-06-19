"""Advanced ATS / match analysis (deterministic, local — no LLM cost).

Produces the recruiter-grade analysis the redesigned UI and the resume tailor
consume:

  * an overall match score blending keyword coverage, weighted-keyword
    importance, and TF cosine similarity (semantic overlap),
  * a weighted breakdown that sums to 100 (keyword match, bullet quality,
    section completeness, formatting, impact quantification),
  * matched / missing keywords grouped by category, each missing keyword ranked
    by impact (High / Medium / Low) from JD frequency + section placement,
  * red-flag bullets (passive voice, weak verbs, missing quantification,
    first-person, overlong) with a concrete rewrite for each.

Robustness features: alias normalization (k8s→kubernetes, js→javascript…),
multi-word skill phrase matching ("machine learning", "incident response"), and
JD requirement-section weighting.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional

from app.utils.text_processing import (
    TECH_SKILLS,
    clean_text,
    compute_keyword_overlap,
    extract_relevant_keywords,
    extract_skills_from_text,
)

# ── Category dictionaries ──────────────────────────────────────────────────
_TOOLS_PLATFORMS = {
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform",
    "ansible", "jenkins", "github", "github actions", "gitlab", "bitbucket", "jira",
    "confluence", "datadog", "grafana", "prometheus", "splunk", "kafka", "rabbitmq",
    "redis", "elasticsearch", "snowflake", "databricks", "airflow", "tableau", "power bi",
    "figma", "vs code", "linux", "unix", "bash", "nginx", "vercel", "netlify", "cloudflare",
    "postman", "salesforce", "servicenow", "sentinel", "qradar", "crowdstrike", "nessus",
    "qualys", "wireshark", "burp suite", "metasploit", "nmap", "jupyter", "spark", "hadoop",
}
_METHODOLOGIES = {
    "agile", "scrum", "kanban", "waterfall", "cicd", "tdd", "bdd", "devops",
    "devsecops", "mlops", "sre", "microservices", "rest", "restful", "graphql", "grpc", "oop",
    "design patterns", "pair programming", "code review", "sprint planning",
    "continuous integration", "continuous deployment", "infrastructure as code", "ci/cd",
}
_CERTIFICATIONS = {
    "aws certified", "aws solutions architect", "azure certified", "gcp certified",
    "cissp", "ccsp", "security+", "comptia", "network+", "ceh", "oscp", "pmp", "csm",
    "ccna", "cka", "ckad", "cisa", "cism", "cpa", "six sigma", "itil", "togaf",
    "cysa+", "gsec", "sc-200", "splunk certified",
}
_SOFT_SKILLS = {
    "communication", "leadership", "collaboration", "teamwork", "problem solving",
    "critical thinking", "adaptability", "time management", "stakeholder management",
    "mentoring", "mentorship", "cross-functional", "presentation", "negotiation",
    "ownership", "attention to detail", "creativity", "analytical", "customer focus",
    "decision making", "conflict resolution",
}

# Variant → canonical, so resume and JD match despite different spellings.
_ALIASES = {
    "k8s": "kubernetes", "js": "javascript", "ts": "typescript", "py": "python",
    "gcp": "google cloud", "postgres": "postgresql", "pg": "postgresql",
    "ml": "machine learning", "ai": "artificial intelligence", "dl": "deep learning",
    "nlp": "natural language processing", "ci/cd": "cicd", "ci cd": "cicd",
    "node": "node.js", "nodejs": "node.js", "reactjs": "react", "react.js": "react",
    "rest api": "rest", "restful": "rest", "oop": "object oriented programming",
    "k8": "kubernetes", "tf": "terraform", "gh actions": "github actions",
    "problem-solving": "problem solving", "ci-cd": "cicd",
}

# Multi-word skills worth matching as a unit.
_KNOWN_PHRASES = {
    "machine learning", "deep learning", "natural language processing", "computer vision",
    "data analysis", "data engineering", "data science", "incident response",
    "threat intelligence", "vulnerability management", "project management",
    "product management", "continuous integration", "continuous deployment",
    "infrastructure as code", "object oriented programming", "test driven development",
    "google cloud", "power bi", "burp suite", "github actions", "design patterns",
    "rest api", "stakeholder management", "cross-functional", "code review",
} | {p for p in (_TOOLS_PLATFORMS | _METHODOLOGIES | _CERTIFICATIONS | _SOFT_SKILLS) if " " in p}

_WEAK_OPENERS = (
    "responsible for", "worked on", "helped with", "assisted with", "involved in",
    "duties included", "tasked with", "in charge of", "participated in", "handled",
    "worked with", "was part of", "responsibilities included", "good at", "familiar with",
    "experience with", "knowledge of",
)
_STRONG_VERBS = (
    "led", "built", "designed", "architected", "implemented", "developed", "launched",
    "automated", "migrated", "optimized", "reduced", "increased", "improved", "delivered",
    "deployed", "secured", "resolved", "streamlined", "mentored", "spearheaded", "drove",
    "owned", "scaled", "engineered", "shipped", "accelerated", "cut", "boosted", "generated",
    "negotiated", "orchestrated", "pioneered", "transformed", "championed",
)
_QUANT_RE = re.compile(r"\d+\s?%|\$\s?\d+|\b\d+x\b|\bby\s+\d+|\b\d+\s?(?:k|m|b|bn)\b|\b\d{2,}\b")
_SECTION_HEADERS = {
    "experience", "work experience", "professional experience", "education", "skills",
    "technical skills", "projects", "certifications", "summary", "professional summary",
    "objective", "achievements", "awards", "publications", "contact", "references", "interests",
}


def _normalize(term: str) -> str:
    t = (term or "").strip().lower()
    return _ALIASES.get(t, t)


def _category_of(term: str) -> str:
    t = _normalize(term)
    if any(c in t for c in _CERTIFICATIONS):
        return "Certifications"
    if t in _TOOLS_PLATFORMS:
        return "Tools & Platforms"
    if t in _METHODOLOGIES:
        return "Methodologies"
    if t in _SOFT_SKILLS:
        return "Soft Skills"
    return "Technical Skills"


def categorize_keywords(keywords: list[str]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {
        "Technical Skills": [], "Tools & Platforms": [], "Methodologies": [],
        "Certifications": [], "Soft Skills": [],
    }
    seen: set[str] = set()
    for kw in keywords:
        k = (kw or "").strip()
        n = _normalize(k)
        if not k or n in seen:
            continue
        seen.add(n)
        buckets[_category_of(k)].append(k)
    return {c: items for c, items in buckets.items() if items}


def _extract_terms(text: str) -> set[str]:
    """Normalized skills + known phrases + clean single keywords from text."""
    low = " " + clean_text(text).lower() + " "
    terms: set[str] = set()
    for ph in _KNOWN_PHRASES:
        if f" {ph} " in low or ph in low:
            terms.add(_normalize(ph))
    for sk in extract_skills_from_text(text):
        terms.add(_normalize(sk))
    for kw in extract_relevant_keywords(text, top_n=50):
        if " " not in kw and len(kw) >= 2:
            terms.add(_normalize(kw))
    return terms


def _jd_importance(jd_text: str, terms: set[str]) -> dict[str, str]:
    """Rank each JD term High/Medium/Low by frequency + requirement-section hits."""
    low = clean_text(jd_text).lower()
    req_zone = ""
    m = re.search(r"(requirements?|qualifications?|must have|what you'll need|required)(.*)", low, re.S)
    if m:
        req_zone = m.group(2)[:1500]
    out: dict[str, str] = {}
    for t in terms:
        freq = low.count(t)
        in_req = t in req_zone
        hard = _normalize(t) in TECH_SKILLS or _category_of(t) in ("Tools & Platforms", "Certifications")
        if (freq >= 2 and hard) or (in_req and hard):
            out[t] = "High"
        elif freq >= 2 or in_req or hard:
            out[t] = "Medium"
        else:
            out[t] = "Low"
    return out


def _tf_cosine(a: str, b: str) -> float:
    """Bag-of-words TF cosine similarity (cheap semantic overlap signal)."""
    def vec(t: str) -> Counter:
        toks = [w for w in re.findall(r"[a-z0-9+.#]{2,}", clean_text(t).lower())]
        return Counter(toks)
    va, vb = vec(a), vec(b)
    if not va or not vb:
        return 0.0
    common = set(va) & set(vb)
    dot = sum(va[w] * vb[w] for w in common)
    na = math.sqrt(sum(v * v for v in va.values()))
    nb = math.sqrt(sum(v * v for v in vb.values()))
    return (dot / (na * nb)) if na and nb else 0.0


def _split_bullets(resume_text: str) -> list[str]:
    lines = re.split(r"[\n\r]+|(?<=[.;])\s+(?=[A-Z])", resume_text or "")
    out: list[str] = []
    for line in lines:
        s = re.sub(r"^[•‣◦\-\*–—\s]+", "", line).strip()
        low = s.lower().strip(":").strip()
        if not (24 <= len(s) <= 320) or not re.search(r"[a-zA-Z]", s):
            continue
        if low in _SECTION_HEADERS:
            continue
        if "@" in s or re.search(r"https?://|linkedin\.com|github\.com|\+?\d[\d \-()]{7,}", s):
            continue
        if s.count(",") >= 3 and not any(re.search(rf"\b{v}\b", low) for v in _STRONG_VERBS):
            continue
        if len(s.split()) <= 6 and s == s.title() and not any(re.search(rf"\b{v}\b", low) for v in _STRONG_VERBS):
            continue
        out.append(s)
    return out


def detect_red_flags(resume_text: str, max_flags: int = 10) -> list[dict]:
    flags: list[dict] = []
    for bullet in _split_bullets(resume_text):
        low = bullet.lower()
        opener = next((w for w in _WEAK_OPENERS if low.startswith(w) or f" {w} " in f" {low} "), None)
        has_quant = bool(_QUANT_RE.search(bullet))
        has_strong = any(re.search(rf"\b{v}\b", low) for v in _STRONG_VERBS)
        first_person = bool(re.match(r"^(i|my|we|our)\b", low))
        overlong = len(bullet.split()) > 42
        if opener:
            category, impact = "Passive voice / weak verb", "High"
        elif first_person:
            category, impact = "First-person phrasing", "Medium"
        elif not has_quant and not has_strong:
            category, impact = "Missing quantification", "High"
        elif overlong:
            category, impact = "Bullet too long", "Low"
        elif not has_quant:
            category, impact = "Add a measurable result", "Medium"
        else:
            continue
        core = bullet
        if opener:
            core = re.sub(re.escape(opener), "", bullet, count=1, flags=re.I).strip(" ,.-")
        if first_person:
            core = re.sub(r"^(i|my|we|our)\b\s*", "", bullet, flags=re.I).strip()
        flags.append({
            "original": bullet,
            "suggestion": _rewrite(core, has_quant),
            "category": category,
            "impact": impact,
        })
        if len(flags) >= max_flags:
            break
    order = {"High": 0, "Medium": 1, "Low": 2}
    flags.sort(key=lambda f: order.get(f["impact"], 3))
    return flags


def _rewrite(core: str, has_quant: bool) -> str:
    verb = "Led" if re.search(r"\bteam|people|engineers|developers|staff\b", core, re.I) else "Delivered"
    if has_quant:
        return f"{verb} {core}".strip()
    return f"{verb} {core} — add a measurable result (e.g. % improvement, $ saved, time reduced)".strip()


def _section_completeness(resume_low: str) -> tuple[float, int]:
    sections = ("experience", "education", "skills", "projects", "certifications", "summary")
    hits = sum(1 for s in sections if re.search(rf"\b{s}\b", resume_low))
    return min(15.0, hits * 2.6), hits


def _formatting_score(resume_text: str, resume_low: str) -> float:
    score = 4.0
    if re.search(r"[a-z0-9._-]+@[a-z0-9.-]+\.[a-z]{2,}", resume_low):
        score += 2.0
    if re.search(r"\b(github\.com|linkedin\.com|gitlab\.com|portfolio)\b", resume_low):
        score += 2.0
    if len(_split_bullets(resume_text)) >= 5:
        score += 2.0
    return min(10.0, score)


def _impact_score(resume_text: str) -> float:
    metrics = len(re.findall(r"\d+\s?%|\$\s?\d+[kKmMbB]?|\b\d+x\b|\bby\s+\d+|team of \d+|reduced \d+|increased \d+|saved \d+", resume_text or ""))
    return min(15.0, metrics * 2.5)


def _bullet_quality(resume_text: str) -> float:
    bullets = _split_bullets(resume_text)
    if not bullets:
        return 0.0
    strong = 0
    for b in bullets:
        low = b.lower()
        if any(re.search(rf"\b{v}\b", low) for v in _STRONG_VERBS) and not any(low.startswith(w) for w in _WEAK_OPENERS):
            strong += 1
    return round(min(25.0, (strong / max(1, len(bullets))) * 25.0), 1)


def analyze(resume_text: str, job_description: str, *, job_title: str = "", company: str = "") -> dict:
    resume_text = resume_text or ""
    jd = "\n".join(p for p in [job_title, company, job_description] if p)
    resume_low = clean_text(resume_text).lower()

    jd_terms = _extract_terms(jd)
    resume_terms = _extract_terms(resume_text)
    matched = sorted(jd_terms & resume_terms)
    missing = sorted(jd_terms - resume_terms)

    coverage = (len(matched) / len(jd_terms) * 100.0) if jd_terms else 0.0
    importance = _jd_importance(jd, jd_terms)
    # Weighted coverage: High-impact terms count triple, Medium double.
    w = {"High": 3.0, "Medium": 2.0, "Low": 1.0}
    tot_w = sum(w[importance[t]] for t in jd_terms) or 1.0
    matched_w = sum(w[importance[t]] for t in matched)
    weighted_coverage = matched_w / tot_w * 100.0
    cosine = _tf_cosine(resume_text, jd) * 100.0
    # Blended match score: weighted coverage (semantic priority) + raw + cosine.
    match_score = round(weighted_coverage * 0.55 + coverage * 0.2 + cosine * 0.25, 0)

    keyword_match = round(min(35.0, (weighted_coverage / 100.0) * 35.0), 1)
    bullet_quality = _bullet_quality(resume_text)
    section_pts, section_hits = _section_completeness(resume_low)
    formatting = _formatting_score(resume_text, resume_low)
    impact = _impact_score(resume_text)
    overall = round(keyword_match + bullet_quality + section_pts + formatting + impact, 0)

    def _band(pts: float, mx: float) -> str:
        pct = pts / mx if mx else 0
        return "success" if pct >= 0.8 else "warning" if pct >= 0.5 else "danger"

    breakdown = [
        {"label": "Keyword Match", "score": keyword_match, "max": 35, "color": _band(keyword_match, 35)},
        {"label": "Bullet Quality", "score": bullet_quality, "max": 25, "color": _band(bullet_quality, 25)},
        {"label": "Section Completeness", "score": round(section_pts, 1), "max": 15, "color": _band(section_pts, 15)},
        {"label": "Formatting & Structure", "score": round(formatting, 1), "max": 10, "color": _band(formatting, 10)},
        {"label": "Impact Quantification", "score": round(impact, 1), "max": 15, "color": _band(impact, 15)},
    ]

    # Missing keywords carry their impact rank for the UI ("High"/"Medium").
    missing_ranked = sorted(missing, key=lambda t: {"High": 0, "Medium": 1, "Low": 2}.get(importance.get(t, "Low"), 3))[:24]
    missing_with_impact = [{"keyword": t, "impact": importance.get(t, "Low"), "category": _category_of(t)} for t in missing_ranked]

    return {
        "score": round(overall, 0),
        "match_score": match_score,
        "recommendation": ("Strong match" if overall >= 80 else "Good match" if overall >= 60 else "Partial match" if overall >= 40 else "Needs work"),
        "breakdown": breakdown,
        "matched_keywords": categorize_keywords(matched),
        "missing_keywords": categorize_keywords(missing_ranked),
        "missing_with_impact": missing_with_impact,
        "matched_count": len(matched),
        "missing_count": len(missing),
        "coverage_pct": round(coverage, 0),
        "semantic_similarity": round(cosine, 0),
        "red_flags": detect_red_flags(resume_text),
        "sections_found": section_hits,
    }
