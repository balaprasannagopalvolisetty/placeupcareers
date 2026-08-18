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
import time
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
_DASHBOARD_SUMMARY_TTL_SECONDS = 45
_dashboard_summary_cache: dict[str, tuple[float, DashboardSummary]] = {}


def _invalidate_dashboard_summary(user_id: str) -> None:
    _dashboard_summary_cache.pop(user_id, None)


def _invalidate_jobs_context(user_id: str) -> None:
    try:
        from app.api.jobs import invalidate_user_job_caches
        invalidate_user_job_caches(user_id)
    except Exception as exc:  # pragma: no cover - defensive cache cleanup
        log.debug("Jobs cache invalidation skipped for %s: %s", user_id, exc)


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
        country=user.get("country"),
        visa_status=user.get("visa_status"),
        visa_status_other=user.get("visa_status_other"),
        experience_years=user.get("experience_years"),
        current_role=user.get("current_role"),
        current_company=user.get("current_company"),
        plan=user.get("plan") or "Pro",
        summary=user.get("summary"),
        linkedin_url=user.get("linkedin_url"),
        github_url=user.get("github_url"),
        portfolio_url=user.get("portfolio_url"),
        gender=user.get("gender"),
        race_ethnicity=user.get("race_ethnicity"),
        disability_status=user.get("disability_status"),
        veteran_status=user.get("veteran_status"),
        open_to_relocation=user.get("open_to_relocation"),
        authorized_to_work=user.get("authorized_to_work"),
        requires_sponsorship=user.get("requires_sponsorship"),
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
    # Score is computed when the resume is uploaded. Recomputing over full
    # parsed_text on every list read made /dashboard/resumes unnecessarily slow.
    score = int(row.get("score") or 0)
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
        sponsorship_required=bool(raw.get("sponsorship_required", True)),
        english_friendly_only=bool(raw.get("english_friendly_only", True)),
        max_years_required=raw.get("max_years_required", 5),
        target_roles=list(raw.get("target_roles") or [])[:25],
        target_locations=list(raw.get("target_locations") or []),
        target_keywords=list(raw.get("target_keywords") or [])[:80],
        avoid_title_signals=list(raw.get("avoid_title_signals") or [])[:40],
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


def _extract_experience_details(resume_json: dict) -> list[dict]:
    raw = resume_json.get("experience_details") if isinstance(resume_json, dict) else None
    out: list[dict] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            company = str(item.get("company") or "").strip()
            title = str(item.get("title") or "").strip()
            duration = str(item.get("duration") or item.get("dates") or "").strip()
            location = str(item.get("location") or "").strip()
            bullets = [str(v).strip() for v in (item.get("bullets") or []) if str(v).strip()]
            if company or title:
                out.append({
                    "company": company,
                    "title": title,
                    "duration": duration,
                    "location": location,
                    "bullets": bullets[:5],
                })
            if len(out) >= 8:
                break
    return out


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


# ─── Professional keyword display casing ──────────────────────────────
# Keyword matching normalizes terms to lowercase and de-pluralizes them
# (e.g. "kubernetes" -> "kubernete"). This layer restores the casing a
# recruiter expects to see so skills/summaries never read as lowercase
# keyword soup. Unlisted terms fall back to acronym-aware title casing.
_TERM_DISPLAY = {
    "aws": "AWS", "gcp": "GCP", "azure": "Azure", "google cloud": "Google Cloud",
    "ci/cd": "CI/CD", "cicd": "CI/CD", "ci/cd pipeline": "CI/CD Pipelines",
    "ci/cd pipelines": "CI/CD Pipelines", "linux": "Linux", "windows": "Windows",
    "macos": "macOS", "unix": "Unix", "kubernete": "Kubernetes",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes", "docker": "Docker",
    "terraform": "Terraform", "ansible": "Ansible", "jenkins": "Jenkins",
    "mysql": "MySQL", "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "mongodb": "MongoDB", "redis": "Redis", "sqlite": "SQLite", "sql": "SQL",
    "fastapi": "FastAPI", "react": "React", "reactjs": "React", "react 18": "React 18",
    "node.js": "Node.js", "nodejs": "Node.js", "node": "Node.js",
    "typescript": "TypeScript", "javascript": "JavaScript", "python": "Python",
    "bash": "Bash", "powershell": "PowerShell", "celery": "Celery",
    "nmap": "Nmap", "zap": "OWASP ZAP", "sqlmap": "SQLMap", "wireshark": "Wireshark",
    "splunk": "Splunk", "prometheus": "Prometheus", "grafana": "Grafana",
    "active directory": "Active Directory", "intune": "Intune", "jira": "Jira",
    "proxmox": "Proxmox", "iam": "IAM", "soc 2": "SOC 2", "soc2": "SOC 2",
    "owasp": "OWASP", "owasp top 10": "OWASP Top 10", "cve": "CVE", "cvss": "CVSS",
    "gpo": "GPO", "vlan": "VLANs", "llm": "LLM", "llm agent": "LLM Agents",
    "llm agents": "LLM Agents", "self healing": "Self-Healing Systems",
    "self-healing": "Self-Healing Systems", "cloud based": "Cloud-Native",
    "cloud-based": "Cloud-Native", "incident response": "Incident Response",
    "vulnerability management": "Vulnerability Management",
    "penetration testing": "Penetration Testing",
    "information security": "Information Security",
    "application security": "Application Security", "cybersecurity": "Cybersecurity",
    "compliance": "Compliance", "networking": "Networking", "automation": "Automation",
    "troubleshooting": "Troubleshooting", "security": "Security",
    "pipeline": "Pipelines", "desktop support": "Desktop Support",
    "infrastructure as code": "Infrastructure as Code", "power bi": "Power BI",
    "google workspace": "Google Workspace", "microsoft 365": "Microsoft 365",
    "office 365": "Office 365", "mfa": "MFA", "otp": "OTP", "api": "APIs",
    "rest": "REST", "graphql": "GraphQL", "html": "HTML", "css": "CSS",
    "git": "Git", "github": "GitHub", "gitlab": "GitLab",
    # Cross-domain tools & terms (finance, marketing, design, healthcare,
    # sales, ops) so the casing layer is not biased toward any one field.
    "salesforce": "Salesforce", "hubspot": "HubSpot", "quickbooks": "QuickBooks",
    "sap": "SAP", "tableau": "Tableau", "looker": "Looker", "excel": "Excel",
    "powerpoint": "PowerPoint", "word": "Word", "outlook": "Outlook",
    "photoshop": "Photoshop", "illustrator": "Illustrator", "indesign": "InDesign",
    "figma": "Figma", "sketch": "Sketch", "canva": "Canva", "autocad": "AutoCAD",
    "solidworks": "SolidWorks", "matlab": "MATLAB", "sas": "SAS", "stata": "Stata",
    "spss": "SPSS", "google ads": "Google Ads", "google analytics": "Google Analytics",
    "wordpress": "WordPress", "mailchimp": "Mailchimp", "shopify": "Shopify",
    "servicenow": "ServiceNow", "workday": "Workday", "netsuite": "NetSuite",
    "oracle": "Oracle", "sql server": "SQL Server", "quickbooks online": "QuickBooks Online",
    "seo": "SEO", "sem": "SEM", "ppc": "PPC", "crm": "CRM", "erp": "ERP",
    "kpi": "KPIs", "roi": "ROI", "p&l": "P&L", "gaap": "GAAP", "ehr": "EHR",
    "hipaa": "HIPAA", "osha": "OSHA", "b2b": "B2B", "b2c": "B2C",
    "ux/ui": "UX/UI", "ui/ux": "UI/UX", "saas": "SaaS",
}

# Lowercase, no-spaces forms that should render fully uppercased. Covers
# common acronyms across many professions, not just tech.
_ACRONYMS = {
    # tech / IT
    "aws", "gcp", "ci", "cd", "iam", "soc", "cve", "cvss", "gpo", "vlan", "vlans",
    "llm", "mfa", "otp", "api", "apis", "sql", "html", "css", "ssh", "tcp", "ip",
    "dns", "vpn", "paas", "iaas", "etl", "ml", "ai", "nlp", "os", "rest", "json",
    "yaml", "xml", "cdn", "waf", "siem", "cms", "pos", "qa", "qc", "sdk", "ide",
    # business / finance / ops
    "crm", "erp", "kpi", "kpis", "roi", "okr", "okrs", "gaap", "ifrs", "ebitda",
    "ap", "ar", "hr", "it", "pmp", "cpa", "mba", "cfa", "cma", "shrm", "phr",
    "sphr", "b2b", "b2c", "b2g", "sla", "slas", "rfp", "rfq", "po", "sow",
    # marketing
    "seo", "sem", "ppc", "ctr", "cpa", "cpc", "cpm", "ugc", "smm",
    # healthcare
    "ehr", "emr", "hipaa", "icu", "er", "rn", "lpn", "cna", "bls", "acls",
    "cpr", "phi", "ot", "pt",
    # general / safety
    "osha", "fmla", "pto", "ada", "eeo", "gpa", "sat", "gre", "gmat",
    "ceo", "cfo", "cto", "coo", "cio", "vp", "svp", "evp",
    "ux", "ui", "saas",
}

# Connector words kept lowercase when they appear mid-phrase (e.g.
# "Cost of Goods Sold", "Search and Rescue").
_SMALL_WORDS = {
    "a", "an", "the", "of", "and", "or", "for", "to", "in", "on", "with",
    "at", "by", "as", "vs", "per", "via",
}


def _display_term(term: str) -> str:
    t = re.sub(r"\s+", " ", str(term or "")).strip()
    if not t:
        return ""
    low = t.lower()
    if low in _TERM_DISPLAY:
        return _TERM_DISPLAY[low]
    if low + "s" in _TERM_DISPLAY:  # restore plural the matcher stripped
        return _TERM_DISPLAY[low + "s"]
    parts = re.split(r"(\s+|/|-)", t)
    out: list[str] = []
    word_index = 0
    for part in parts:
        pl = part.lower()
        if part in ("/", "-") or part.strip() == "":
            out.append(part)
            continue
        if pl in _ACRONYMS:
            out.append(part.upper())
        elif part.isupper() and 2 <= len(part) <= 6:
            out.append(part)  # already an acronym, preserve it
        elif word_index > 0 and pl in _SMALL_WORDS:
            out.append(pl)  # keep connector words lowercase mid-phrase
        else:
            out.append(part[:1].upper() + part[1:])
        word_index += 1
    return "".join(out)


def _display_terms(terms: list[str], *, limit: Optional[int] = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        disp = _display_term(term)
        if not disp:
            continue
        key = disp.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(disp)
        if limit and len(out) >= limit:
            break
    return out


# ─── Keyword curation (de-noise + de-duplicate) ───────────────────────
# Scraped job descriptions leak markup/code fragments ("H2", "Data Stringify
# Link", "C Link") and the keyword extractor emits overlapping n-grams
# ("Compliance", "Compliance GAAP", "GAAP"). These helpers strip that noise so
# Core Skills and the summary read like a real, curated skills list.
_ARTIFACT_WORDS = {
    "stringify", "intro", "cid", "href", "span", "div", "img", "nbsp",
    "lorem", "ipsum", "link", "sk", "json", "dom", "css", "html", "px",
}
_RECOGNIZED_SKILLS_CACHE: Optional[set] = None


def _recognized_skills() -> set:
    global _RECOGNIZED_SKILLS_CACHE
    if _RECOGNIZED_SKILLS_CACHE is None:
        try:
            from app.utils.text_processing import TECH_SKILLS
            _RECOGNIZED_SKILLS_CACHE = {str(s).lower() for s in TECH_SKILLS}
        except Exception:
            _RECOGNIZED_SKILLS_CACHE = set()
    return _RECOGNIZED_SKILLS_CACHE


def _is_noise_keyword(term: str) -> bool:
    low = str(term or "").strip().lower()
    if len(low) < 2:
        return True
    for w in re.split(r"[\s/]+", low):
        if not w:
            continue
        if w in _ARTIFACT_WORDS:
            return True
        if re.fullmatch(r"[a-z]\d+", w):           # markup like h2, p3
            return True
        if w.isalpha():
            if len(w) == 1 and w not in {"c", "r"}:  # stray single-letter token ("C Link")
                return True
            if 2 <= len(w) <= 3 and not re.search(r"[aeiou]", w) and w not in _ACRONYMS:
                return True                          # vowel-less non-acronym ("Sk")
    return False


def _dedupe_compounds(terms: list[str]) -> list[str]:
    """Drop multi-word terms whose every word already appears as a standalone
    term — e.g. remove "Compliance GAAP"/"Python SQL" when "Compliance",
    "GAAP", "Python", "SQL" are present."""
    singles = {t.lower() for t in terms if not re.search(r"[\s/]", t)}
    out: list[str] = []
    for t in terms:
        words = [w for w in re.split(r"[\s/]+", t.lower()) if w]
        if len(words) > 1 and all(w in singles for w in words):
            continue
        out.append(t)
    return out


def _clean_terms(terms: list[str]) -> list[str]:
    cleaned = _dedupe_compounds(_display_terms(terms))
    return [t for t in cleaned if not _is_noise_keyword(t)]


def _curate_skills(matched: list[str], missing: list[str], resume_skills: list[str], *, limit: int = 26) -> list[str]:
    """Build a clean Core Skills list. Grounded terms (in the resume / matched
    to the job) are kept; JD-only "missing" terms are admitted only when they
    are recognized skills, which filters out scraped markup noise."""
    recognized = _recognized_skills()
    grounded = [*(matched or []), *(resume_skills or [])]
    aspirational = [m for m in (missing or []) if str(m).strip().lower() in recognized]
    return _clean_terms([*grounded, *aspirational])[:limit]


# Deterministic-fallback skill categorization (the LLM does this better when
# available; this keeps Core Skills grouped even when Groq is offline).
_SKILL_CATEGORIES = [
    ("Cloud & Infrastructure", {"aws", "azure", "gcp", "google cloud", "cloud", "kubernetes", "docker", "terraform", "ansible", "linux", "unix", "windows server", "networking", "vpn", "vlan", "dns", "dhcp", "active directory", "proxmox", "vmware", "server", "infrastructure", "ci/cd", "jenkins", "helm", "nginx"}),
    ("Security & Compliance", {"security", "owasp", "cvss", "soc 2", "compliance", "gaap", "hipaa", "incident response", "vulnerability management", "penetration testing", "siem", "iam", "mfa", "audit", "nist", "cybersecurity", "hardening", "gpo", "encryption", "firewall", "sox"}),
    ("Programming & Scripting", {"python", "java", "javascript", "typescript", "bash", "powershell", "sql", "c++", "c#", "ruby", "php", "react", "node.js", "fastapi", "celery", "html", "css", "scala", "rust", "kotlin"}),
    ("Data & Reporting", {"tableau", "power bi", "excel", "pandas", "numpy", "analytics", "reporting", "etl", "looker", "spss", "sas", "forecasting", "financial modeling", "dashboards", "bigquery", "snowflake"}),
    ("Tools & Platforms", {"jira", "github", "gitlab", "salesforce", "hubspot", "servicenow", "workday", "sap", "netsuite", "intune", "okta", "microsoft 365", "office 365", "quickbooks", "confluence", "slack"}),
]


def _categorize_skills(skills: list[str]) -> list[dict]:
    buckets: dict[str, list[str]] = {name: [] for name, _ in _SKILL_CATEGORIES}
    other: list[str] = []
    for skill in skills:
        low = skill.lower()
        placed = False
        for name, indicators in _SKILL_CATEGORIES:
            if low in indicators or any(len(ind) > 3 and ind in low for ind in indicators):
                buckets[name].append(skill)
                placed = True
                break
        if not placed:
            other.append(skill)
    groups = [{"category": name, "items": items} for name, items in buckets.items() if items]
    if other:
        groups.append({"category": "Additional Skills", "items": other})
    return groups[:6]


# ─── Experience / bullet normalization ────────────────────────────────
_BULLET_RE = re.compile(
    r"^\s*(?:[•●▪▫‣◦○·∙⁌⁃∗*►▶▷◆◇§]+|[-–—]+|l(?=\s+[A-Z]))\s+"
)
# Date detection covers the formats seen across real resumes regardless of
# field: "Jan 2020", "January 2020", "Summer 2021", "06/2020", "2020".
_MONTH_TOKEN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?"
    r"|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
_SEASON_TOKEN = r"(?:Spring|Summer|Fall|Autumn|Winter)"
_DATE_POINT = (
    r"(?:(?:" + _MONTH_TOKEN + r"|" + _SEASON_TOKEN + r"|\d{1,2}[/.\-])\s*)?\d{4}"
)
_DATE_END = r"(?:Present|Current|Now|Ongoing|To\s*Date|Today|" + _DATE_POINT + r")"
_DATE_RANGE_RE = re.compile(
    r"\s*[–—\-]?\s*(" + _DATE_POINT + r"\s*(?:[–—\-]|to)\s*" + _DATE_END + r")\s*$",
    re.I,
)


def _strip_keyword_stuffing(text: str) -> str:
    return re.sub(r"\s+with emphasis on [^.]*\.?\s*$", "", text, flags=re.I).strip()


_ABBREV_END = {"etc.", "inc.", "ltd.", "co.", "e.g.", "i.e.", "vs.", "approx.",
               "dept.", "jr.", "sr.", "u.s.", "u.k.", "u.s.a.", "ph.d.", "no."}


def _ends_with_abbrev(text: str) -> bool:
    """True if the line ends in an abbreviation (e.g. 'across U.S.') so its
    trailing period must not be treated as a sentence end."""
    s = str(text or "").rstrip()
    if re.search(r"(?:\b[A-Za-z]\.){1,}$", s):       # U.S., U.S.A., e.g.
        return True
    return s.lower().rsplit(" ", 1)[-1] in _ABBREV_END


def _polish_bullet(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip(" -–—•*\t")
    t = _strip_keyword_stuffing(t)
    if len(t) < 3:
        return ""
    t = t[:1].upper() + t[1:]
    if t[-1] not in ".!?":
        t += "."
    return t


def _weak_tailor_fragment(text: str) -> bool:
    t = re.sub(r"\s+", " ", str(text or "")).strip(" .,-;:")
    if not t:
        return True
    words = t.split()
    if len(words) >= 5:
        return False
    if re.search(r"\b\d+%|\$\d+|\b\d{4}\b|\b[A-Z]{2,}\b|\b(Security\+|CySA\+|Network\+|CISSP|AWS|Azure|GCP)\b", t):
        return False
    return True


def _merge_fragment_lines(lines: list[str], *, limit: int = 12) -> list[str]:
    """Merge PDF-extracted fragments like short project/education words."""
    cleaned = [re.sub(r"\s+", " ", str(line or "")).strip(" -\t") for line in (lines or [])]
    cleaned = [line for line in cleaned if line]
    if not cleaned:
        return []
    short_ratio = sum(1 for line in cleaned if len(line.split()) <= 3) / max(1, len(cleaned))
    if short_ratio < 0.55:
        return cleaned[:limit]
    joined = " ".join(cleaned)
    parts = [p.strip(" .;-") for p in re.split(r"\s*(?:\||;)\s*|\s{3,}", joined) if p.strip(" .;-")]
    if len(parts) <= 1:
        parts = [joined.strip(" .;-")]
    return parts[:limit]


def _usable_tailor_bullets(lines: list[str], *, limit: int = 8) -> list[str]:
    out: list[str] = []
    for raw in _merge_fragment_lines(lines, limit=limit * 2):
        bullet = _polish_bullet(raw)
        if not bullet or _weak_tailor_fragment(bullet):
            continue
        out.append(bullet)
        if len(out) >= limit:
            break
    return out


def _split_header(line: str) -> tuple[str, str]:
    m = _DATE_RANGE_RE.search(line)
    if m:
        dates = m.group(1).strip()
        head = line[: m.start()].strip(" |-–—\t")
        return head, dates
    return line.strip(" |\t"), ""


def _is_header_line(raw_line: str, marked: bool) -> bool:
    if marked:
        return False
    return (" | " in raw_line) or bool(_DATE_RANGE_RE.search(raw_line))


def _is_roleish(text: str) -> bool:
    """A short, non-sentence line that reads like a job-title/company line
    rather than an accomplishment bullet."""
    t = (text or "").strip()
    return bool(t) and t[-1:] not in ".!?" and len(t) <= 70 and len(t.split()) <= 10


def _group_experience(lines: list[str], *, max_entries: int = 6, max_bullets: int = 6) -> list[dict]:
    """Turn flat resume lines into {header, dates, bullets} entries.

    Handles three line shapes seen in parsed resumes: company/role headers
    (contain ' | ' or a trailing date range), glyph-marked bullets, and
    unmarked wrapped continuations of the previous bullet.
    """
    entries: list[dict] = []
    cur: Optional[dict] = None
    for raw in lines:
        line = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not line:
            continue
        marked = bool(_BULLET_RE.match(line))
        body = _BULLET_RE.sub("", line).strip() if marked else line
        if not body:
            continue
        if _is_header_line(line, marked):
            head, dates = _split_header(body)
            if not head and dates:
                # Date-only line: bind it to the job-title line it sits under.
                # That title is usually the trailing "roleish" line of the
                # current entry (resumes that stack title / dates / bullets).
                role = cur["bullets"][-1] if (cur and cur["bullets"] and _is_roleish(cur["bullets"][-1])) else None
                if role is not None and cur and not cur["dates"] and not cur["header"]:
                    cur["bullets"].pop()
                    cur["header"] = role
                    cur["dates"] = dates
                elif role is not None:
                    cur["bullets"].pop()
                    cur = {"header": role, "dates": dates, "bullets": []}
                    entries.append(cur)
                elif cur and cur["header"] and not cur["dates"]:
                    cur["dates"] = dates
                else:
                    cur = {"header": "", "dates": dates, "bullets": []}
                    entries.append(cur)
                continue
            cur = {"header": head, "dates": dates, "bullets": []}
            entries.append(cur)
            continue
        if cur is None:
            cur = {"header": "", "dates": "", "bullets": []}
            entries.append(cur)
        body = _strip_keyword_stuffing(body)
        prev = cur["bullets"][-1] if cur["bullets"] else ""
        # Bullets are stored raw here and polished in a final pass. An unmarked
        # line is a wrapped continuation of the previous bullet when it starts
        # lowercase ("and global jurisdictions") or the previous line has no
        # real sentence end — counting a trailing abbreviation like "U.S." as
        # NOT a sentence end.
        starts_lower = body[:1].islower()
        prev_unfinished = bool(prev) and prev.rstrip()[-1:] not in ".!?:"
        # Merge only on a clear continuation signal — a lowercase start, a
        # false period from an abbreviation ("U.S."), or a prev that ends with
        # no punctuation AND this line also starts lowercase — so a new
        # capitalized bullet is never swallowed by a dangling previous line.
        merge = (not marked) and bool(prev) and (
            starts_lower or _ends_with_abbrev(prev) or (prev_unfinished and starts_lower)
        )
        if merge:
            cur["bullets"][-1] = f"{prev.rstrip()} {body}".strip()
        elif body:
            cur["bullets"].append(body)

    cleaned: list[dict] = []
    for entry in entries:
        bullets = [
            pb for pb in (_polish_bullet(b) for b in entry["bullets"])
            if pb and not _weak_tailor_fragment(pb)
        ][:max_bullets]
        if entry["header"] or bullets:
            cleaned.append({"header": entry["header"], "dates": entry["dates"], "bullets": bullets})
        if len(cleaned) >= max_entries:
            break
    return cleaned


def _clean_bullets(lines: list[str], *, limit: int = 8) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for entry in _group_experience(lines, max_entries=20, max_bullets=limit):
        for b in entry["bullets"]:
            key = b.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(b)
            if len(out) >= limit:
                return out
    return out


def _polish_certification(text: str) -> str:
    t = _BULLET_RE.sub("", re.sub(r"\s+", " ", str(text or "")).strip())
    return t.strip(" -–—•*\t").rstrip(".")


_CERT_HINTS = (
    "certified", "certification", "certificate", "credential", "license",
    "comptia", "security+", "network+", "pentest+", "cysa", "cissp", "ccna",
    "aws", "azure", "gcp", "pmp", "cpa", "cfa", "scrum", "microsoft", "cisco",
    "google", "oracle", "itil", "six sigma", "sc-900", "rhce", "ceh", "okta",
)


def _looks_like_cert(text: str) -> bool:
    low = text.lower()
    if any(h in low for h in _CERT_HINTS):
        return True
    if re.search(r"\b(19|20)\d{2}\b", text):     # has a year
        return True
    if re.search(r"\([^)]+\)", text):            # has a parenthetical (e.g. "(ce)")
        return True
    return False


def _curate_certifications(lines: list[str], *, limit: int = 6) -> list[str]:
    """Clean certification lines. If parsing fragmented them into single words
    (e.g. '&', 'Achievements', 'l', 'Passed', 'the', 'CPA'), collapse and keep
    only entries that actually read like credentials."""
    items = [c for c in (_polish_certification(str(v)) for v in (lines or [])) if c]
    if not items:
        return []
    fragments = sum(1 for c in items if len(c.split()) <= 1)
    if fragments / len(items) > 0.4:
        blob = " ".join(items)
        split = [p.strip(" -–—•·\t") for p in re.split(r"\s*[•·;|]\s*|\s{2,}", blob)]
        items = [p for p in split if len(p) > 2] or [blob.strip()]
    kept = [c for c in items if _looks_like_cert(c)]
    return (kept or items)[:limit]


def _rank_experience_to_job(entries: list[dict], jd_terms: list[str], *, keep: int = 6) -> list[dict]:
    """Reorder each job's bullets so the ones matching the target job's
    keywords surface first, then keep the most relevant. Facts are never
    changed — only prioritized — so the same true history reads differently
    per position. Ties preserve the resume's original order (stable sort)."""
    terms = sorted({str(t).lower().strip() for t in (jd_terms or []) if len(str(t).strip()) >= 2})

    def score(bullet: str) -> int:
        low = f" {bullet.lower()} "
        return sum(1 for t in terms if t in low or t in bullet.lower())

    ranked: list[dict] = []
    for e in entries:
        bullets = sorted(e.get("bullets") or [], key=score, reverse=True)
        ranked.append({"header": e.get("header", ""), "dates": e.get("dates", ""), "bullets": bullets[:keep]})
    return ranked


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
    resume_skills = [str(v).strip() for v in (resume_json.get("skills") or []) if str(v).strip()]
    skills = _curate_skills(matched, missing, resume_skills, limit=26)
    target_keywords = _clean_terms([*matched[:12], *missing[:14]])
    # Position-specific summary: lead with the candidate's genuine strengths
    # that this job actually asks for (matched terms, de-noised), and name the
    # role and company, so the summary changes meaningfully per position.
    # Only claim strengths the resume actually demonstrates (matched terms).
    # The old fallback pulled from MISSING keywords, which put skills on the
    # document the candidate never had — a fabrication and an interview risk.
    core = _clean_terms(matched)[:6]
    if len(core) >= 3:
        strengths = f"{', '.join(core[:-1])}, and {core[-1]}"
    elif core:
        strengths = " and ".join(core)
    else:
        strengths = ""
    if strengths:
        summary = (
            f"{title} with hands-on experience in {strengths}, targeting the "
            f"{title} position at {company}. Known for clear ownership, "
            f"measurable results, and steady collaboration across teams."
        )
    else:
        summary = (
            f"Candidate targeting the {title} position at {company}, bringing "
            f"a track record of ownership, measurable results, and steady "
            f"collaboration across teams."
        )
    experience_lines = resume_json.get("experience") or _clean_resume_lines(resume_text, limit=36)
    project_lines = _merge_fragment_lines(resume_json.get("projects") or [], limit=8)
    education_lines = _merge_fragment_lines(resume_json.get("education") or [], limit=8)
    cert_lines = _merge_fragment_lines(resume_json.get("certifications") or [], limit=10)
    # Reorder each job's real bullets toward this job's keywords so the
    # experience section adapts per position without altering the facts.
    jd_terms = [*(matched or []), *(missing or [])]
    experience = _rank_experience_to_job(
        _group_experience([str(v) for v in experience_lines], max_entries=6, max_bullets=10),
        jd_terms, keep=6,
    )
    return {
        "name": _candidate_name(user, resume_text),
        "contact": [str(item).strip() for item in contact_items if str(item or "").strip()],
        "target": f"{title}  |  {company}{('  |  ' + location) if location else ''}",
        "summary": summary,
        "skills": skills,
        "skill_groups": _categorize_skills(skills),
        "experience": experience,
        "projects": _usable_tailor_bullets([str(v) for v in project_lines], limit=5) if project_lines else [],
        "education": _group_experience([str(v) for v in education_lines], max_entries=4, max_bullets=4),
        "certifications": _curate_certifications(cert_lines, limit=6),
        "keywords": target_keywords[:18],
    }


def _payload_from_llm(llm: dict, job: dict, user: dict, resume_text: str) -> Optional[dict]:
    """Map the LLM tailoring JSON onto the renderer's payload shape. Returns
    None if the structure is too thin to render (caller then falls back)."""
    r = llm.get("resume") if isinstance(llm, dict) else None
    if not isinstance(r, dict):
        return None
    title = job.get("title") or "Target Role"
    company = job.get("company") or "Target Company"
    location = job.get("location") or ""

    experience: list[dict] = []
    for e in (r.get("experience") or []):
        if not isinstance(e, dict):
            continue
        header = " | ".join(part for part in (
            str(e.get("title") or "").strip(),
            str(e.get("company") or "").strip(),
            str(e.get("location") or "").strip(),
        ) if part)
        bullets = [
            b for b in (_polish_bullet(str(x)) for x in (e.get("bullets") or []))
            if b and not _weak_tailor_fragment(b)
        ][:5]
        if header or bullets:
            experience.append({"header": header, "dates": str(e.get("dates") or "").strip(), "bullets": bullets})

    education: list[dict] = []
    for e in (r.get("education") or []):
        if not isinstance(e, dict):
            continue
        detail = ", ".join(part for part in (
            str(e.get("institution") or "").strip(),
            str(e.get("location") or "").strip(),
        ) if part)
        header = str(e.get("degree") or "").strip()
        if header or detail:
            education.append({"header": header, "dates": str(e.get("dates") or "").strip(), "bullets": [detail] if detail else []})

    summary = str(r.get("summary") or "").strip()
    if not (summary and experience):
        return None

    # Skills may arrive categorized ([{category, items}]) or as a flat list.
    skill_groups: list[dict] = []
    flat_skills: list[str] = []
    for g in (r.get("skills") or []):
        if isinstance(g, dict):
            cat = str(g.get("category") or "").strip()
            items = _display_terms([str(i) for i in (g.get("items") or []) if str(i or "").strip()], limit=12)
            if cat and items:
                skill_groups.append({"category": cat, "items": items})
                flat_skills.extend(items)
        elif isinstance(g, str) and g.strip():
            flat_skills.append(g.strip())
    flat_skills = _display_terms(flat_skills, limit=30)

    contact = [str(c).strip() for c in (r.get("contact") or []) if str(c or "").strip()]
    match = llm.get("match") if isinstance(llm.get("match"), dict) else {}
    return {
        "name": str(r.get("name") or "").strip() or _candidate_name(user, resume_text),
        "contact": contact or [str(user.get("email") or "").strip()],
        "target": f"{title}  |  {company}{('  |  ' + location) if location else ''}",
        "summary": summary,
        "skills": flat_skills,
        "skill_groups": skill_groups[:6],
        "experience": experience[:6],
        "projects": [
            str(x).strip() for x in (r.get("projects") or [])
            if str(x or "").strip() and not _weak_tailor_fragment(str(x))
        ][:5],
        "education": education[:4],
        "certifications": _curate_certifications([str(x) for x in (r.get("certifications") or [])], limit=6),
        "keywords": _display_terms([*(match.get("strong") or []), *(match.get("have_but_unstated") or [])])[:18],
    }


def _tailored_resume_text(resume: dict) -> str:
    parts: list[str] = [
        str(resume.get("name") or ""),
        " | ".join(str(item) for item in (resume.get("contact") or [])),
        str(resume.get("target") or ""),
        str(resume.get("summary") or ""),
        "Skills: " + ", ".join(str(item) for item in (resume.get("skills") or [])),
    ]
    for group in resume.get("skill_groups") or []:
        if isinstance(group, dict):
            parts.append(f"{group.get('category') or 'Skills'}: " + ", ".join(str(item) for item in (group.get("items") or [])))
    for section in ("experience", "education"):
        for entry in resume.get(section) or []:
            if isinstance(entry, dict):
                parts.append(" ".join(str(entry.get(key) or "") for key in ("header", "dates")))
                parts.extend(str(item) for item in (entry.get("bullets") or []))
    parts.extend(str(item) for item in (resume.get("projects") or []))
    parts.extend(str(item) for item in (resume.get("certifications") or []))
    if resume.get("keywords"):
        parts.append("Target Keywords: " + ", ".join(str(item) for item in (resume.get("keywords") or [])))
    return "\n".join(part for part in parts if part.strip())


def _deterministic_tailored_ats_score(resume: dict, job_text: str, fallback: int = 0) -> int:
    try:
        from app.services.ats_analysis import analyze

        analysis = analyze(_tailored_resume_text(resume), job_text)
        score = analysis.get("match_score") or analysis.get("score")
        return max(0, min(100, int(round(float(score)))))
    except Exception as exc:
        log.warning("Tailored ATS score fallback used: %s", exc)
        return max(0, min(100, int(fallback or 0)))


def _raw_resume_match_score(resume_text: str, job_text: str, fallback: int = 0) -> int:
    """Score the original active resume on the same scale used for tailored output."""
    try:
        from app.services.ats_analysis import analyze

        analysis = analyze(resume_text or "", job_text or "")
        score = analysis.get("match_score") or analysis.get("score")
        return max(0, min(100, int(round(float(score)))))
    except Exception as exc:
        log.warning("Original resume ATS score fallback used: %s", exc)
        return max(0, min(100, int(fallback or 0)))


def _build_original_preserving_tailored_payload(
    resume_text: str,
    resume_json: dict,
    job: dict,
    matched: list[str],
    missing: list[str],
    user: dict,
) -> dict:
    """Conservative tailor pass used when a generated rewrite loses signal.

    It keeps more of the user's original resume evidence and only reorders it
    toward the job. That prevents a thin LLM rewrite from deleting the very
    keywords/accomplishments that produced a strong current match.
    """
    payload = _build_tailored_resume_payload(resume_text, resume_json, job, matched, missing, user)
    sections = resume_json.get("sections") if isinstance(resume_json, dict) else {}
    original_lines = (
        list((sections or {}).get("experience") or [])
        or list(resume_json.get("experience") or [])
        or _clean_resume_lines(resume_text, limit=110)
    )
    ranked = _rank_experience_to_job(
        _group_experience(original_lines, max_entries=8, max_bullets=12),
        [*(matched or []), *(missing or [])],
        keep=8,
    )
    if ranked:
        payload["experience"] = ranked
    payload["keywords"] = _clean_terms([*(matched or [])[:16], *(missing or [])[:10]])[:24]
    skills = _curate_skills(matched, missing, [str(v) for v in (resume_json.get("skills") or [])], limit=32)
    if skills:
        payload["skills"] = skills
        payload["skill_groups"] = _categorize_skills(skills)
    return payload


def _select_tailored_resume_payload(
    *,
    llm_payload: Optional[dict],
    deterministic_payload: dict,
    conservative_payload: dict,
    resume_text: str,
    job_text: str,
    current_match_score: int,
) -> tuple[dict, int, str, dict]:
    """Pick the strongest generated resume and prevent visible score regressions."""
    candidates: list[tuple[str, dict, int]] = []
    if llm_payload:
        candidates.append(("llm", llm_payload, _deterministic_tailored_ats_score(llm_payload, job_text, current_match_score)))
    candidates.append((
        "deterministic",
        deterministic_payload,
        _deterministic_tailored_ats_score(deterministic_payload, job_text, current_match_score),
    ))
    candidates.append((
        "conservative",
        conservative_payload,
        _deterministic_tailored_ats_score(conservative_payload, job_text, current_match_score),
    ))
    original_score = _raw_resume_match_score(resume_text, job_text, current_match_score)
    best_engine, best_payload, raw_score = max(candidates, key=lambda row: row[2])

    floor_score = max(current_match_score, original_score)
    projected_score = max(raw_score, floor_score)
    diagnostics = {
        "raw_tailored_score": raw_score,
        "original_score": original_score,
        "current_match_score": current_match_score,
        "score_floor_applied": projected_score > raw_score,
        "candidate_scores": {engine: score for engine, _payload, score in candidates},
    }
    if raw_score < floor_score:
        best_engine = f"{best_engine}+score_guard"
    return best_payload, projected_score, best_engine, diagnostics


def _doc_bytes(resume: dict, title: str) -> bytes:
    def p(value: str) -> str:
        return html.escape(str(value or ""))

    def bullet_list(items: list[str]) -> str:
        return "<ul>" + "".join(f"<li>{p(i)}</li>" for i in items) + "</ul>"

    def entries_html(entries: list[dict]) -> str:
        rows = []
        for e in entries:
            header = p(e.get("header") or "")
            dates = p(e.get("dates") or "")
            head_html = ""
            if header or dates:
                # Word does not support flexbox in HTML-based .doc files, which
                # broke title/date alignment. A borderless two-cell table is the
                # Word-safe way to right-align dates on the same line.
                head_html = (
                    f"<table class='entry'><tr><td class='entry-title'>{header}</td>"
                    f"<td class='entry-dates'>{dates}</td></tr></table>"
                )
            blist = bullet_list(e.get("bullets") or []) if e.get("bullets") else ""
            rows.append(head_html + blist)
        return "\n".join(rows)

    parts = [f"<h1>{p(str(resume['name'] or '').upper())}</h1>"]
    parts.append(f"<div class='contact'>{p('  |  '.join(resume['contact']))}</div>")
    if resume.get("target"):
        parts.append(f"<div class='target'>{p(resume['target'])}</div>")
    parts.append("<h2>Professional Summary</h2>")
    parts.append(f"<p>{p(resume['summary'])}</p>")
    parts.append("<h2>Core Skills</h2>")
    skill_groups = resume.get("skill_groups") or []
    if skill_groups:
        for g in skill_groups[:6]:
            cat = str(g.get("category") or "").strip()
            items = [str(i) for i in (g.get("items") or []) if str(i).strip()][:10]
            if cat and items:
                parts.append(f"<p class='skills'><b>{p(cat)}:</b> {p(', '.join(items))}</p>")
    else:
        parts.append(f"<p class='skills'>{p(' • '.join(resume['skills']))}</p>")
    parts.append("<h2>Professional Experience</h2>")
    parts.append(entries_html(resume.get("experience") or []))
    if resume.get("projects"):
        parts.append("<h2>Projects</h2>")
        parts.append(bullet_list(resume["projects"]))
    if resume.get("education"):
        parts.append("<h2>Education</h2>")
        parts.append(entries_html(resume["education"]))
    if resume.get("certifications"):
        parts.append("<h2>Certifications</h2>")
        parts.append(bullet_list(resume["certifications"]))
    body_html = "\n".join(parts)

    document = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    @page {{ margin: 0.6in 0.7in; }}
    body {{ font-family: 'Calibri', 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; line-height: 1.3; margin: 0; font-size: 10.5pt; }}
    h1 {{ font-size: 21pt; font-weight: 700; text-align: center; letter-spacing: 1px; margin: 0 0 2px; }}
    .contact {{ text-align: center; font-size: 9pt; color: #444; margin: 0 0 2px; }}
    .target {{ text-align: center; font-size: 9.5pt; font-style: italic; color: #555; margin: 0 0 12px; }}
    h2 {{ font-size: 10.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; color: #1a1a1a; border-bottom: 1.2px solid #1a1a1a; margin: 13px 0 6px; padding-bottom: 2px; }}
    p {{ margin: 0 0 6px; }}
    .skills {{ color: #222; }}
    table.entry {{ width: 100%; border-collapse: collapse; margin: 6px 0 1px; }}
    table.entry td {{ border: none; padding: 0; vertical-align: top; }}
    .entry-title {{ font-weight: 700; }}
    .entry-dates {{ color: #555; font-size: 9.5pt; white-space: nowrap; padding-left: 12px; text-align: right; width: 26%; }}
    ul {{ margin: 1px 0 4px 18px; padding: 0; }}
    li {{ margin: 0 0 2px; }}
  </style>
</head>
<body>
  {body_html}
</body>
</html>"""
    return document.encode("utf-8")


def _simple_pdf_bytes(resume: dict) -> bytes:
    exp_lines: list[str] = []
    for e in (resume.get("experience") or []):
        head = e.get("header") or ""
        if e.get("dates"):
            head = f"{head}  ({e['dates']})" if head else e["dates"]
        if head:
            exp_lines.append(head)
        exp_lines.extend(f"  - {b}" for b in (e.get("bullets") or []))
    lines = [
        resume.get("name") or "Candidate Name",
        "  |  ".join(resume.get("contact") or []),
        resume.get("target") or "",
        "",
        "PROFESSIONAL SUMMARY",
        resume.get("summary") or "",
        "",
        "CORE SKILLS",
        ", ".join(resume.get("skills") or []),
        "",
        "PROFESSIONAL EXPERIENCE",
        *exp_lines,
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


# Density presets, roomy -> tight. The generator renders with the first preset
# that fits one page. Per the ATS spec, font never drops below the floor
# (body >=10pt, name >=18pt, headings 12-14pt, margins >=0.5in, 3-5 bullets) —
# to fit, we CUT the weakest content (fewer bullets/entries/skills), we do not
# shrink type below spec.
_PDF_PRESETS = [
    {"name": 21, "sec": 13.5, "body": 11.0, "bul": 11.0, "lead": 13.6, "sp": 11, "gap": 5, "top": 0.7,  "side": 0.75, "max_e": 6, "max_b": 5, "max_sk": 24, "max_proj": 4},
    {"name": 20, "sec": 13.0, "body": 10.5, "bul": 10.5, "lead": 13.0, "sp": 10, "gap": 4, "top": 0.6,  "side": 0.65, "max_e": 5, "max_b": 5, "max_sk": 22, "max_proj": 4},
    {"name": 19, "sec": 12.5, "body": 10.2, "bul": 10.2, "lead": 12.4, "sp": 9,  "gap": 4, "top": 0.55, "side": 0.6,  "max_e": 5, "max_b": 4, "max_sk": 20, "max_proj": 3},
    {"name": 18, "sec": 12.0, "body": 10.0, "bul": 10.0, "lead": 12.0, "sp": 8,  "gap": 3, "top": 0.5,  "side": 0.55, "max_e": 5, "max_b": 4, "max_sk": 18, "max_proj": 3},
    {"name": 18, "sec": 12.0, "body": 10.0, "bul": 10.0, "lead": 11.7, "sp": 7,  "gap": 3, "top": 0.5,  "side": 0.5,  "max_e": 4, "max_b": 4, "max_sk": 16, "max_proj": 2},
]


def _pdf_bytes(resume: dict, title: str) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )

        ink = colors.HexColor("#1a1a1a")
        muted = colors.HexColor("#555555")
        base = getSampleStyleSheet()

        def safe(value: str) -> str:
            return html.escape(str(value or "")).replace("\n", "<br/>")

        def render(preset: dict) -> tuple[bytes, int]:
            side = preset["side"] * inch
            avail = letter[0] - 2 * side
            styles = {
                "name": ParagraphStyle("Name", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=preset["name"], leading=preset["name"] + 3, alignment=TA_CENTER, textColor=ink, spaceAfter=3),
                "contact": ParagraphStyle("Contact", parent=base["Normal"], fontName="Helvetica", fontSize=max(8.0, preset["body"] - 0.8), leading=preset["lead"] - 1, alignment=TA_CENTER, textColor=colors.HexColor("#444444"), spaceAfter=2),
                "target": ParagraphStyle("Target", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=max(8.5, preset["body"] - 0.3), leading=preset["lead"] - 1, alignment=TA_CENTER, textColor=muted, spaceAfter=4),
                "section": ParagraphStyle("Section", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=preset["sec"], leading=preset["sec"] + 1.5, alignment=TA_LEFT, textColor=ink, spaceBefore=preset["sp"], spaceAfter=2),
                "body": ParagraphStyle("Body", parent=base["Normal"], fontName="Helvetica", fontSize=preset["body"], leading=preset["lead"], textColor=ink, spaceAfter=2),
                "entry": ParagraphStyle("Entry", parent=base["Normal"], fontName="Helvetica", fontSize=preset["body"] + 0.2, leading=preset["lead"], textColor=ink),
                "entry_date": ParagraphStyle("EntryDate", parent=base["Normal"], fontName="Helvetica", fontSize=preset["body"] - 0.8, leading=preset["lead"], alignment=TA_RIGHT, textColor=muted),
                "bullet": ParagraphStyle("Bullet", parent=base["Normal"], fontName="Helvetica", fontSize=preset["bul"], leading=preset["lead"], leftIndent=13, firstLineIndent=-9, textColor=ink, spaceAfter=1.5),
            }

            def section(story: list, heading: str) -> None:
                story.append(Paragraph(safe(heading.upper()), styles["section"]))
                story.append(HRFlowable(width="100%", thickness=1.0, color=ink, spaceBefore=1, spaceAfter=preset["gap"]))

            def add_bullets(story: list, items: list[str], cap: int) -> None:
                for item in items[:cap]:
                    story.append(Paragraph(f"- {safe(item)}", styles["bullet"]))

            def add_entries(story: list, entries: list[dict]) -> None:
                for e in entries[: preset["max_e"]]:
                    header = e.get("header") or ""
                    dates = e.get("dates") or ""
                    if header or dates:
                        parts = [pt for pt in header.split(" | ") if pt.strip()]
                        if parts:
                            bold_n = min(2, len(parts))  # bold title + company
                            left_html = "  |  ".join(f"<b>{safe(p)}</b>" for p in parts[:bold_n])
                            if len(parts) > bold_n:
                                left_html += "  |  " + safe("  |  ".join(parts[bold_n:]))
                        else:
                            left_html = f"<b>{safe(header)}</b>"
                        row = Table(
                            [[Paragraph(left_html, styles["entry"]),
                              Paragraph(safe(dates), styles["entry_date"])]],
                            colWidths=[avail * 0.74, avail * 0.26],
                        )
                        row.setStyle(TableStyle([
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                        ]))
                        story.append(row)
                    add_bullets(story, e.get("bullets") or [], preset["max_b"])

            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf, pagesize=letter,
                leftMargin=side, rightMargin=side,
                topMargin=preset["top"] * inch, bottomMargin=preset["top"] * inch,
                title=title,
            )
            story: list = [
                Paragraph(safe(str(resume.get("name") or "").upper()), styles["name"]),
                Paragraph(safe("  |  ".join(resume.get("contact") or [])), styles["contact"]),
            ]
            if resume.get("target"):
                story.append(Paragraph(safe(resume.get("target")), styles["target"]))
            section(story, "Professional Summary")
            story.append(Paragraph(safe(resume.get("summary")), styles["body"]))
            section(story, "Core Skills")
            groups = resume.get("skill_groups") or []
            if groups:
                for g in groups[:6]:
                    cat = str(g.get("category") or "").strip()
                    items = [str(i) for i in (g.get("items") or []) if str(i).strip()][:10]
                    if cat and items:
                        story.append(Paragraph(f"<b>{safe(cat)}:</b> {safe(', '.join(items))}", styles["body"]))
            else:
                story.append(Paragraph(safe(", ".join((resume.get("skills") or [])[: preset["max_sk"]])), styles["body"]))
            section(story, "Professional Experience")
            add_entries(story, resume.get("experience") or [])
            if resume.get("projects"):
                section(story, "Projects")
                add_bullets(story, resume.get("projects") or [], preset["max_proj"])
            if resume.get("education"):
                section(story, "Education")
                add_entries(story, resume.get("education") or [])
            if resume.get("certifications"):
                section(story, "Certifications")
                add_bullets(story, resume.get("certifications") or [], 8)
            story.append(Spacer(1, 0.01 * inch))
            doc.build(story)
            return buf.getvalue(), doc.page

        last = b""
        for preset in _PDF_PRESETS:
            data, pages = render(preset)
            last = data
            if pages <= 1:
                return data
        return last  # tightest preset; best effort if still long
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
    # SECURITY: strip every server-owned field. `plan` in particular must
    # never be client-writable — it drives billing tier AND (formerly) the
    # admin check, so accepting it from this endpoint was a privilege
    # escalation: any signed-in user could PUT {"plan": "admin"}.
    for privileged in ("id", "email", "updated_at", "plan", "payment_status", "payment_plan", "payment_reference"):
        fields.pop(privileged, None)
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
    _invalidate_jobs_context(user_id)
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
    now = time.monotonic()
    cached = _dashboard_summary_cache.get(user_id)
    if cached and now - cached[0] < _DASHBOARD_SUMMARY_TTL_SECONDS:
        return cached[1].model_copy(deep=True)

    resumes = user_store.list_resumes(user_id)
    active_resume = next((r for r in resumes if r.get("active")), None) or (resumes[0] if resumes else None)
    resume_score = int((active_resume or {}).get("score") or 0)

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

    payload = DashboardSummary(
        resume_score=resume_score,
        has_resume=bool(active_resume),
        active_resume_name=(active_resume or {}).get("name"),
        total_resumes=len(resumes),
        total_jobs=total_jobs,
        total_applications=total_applications,
        recent_alerts=recent_alerts,
    )
    if len(_dashboard_summary_cache) > 2000:
        _dashboard_summary_cache.clear()
    _dashboard_summary_cache[user_id] = (now, payload)
    return payload


@router.post("/applications")
async def save_user_application(payload: UserApplication = Body(...), user_id: str = Depends(current_user_id)):
    """Store whether a user applied or skipped a job for analytics."""
    try:
        result = user_store.upsert_user_application(user_id, payload.model_dump())
        _invalidate_dashboard_summary(user_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/applications")
async def list_user_applications(user_id: str = Depends(current_user_id)):
    return user_store.list_user_applications(user_id)


@router.get("/tailor-queue")
async def list_tailor_queue(user_id: str = Depends(current_user_id)):
    items = user_store.list_tailor_queue(user_id)
    for item in items:
        try:
            ats = int(item.get("ats_score") or 0)
            match = int(item.get("match_score") or 0)
        except Exception:
            ats = 0
            match = 0
        if ats and match and ats < match:
            item["raw_ats_score"] = ats
            item["ats_score"] = match
            item["score_guarded"] = True
    used_today = user_store.count_tailor_requests_today(user_id)
    return {
        "items": items,
        "used_today": used_today,
        "daily_limit": TAILOR_DAILY_LIMIT,
        "remaining_today": max(0, TAILOR_DAILY_LIMIT - used_today),
        "feature_enabled": bool(settings.tailor_feature_enabled),
    }


@router.post("/tailor-queue")
async def add_tailor_queue_item(payload: TailorQueueRequest = Body(...), user_id: str = Depends(current_user_id)):
    if not settings.tailor_feature_enabled:
        raise HTTPException(
            status_code=503,
            detail="Resume Tailor is temporarily unavailable while we improve output quality. Check back soon.",
        )
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
    if not settings.tailor_feature_enabled:
        raise HTTPException(
            status_code=503,
            detail="Resume Tailor is temporarily unavailable while we improve output quality. Check back soon.",
        )
    item = user_store.get_tailor_queue_item(user_id, queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Tailor queue item not found")
    active_resume = _active_resume_row(user_id)
    resume_text = (active_resume or {}).get("parsed_text") or ""
    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="Upload or re-upload an active resume before tailoring.")
    resume_json = (active_resume or {}).get("parsed_json") or {}
    if not isinstance(resume_json, dict):
        resume_json = {}
    # Derive from raw text whenever ANY section the tailored document needs is
    # missing (older resumes often have experience but no education/projects/
    # certifications arrays), then merge only the gaps. This is why tailored
    # files used to arrive with whole sections missing.
    _tailor_keys = ("experience", "education", "projects", "certifications", "skills", "summary", "sections", "contact")
    from app.services.resume_parser import resume_json_looks_shattered
    if resume_json_looks_shattered(resume_json):
        # Word-per-line legacy JSON poisons tailored output — rebuild fully.
        resume_json = {}
    if any(not resume_json.get(k) for k in _tailor_keys):
        try:
            from app.services.resume_parser import resume_text_to_json
            derived = resume_text_to_json(
                resume_text,
                metadata={
                    "filename": (active_resume or {}).get("name"),
                    "derived_for_tailor": True,
                },
            )
            if isinstance(derived, dict):
                resume_json = dict(resume_json)
                for k in _tailor_keys:
                    if not resume_json.get(k) and derived.get(k):
                        resume_json[k] = derived[k]
        except Exception as exc:
            log.warning("Tailor resume_json derivation failed for %s: %s", user_id, exc)

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

    # Primary path: LLM tailoring (work-auth filter, match diagnostic, honest
    # red-flag reframing, human-sounding rewrite per the tailor spec). Falls
    # back to the deterministic builder if Groq is unavailable or returns
    # unusable output — generation never breaks.
    tailored_resume = None
    diagnostics = None
    engine = "deterministic"
    llm_out = None
    llm_provider = ""
    # Primary path: the private OpenClaw service running Ollama Cloud
    # glm-5.2:cloud — the same engine One-Click Apply uses, so Tailor and
    # One-Click produce identical-quality documents. Falls back to the Groq
    # tailor spec, then deterministic — generation never breaks.
    try:
        from app.services.apply.openclaw_tailor import tailor_with_openclaw

        openclaw_out = await tailor_with_openclaw(
            resume_text=resume_text,
            job=job_data,
            profile={
                "full_name": f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip(),
                "visa_status": str(user.get("visa_status") or "Not specified"),
            },
        )
        if openclaw_out and isinstance(openclaw_out.get("resume_spec"), dict):
            llm_out = openclaw_out["resume_spec"]
            llm_provider = "ollama-cloud/glm-5.2"
    except Exception as exc:  # noqa: BLE001 — degrade to Groq/deterministic
        log.warning("OpenClaw tailoring unavailable for %s: %s", user_id, exc)
    if llm_out is None:
        try:
            from app.services.resume_tailor_llm import tailor_resume as _llm_tailor
            llm_out = await _llm_tailor(
                resume_text=resume_text,
                job_title=str(job_data.get("title") or ""),
                job_company=str(job_data.get("company") or ""),
                job_description=str(job_data.get("description") or ""),
                work_auth=str(user.get("visa_status") or "Not specified"),
            )
            if llm_out:
                llm_provider = "groq"
        except Exception as exc:  # noqa: BLE001 — degrade to deterministic
            log.warning("LLM tailoring unavailable for %s: %s", user_id, exc)
            llm_out = None
    llm_payload = None
    if llm_out:
        llm_payload = _payload_from_llm(llm_out, job_data, user, resume_text)
        if llm_payload:
            engine = "llm"
            diagnostics = {k: llm_out.get(k) for k in ("work_auth", "match", "red_flags") if llm_out.get(k) is not None}
            if llm_provider:
                diagnostics["provider"] = llm_provider
    deterministic_payload = _build_tailored_resume_payload(resume_text, resume_json, job_data, matched, missing, user)
    conservative_payload = _build_original_preserving_tailored_payload(resume_text, resume_json, job_data, matched, missing, user)
    current_match_score = max(0, min(100, int(item.get("match_score") or 0)))
    tailored_resume, projected_score, engine, score_diagnostics = _select_tailored_resume_payload(
        llm_payload=llm_payload,
        deterministic_payload=deterministic_payload,
        conservative_payload=conservative_payload,
        resume_text=resume_text,
        job_text=job_text,
        current_match_score=current_match_score,
    )
    diagnostics = {**(diagnostics or {}), **score_diagnostics}

    # The LLM payload never carries Projects and often returns thin Education /
    # Certifications, so generated files were missing whole sections. Backfill
    # anything absent from the deterministic build, which always derives its
    # sections from the user's actual resume content.
    for _key in ("projects", "education", "certifications", "skill_groups", "contact"):
        if not tailored_resume.get(_key) and deterministic_payload.get(_key):
            tailored_resume[_key] = deterministic_payload[_key]

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
        "matched_keywords": _display_terms(matched),
        "keyword_targets": _display_terms(missing[:12]),
        "engine": engine,
        "diagnostics": diagnostics,
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
                "links": parsed.get("links") or [],
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

    def _firestore_safe(value, depth: int = 0):
        """Coerce parsed JSON to Firestore-storable primitives.

        Firestore rejects nested arrays and non-primitive types; a single bad
        node made the whole resume save fail with a 500, which users saw as
        "my resume never saved". Round-trip defensively instead of failing.
        """
        if depth > 12:
            return str(value)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): _firestore_safe(v, depth + 1) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            out = []
            for item in value:
                coerced = _firestore_safe(item, depth + 1)
                # Firestore cannot store arrays inside arrays.
                out.append(", ".join(map(str, coerced)) if isinstance(coerced, list) else coerced)
            return out
        return str(value)

    import json as _json

    safe_json = _firestore_safe(parsed_json) if isinstance(parsed_json, dict) else {}
    # Firestore documents cap at ~1 MiB. parsed_text is capped in the store,
    # but parsed_json was unbounded: large resumes doubled or tripled the
    # payload and the write failed, so the resume silently never appeared in
    # the user's account. Trim progressively until the document fits.
    def _json_bytes(value) -> int:
        try:
            return len(_json.dumps(value, ensure_ascii=False).encode("utf-8"))
        except Exception:
            return 1 << 22
    if _json_bytes(safe_json) > 350_000:
        trimmed = dict(safe_json)
        for key in ("sections", "experience", "projects", "education", "certifications", "keywords", "skills"):
            if _json_bytes(trimmed) <= 350_000:
                break
            if isinstance(trimmed.get(key), list):
                trimmed[key] = trimmed[key][:40]
            elif isinstance(trimmed.get(key), dict):
                trimmed[key] = {k: (v[:40] if isinstance(v, list) else v) for k, v in list(trimmed[key].items())[:12]}
        safe_json = trimmed if _json_bytes(trimmed) <= 350_000 else {"summary": trimmed.get("summary"), "skills": (trimmed.get("skills") or [])[:40]}

    attempts = (
        {"parsed_text": parsed_text, "parsed_json": safe_json},
        {"parsed_text": parsed_text[:150_000], "parsed_json": {}},
    )
    row = None
    last_exc: Exception | None = None
    for attempt in attempts:
        try:
            row = user_store.create_resume(
                user_id,
                name=filename,
                score=score,
                size_bytes=len(content),
                active=True,
                storage_path=None,
                **attempt,
            )
            break
        except Exception as exc:  # noqa: BLE001 — retry smaller before failing
            last_exc = exc
            log.warning("Resume save attempt failed for %s (%s); retrying smaller.", user_id, exc)
    if row is None:
        log.error("Resume save failed for %s after retries: %s", user_id, last_exc)
        raise HTTPException(status_code=500, detail="Could not save your resume. Please try again or contact support.")
    _invalidate_dashboard_summary(user_id)
    _invalidate_jobs_context(user_id)
    return _to_resume_meta(row)


@router.post("/resumes/{resume_id}/activate", response_model=ResumeMetadata)
async def activate_user_resume(resume_id: str, user_id: str = Depends(current_user_id)):
    row = user_store.set_active_resume(user_id, resume_id)
    if not row:
        raise HTTPException(status_code=404, detail="Resume not found")
    _invalidate_dashboard_summary(user_id)
    _invalidate_jobs_context(user_id)
    return _to_resume_meta(row)


@router.delete("/resumes/{resume_id}")
async def delete_user_resume(resume_id: str, user_id: str = Depends(current_user_id)):
    deleted = user_store.delete_resume(user_id, resume_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Resume not found")
    _invalidate_dashboard_summary(user_id)
    _invalidate_jobs_context(user_id)
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
        # Re-derive on the fly when the stored JSON is missing (resumes
        # uploaded before parsed_json existed) OR shattered (uploaded before
        # the word-per-line PDF repair — each section item was a single word,
        # which rendered a broken one-word-per-line document).
        from app.services.resume_parser import RESUME_SCHEMA_VERSION, resume_json_looks_shattered
        needs_derive = (
            not (resume_json.get("sections") or resume_json.get("experience") or resume_json.get("summary"))
            or resume_json_looks_shattered(resume_json)
            or not resume_json.get("experience_details")
            or resume_json.get("schema_version") != RESUME_SCHEMA_VERSION
        )
        if needs_derive:
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
    experience_details = _extract_experience_details(resume_json)
    past_companies = [
        item["company"] for item in experience_details
        if item.get("company")
    ] or _extract_past_companies(resume_json.get("experience") or [])

    return {
        "has_resume": True,
        "name": active.get("name"),
        "score": active.get("score"),
        "skills": sorted(set(skills)),
        "keywords": keywords[:30],
        "resume_json": resume_json,
        "quick_wins": suggestions,
        "target_roles": target_roles,
        "past_companies": past_companies,
        "experience_details": experience_details,
    }
