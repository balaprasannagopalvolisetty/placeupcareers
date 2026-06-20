"""Advanced ATS / match analysis (deterministic, local — no LLM cost).

Recruiter-grade analysis for the redesigned UI and the resume tailor:

  * an overall match score blending weighted-keyword coverage and TF cosine
    similarity (semantic overlap),
  * a weighted breakdown that sums to 100 (keyword match, bullet quality,
    section completeness, formatting, impact quantification),
  * matched / missing keywords grouped by category, each missing keyword ranked
    High / Medium / Low by JD frequency + requirement-section placement,
  * accomplishment-bullet feedback (passive voice, weak verbs, missing
    quantification) with a concrete rewrite for each — never the candidate's
    name, contact line, section headers, skill lists, or sentence fragments.

The keyword engine is DOMAIN-AGNOSTIC: it surfaces real hard skills for power
systems (PLC, HMI, switchgear), security (SIEM, EDR, MITRE), or software alike
by combining acronym detection, a multi-domain hard-skill lexicon, and known
phrases — then filters generic filler ("data", "back up", "go", "company wide").
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
    "smartsheet", "excel", "google sheets", "sharepoint", "vmware", "proxmox", "intune",
    "sentinelone", "microsoft defender", "active directory", "powershell", "factorytalk",
    "wonderware", "rockwell", "allen-bradley", "modicon", "siemens",
}
_METHODOLOGIES = {
    "agile", "scrum", "kanban", "waterfall", "cicd", "tdd", "bdd", "devops",
    "devsecops", "mlops", "sre", "microservices", "rest", "restful", "graphql", "grpc", "oop",
    "design patterns", "pair programming", "code review", "sprint planning",
    "continuous integration", "continuous deployment", "infrastructure as code", "ci/cd",
    "root cause analysis", "incident response", "change management",
}
_CERTIFICATIONS = {
    "aws certified", "aws solutions architect", "azure certified", "gcp certified",
    "cissp", "ccsp", "security+", "comptia", "network+", "ceh", "oscp", "pmp", "csm",
    "ccna", "cka", "ckad", "cisa", "cism", "cpa", "six sigma", "itil", "togaf",
    "cysa+", "gsec", "sc-200", "splunk certified", "pentest+",
}
_SOFT_SKILLS = {
    "communication", "leadership", "collaboration", "teamwork", "problem solving",
    "critical thinking", "adaptability", "time management", "stakeholder management",
    "mentoring", "mentorship", "cross-functional", "presentation", "negotiation",
    "ownership", "attention to detail", "creativity", "analytical", "customer focus",
    "decision making", "conflict resolution",
}

# Multi-domain hard skills BEYOND the software-centric TECH_SKILLS dictionary, so
# the engine recognises real keywords for engineering, IT, security, ops, etc.
_EXTRA_HARD_SKILLS = {
    # power / controls / electrical engineering
    "plc", "hmi", "scada", "switchgear", "generator", "automation", "controls",
    "commissioning", "schematics", "blueprints", "paralleling", "transfer switch",
    "low voltage", "medium voltage", "power systems", "electrical", "firmware",
    "instrumentation", "distributed control systems", "vfd", "relay", "circuit",
    # IT / infra / security
    "networking", "firewall", "firewalls", "vlan", "dns", "dhcp", "vpn", "tcp/ip",
    "windows server", "group policy", "endpoint", "siem", "edr", "soc", "mitre att&ck",
    "owasp", "vulnerability management", "penetration testing", "threat detection",
    "phishing", "incident analysis", "log analysis", "cvss", "rbac", "mfa", "sso",
    "virtualization", "imaging", "autopilot", "mdm", "patch management",
    "identity", "access management", "entra id", "azure ad", "microsoft 365",
    # data / general
    "data analysis", "data engineering", "reporting", "dashboards", "etl",
    "troubleshooting", "technical support", "root cause", "documentation",
    "computer vision", "machine learning", "automated testing",
}

# Variant → canonical, so resume and JD match despite different spellings.
_ALIASES = {
    "k8s": "kubernetes", "js": "javascript", "ts": "typescript", "py": "python",
    "postgres": "postgresql", "pg": "postgresql",
    "ml": "machine learning", "dl": "deep learning",
    "nlp": "natural language processing", "ci/cd": "cicd", "ci cd": "cicd",
    "node": "node.js", "nodejs": "node.js", "reactjs": "react", "react.js": "react",
    "rest api": "rest", "restful": "rest",
    "k8": "kubernetes", "tf": "terraform", "gh actions": "github actions",
    "problem-solving": "problem solving", "ci-cd": "cicd",
    "active directory": "active directory", "ad": "active directory",
    "allen bradley": "allen-bradley", "att&ck": "mitre att&ck",
    "transfer switches": "transfer switch", "hmis": "hmi", "plcs": "plc",
    "firewalls": "firewall", "controls systems": "controls",
}

# Multi-word skills worth matching as a unit.
_KNOWN_PHRASES = {
    "machine learning", "deep learning", "natural language processing", "computer vision",
    "data analysis", "data engineering", "data science", "incident response",
    "threat intelligence", "vulnerability management", "project management",
    "product management", "continuous integration", "continuous deployment",
    "infrastructure as code", "object oriented programming", "test driven development",
    "google cloud", "power bi", "burp suite", "github actions", "design patterns",
    "stakeholder management", "cross-functional", "code review", "root cause analysis",
    "active directory", "group policy", "power systems", "transfer switch",
    "windows server", "patch management", "technical support", "log analysis",
    "distributed control systems", "low voltage", "medium voltage", "access management",
} | {p for p in (_TOOLS_PLATFORMS | _METHODOLOGIES | _CERTIFICATIONS | _SOFT_SKILLS | _EXTRA_HARD_SKILLS) if " " in p}

# Full hard-skill lexicon used for recognition.
_HARD_SKILLS = {s.lower() for s in (TECH_SKILLS | _TOOLS_PLATFORMS | _METHODOLOGIES | _CERTIFICATIONS | _EXTRA_HARD_SKILLS)}

# Generic words that are NOT meaningful resume/JD keywords. These used to leak
# through frequency counting and made the analysis look unintelligent
# ("back up · High", "data · High", "go · High", "company wide · High").
_NOISE_TERMS = {
    "data", "back up", "backup", "go", "company wide", "company-wide", "team", "teams",
    "work", "working", "experience", "knowledge", "ability", "system", "systems",
    "end user", "end users", "stakeholder", "stakeholders", "business", "process",
    "processes", "quality", "field", "role", "position", "opportunity", "requirement",
    "requirements", "responsibility", "responsibilities", "skill", "skills", "support",
    "user", "users", "customer", "customers", "service", "services", "solution",
    "solutions", "project", "projects", "tool", "tools", "environment", "environments",
    "standard", "standards", "needs", "related", "various", "including", "across",
    "using", "use", "new", "good", "strong", "level", "based", "etc", "per", "via",
    "company", "organization", "operations", "operational", "engineer", "engineering",
    "development", "developer", "design", "designing", "implementation", "management",
    "analysis", "results", "result", "best practices", "day", "year", "years",
}

# All-caps tokens that are NOT skills (geography, benefits, legal, degree codes).
_ACRONYM_STOP = {
    "us", "usa", "u.s", "eeo", "ada", "pto", "fsa", "hsa", "dcfsa", "401k", "id",
    "bsee", "bseet", "cat", "epd", "aes", "ok", "hr", "ceo", "cto", "cfo", "vp",
    "ii", "iii", "iv", "i", "a", "the", "and", "or", "of", "to", "in", "on", "at",
    "msee", "bs", "ms", "ba", "mba", "phd", "gpa", "am", "pm", "est", "pst", "cst",
    "faq", "tbd", "n/a", "na", "etc", "inc", "llc", "ltd", "jr", "sr",
}

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
# Broader action verbs so well-written bullets are recognised as accomplishment
# statements (and the name / summary / skills lines are NOT).
_EXTRA_VERBS = (
    "focused", "strengthened", "sustained", "supported", "replicated", "hardened",
    "authored", "provisioned", "administered", "mapped", "validated", "identified",
    "assessed", "documented", "configured", "maintained", "monitored", "analyzed",
    "investigated", "triaged", "remediated", "collaborated", "coordinated", "executed",
    "performed", "conducted", "created", "established", "enabled", "enhanced",
    "integrated", "managed", "oversaw", "partnered", "prepared", "processed", "produced",
    "programmed", "reviewed", "supervised", "tested", "tracked", "trained", "translated",
    "troubleshot", "researched", "presented", "facilitated", "consolidated", "standardized",
    "modernized", "refactored", "diagnosed", "installed", "upgraded", "automating",
)
_ALL_VERBS = set(_STRONG_VERBS) | set(_EXTRA_VERBS)

_QUANT_RE = re.compile(r"\d+\s?%|\$\s?\d+|\b\d+x\b|\bby\s+\d+|\b\d+\s?(?:k|m|b|bn)\b|\b\d{2,}\b")
_SECTION_HEADERS = {
    "experience", "work experience", "professional experience", "education", "skills",
    "technical skills", "projects", "certifications", "summary", "professional summary",
    "objective", "achievements", "awards", "publications", "contact", "references",
    "interests", "security research & community", "security research and community",
}
_BULLET_GLYPHS = "•‣◦▪●○·*"


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


def _term_present(term: str, low_padded: str) -> bool:
    """Word-boundary-ish presence test against a space-padded lowered text."""
    if re.search(r"[ \-/+.#&]", term):
        return f" {term} " in low_padded or term in low_padded
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", low_padded) is not None


def _acronyms(text: str) -> set[str]:
    """Real skill acronyms (PLC, HMI, ATS, SIEM, EDR, GPO, RBAC, CI/CD…)."""
    out: set[str] = set()
    for m in re.findall(r"\b[A-Z][A-Za-z0-9]{1,5}(?:/[A-Za-z0-9]{1,5})?\b", text or ""):
        a = m.strip()
        low = a.lower()
        if low in _ACRONYM_STOP or a.isdigit() or low in _NOISE_TERMS:
            continue
        # Must contain at least one uppercase letter beyond the first to be an
        # acronym (filters ordinary Capitalised words like "Power", "Remote").
        if not re.search(r"[A-Z0-9].*[A-Z0-9]", a) and "/" not in a:
            continue
        out.add(low)
    return out


def _extract_terms(text: str) -> set[str]:
    """Normalised hard skills + known phrases + acronyms — generic filler removed."""
    low = " " + clean_text(text).lower() + " "
    terms: set[str] = set()
    for ph in _KNOWN_PHRASES:
        if _term_present(ph, low):
            terms.add(_normalize(ph))
    for sk in _HARD_SKILLS:
        if _term_present(sk, low):
            terms.add(_normalize(sk))
    for sk in extract_skills_from_text(text):
        n = _normalize(sk)
        if n in _HARD_SKILLS or n in _KNOWN_PHRASES or " " in n:
            terms.add(n)
    for ac in _acronyms(text):
        terms.add(_normalize(ac))
    # Drop generic filler and trivially short tokens.
    return {t for t in terms if t and t not in _NOISE_TERMS and len(t) >= 2}


def _jd_importance(jd_text: str, terms: set[str]) -> dict[str, str]:
    """Rank each JD term High/Medium/Low by frequency + requirement-section hits."""
    low = clean_text(jd_text).lower()
    req_zone = ""
    m = re.search(r"(requirements?|qualifications?|must have|what you'll need|what you will have|required|what they need)(.*)", low, re.S)
    if m:
        req_zone = m.group(2)[:2500]
    out: dict[str, str] = {}
    for t in terms:
        freq = low.count(t)
        in_req = t in req_zone
        hard = _normalize(t) in _HARD_SKILLS or _category_of(t) in ("Tools & Platforms", "Certifications") or len(t) <= 5
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
    """Return real resume bullets, REJOINING wrapped continuation lines.

    PDF text extraction breaks one long bullet across several physical lines;
    only the first carries the bullet glyph. We reattach the wrapped remainder
    so feedback critiques a COMPLETE sentence, never a fragment. Names, contact
    lines, section headers, date headers and skill-list rows are excluded.
    """
    _CONT = re.compile(r"^(and|or|nor|but|then|the|a|an|to|with|within|across|including|by|for|in|of|on|that|which|who|whose|using|via|through|from|as|at|into|while|where|when|so)\b", re.I)

    def _is_break(s: str) -> bool:
        low = s.lower().strip(": ").strip()
        if low in _SECTION_HEADERS:
            return True
        if " | " in s:
            return True
        if re.search(r"\b(19|20)\d{2}\b\s*[-–—]\s*(present|current|(19|20)\d{2})", low):
            return True
        if "@" in s or re.search(r"https?://|linkedin\.com|github\.com|\+?\d[\d \-()]{7,}", s):
            return True
        return False

    logical: list[str] = []
    cur: Optional[str] = None
    for raw in (resume_text or "").splitlines():
        s = raw.strip()
        if not s:
            if cur:
                logical.append(cur)
                cur = None
            continue
        if s[0] in _BULLET_GLYPHS:
            if cur:
                logical.append(cur)
            cur = re.sub(r"^[•‣◦▪●○·\-\*–—\s]+", "", s).strip()
            continue
        if _is_break(s):
            if cur:
                logical.append(cur)
                cur = None
            logical.append(s)
            continue
        if cur is not None and (s[0].islower() or _CONT.match(s)):
            cur = (cur + " " + s).strip()
            continue
        if cur:
            logical.append(cur)
            cur = None
        logical.append(s)
    if cur:
        logical.append(cur)

    out: list[str] = []
    seen: set[str] = set()
    for s in logical:
        low = s.lower().strip(":").strip()
        if not (24 <= len(s) <= 500) or not re.search(r"[a-zA-Z]", s):
            continue
        if low in _SECTION_HEADERS:
            continue
        if "@" in s or re.search(r"https?://|linkedin\.com|github\.com|\+?\d[\d \-()]{7,}", s):
            continue
        first = (low.split() or [""])[0].strip(":,.")
        if ":" in s[:42] and s.count(",") >= 2 and first not in _ALL_VERBS:
            continue
        if s.lower() in seen:
            continue
        seen.add(s.lower())
        out.append(s)
    return out


def _accomplishment_bullets(resume_text: str) -> list[str]:
    """Bullets that are genuine accomplishment statements (start with an action
    verb). Critiquing only these keeps feedback off names, certs, and skills."""
    out: list[str] = []
    for b in _split_bullets(resume_text):
        first = (b.lower().split() or [""])[0].strip(":,.")
        if first in _ALL_VERBS:
            out.append(b)
    return out


def detect_red_flags(resume_text: str, max_flags: int = 8) -> list[dict]:
    flags: list[dict] = []
    for bullet in _accomplishment_bullets(resume_text):
        low = bullet.lower()
        opener = next((w for w in _WEAK_OPENERS if low.startswith(w) or f" {w} " in f" {low} "), None)
        has_quant = bool(_QUANT_RE.search(bullet))
        has_strong = (low.split() or [""])[0].strip(":,.") in _STRONG_VERBS or any(re.search(rf"\b{v}\b", low) for v in _STRONG_VERBS)
        first_person = bool(re.match(r"^(i|my|we|our)\b", low))
        overlong = len(bullet.split()) > 46
        if opener:
            category, impact = "Passive voice / weak verb", "High"
        elif first_person:
            category, impact = "First-person phrasing", "Medium"
        elif not has_quant:
            category, impact = "Add a measurable result", "Medium"
        elif overlong:
            category, impact = "Bullet too long", "Low"
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
    has_verb_start = (core.lower().split() or [""])[0] in _ALL_VERBS
    if has_quant:
        return core if has_verb_start else f"Delivered {core}".strip()
    tail = " — add a measurable result (e.g. % improvement, $ saved, time reduced)"
    return (core if has_verb_start else f"Delivered {core}") + tail


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
    if len(_accomplishment_bullets(resume_text)) >= 5:
        score += 2.0
    return min(10.0, score)


def _impact_score(resume_text: str) -> float:
    bullets = _accomplishment_bullets(resume_text)
    if not bullets:
        return 0.0
    quantified = sum(1 for b in bullets if _QUANT_RE.search(b))
    ratio = quantified / max(1, len(bullets))
    return round(min(15.0, ratio * 15.0 + min(quantified, 3)), 1)


def _bullet_quality(resume_text: str) -> float:
    bullets = _accomplishment_bullets(resume_text)
    if not bullets:
        return 0.0
    strong = 0
    for b in bullets:
        low = b.lower()
        if any(re.search(rf"\b{v}\b", low) for v in _ALL_VERBS) and not any(low.startswith(w) for w in _WEAK_OPENERS):
            strong += 1
    return round(min(25.0, (strong / max(1, len(bullets))) * 25.0), 1)


def analyze(resume_text: str, job_description: str, *, job_title: str = "", company: str = "") -> dict:
    resume_text = resume_text or ""
    jd = "\n".join(p for p in [job_title, job_description] if p)
    resume_low = clean_text(resume_text).lower()

    jd_terms = _extract_terms(jd)
    resume_terms = _extract_terms(resume_text)
    matched = sorted(jd_terms & resume_terms)
    missing = sorted(jd_terms - resume_terms)

    coverage = (len(matched) / len(jd_terms) * 100.0) if jd_terms else 0.0
    importance = _jd_importance(jd, jd_terms)
    w = {"High": 3.0, "Medium": 2.0, "Low": 1.0}
    tot_w = sum(w[importance[t]] for t in jd_terms) or 1.0
    matched_w = sum(w[importance[t]] for t in matched)
    weighted_coverage = matched_w / tot_w * 100.0
    cosine = _tf_cosine(resume_text, jd) * 100.0
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

    missing_ranked = sorted(missing, key=lambda t: {"High": 0, "Medium": 1, "Low": 2}.get(importance.get(t, "Low"), 3))[:20]
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
