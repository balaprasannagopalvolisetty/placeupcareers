"""
PlaceUp Career — Shared job taxonomy.

Single source of truth used by:
  - The scraper (each role/synonym becomes a query keyword)
  - The categorizer that tags scraped jobs into UI categories
  - The frontend's /api/jobs/taxonomy endpoint that powers the
    category sidebar + filter chips on the Jobs page.

Each role lists `synonyms` (used to broaden scrape queries and to
match incoming job titles to a category) and visa eligibility tags
matching the badges shown in the UI.

International student-friendly = these are roles where OPT/STEM/H-1B
sponsorship is realistic. Pure-domestic-only roles are intentionally
omitted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    name: str
    synonyms: tuple[str, ...]
    visa: tuple[str, ...]
    hot: bool = False


@dataclass(frozen=True)
class Category:
    name: str
    icon: str  # lucide-react name
    roles: tuple[Role, ...]


CATEGORIES: tuple[Category, ...] = (
    Category("Technology & Engineering", "Cpu", (
        Role("Software Engineer",       ("software engineer", "software developer", "swe", "backend engineer", "frontend engineer", "full stack engineer", "full-stack engineer", "web developer", "java developer", "python developer", "application developer", "mobile engineer", "ios engineer", "android engineer"), ("OPT","STEM","H-1B"), hot=True),
        Role("Frontend Engineer",       ("frontend engineer", "front end engineer", "front-end engineer", "frontend developer", "front end developer", "react developer", "ui engineer", "web frontend engineer"), ("OPT","STEM","H-1B"), hot=True),
        Role("Backend Engineer",        ("backend engineer", "back end engineer", "back-end engineer", "backend developer", "api engineer", "server side engineer", "java backend engineer", "python backend engineer"), ("OPT","STEM","H-1B"), hot=True),
        Role("Full Stack Engineer",     ("full stack engineer", "full-stack engineer", "fullstack engineer", "full stack developer", "full-stack developer", "mern stack developer", "web application developer"), ("OPT","STEM","H-1B"), hot=True),
        Role("Data Engineer",           ("data engineer", "etl engineer", "analytics engineer", "data platform engineer", "big data engineer", "data warehouse engineer", "pipeline engineer"), ("OPT","STEM","H-1B"), hot=True),
        Role("Machine Learning Engineer",("machine learning engineer", "ml engineer", "machine learning", "ml platform", "mlops engineer", "ai engineer", "genai engineer", "computer vision engineer", "nlp engineer"), ("OPT","STEM","H-1B"), hot=True),
        Role("Data Scientist",          ("data scientist", "applied scientist", "research scientist data", "decision scientist", "machine learning scientist"), ("OPT","STEM","H-1B"), hot=True),
        Role("DevOps / Cloud Engineer", ("devops engineer", "site reliability engineer", "sre", "cloud engineer", "platform engineer", "infrastructure engineer"), ("OPT","STEM","H-1B")),
        Role("Cybersecurity Analyst",   ("cybersecurity analyst", "security engineer", "soc analyst", "security analyst", "information security analyst"), ("OPT","STEM","H-1B")),
        Role("Security Engineer",       ("security engineer", "application security engineer", "appsec engineer", "cloud security engineer", "product security engineer", "security software engineer"), ("OPT","STEM","H-1B"), hot=True),
        Role("QA / Test Engineer",      ("qa engineer", "test engineer", "sdet", "automation engineer", "quality assurance engineer", "quality engineer", "test automation engineer"), ("OPT","STEM","H-1B")),
        Role("Systems Engineer",        ("systems engineer", "system engineer", "embedded engineer", "firmware engineer", "mbse engineer"), ("OPT","STEM","H-1B")),
        Role("Network Engineer",        ("network engineer", "network administrator", "network analyst", "noc engineer", "telecom engineer"), ("OPT","STEM","H-1B")),
        Role("Database Administrator",  ("database administrator", "dba", "database engineer"), ("OPT","STEM","H-1B")),
        Role("Solutions Architect",     ("solutions architect", "solution architect", "cloud architect", "technical architect", "enterprise architect"), ("OPT","STEM","H-1B"), hot=True),
        Role("CRM / ERP Developer",     ("salesforce developer", "servicenow developer", "sap developer", "oracle developer", "erp developer", "crm developer"), ("OPT","STEM","H-1B")),
        Role("IT Support / Analyst",    (
            "it support", "it support specialist", "it support technician", "it support analyst", "it support assistant",
            "it technician", "it analyst", "it systems analyst", "helpdesk analyst", "help desk analyst",
            "helpdesk technician", "help desk technician", "service desk analyst", "service desk technician",
            "desktop support", "desktop support analyst", "desktop support technician",
            "technical support engineer", "technical support specialist", "computer support specialist", "support analyst",
        ), ("OPT","H-1B")),
        Role("Product Manager (Tech)",  ("product manager", "technical product manager", "tpm", "associate product manager"), ("OPT","H-1B"), hot=True),
        Role("UI/UX Designer",          ("ui designer", "ux designer", "product designer", "interaction designer"), ("OPT","H-1B")),
        Role("Blockchain Developer",    ("blockchain developer", "smart contract engineer", "web3 engineer", "solidity developer"), ("OPT","STEM","H-1B")),
        Role("AI Research Scientist",   ("ai research scientist", "research scientist machine learning", "deep learning researcher", "research engineer ai", "research engineer machine learning"), ("OPT","STEM","H-1B","Vol")),
    )),
    Category("Data & Analytics", "BarChart3", (
        Role("Business Analyst",        ("business analyst", "business systems analyst"), ("OPT","H-1B"), hot=True),
        Role("Data Analyst",            ("data analyst", "marketing analyst", "operations analyst"), ("OPT","STEM","H-1B"), hot=True),
        Role("Business Intelligence Developer", ("bi developer", "business intelligence developer", "tableau developer", "power bi developer"), ("OPT","STEM","H-1B")),
        Role("Analytics Engineer",      ("analytics engineer", "dbt developer", "data modeling analyst", "semantic layer engineer"), ("OPT","STEM","H-1B"), hot=True),
        Role("Quantitative Analyst",    ("quantitative analyst", "quant analyst", "quant researcher", "quantitative researcher", "quantitative developer"), ("OPT","STEM","H-1B")),
        Role("Research Analyst",        ("research analyst", "market research analyst", "user research analyst", "policy research analyst"), ("OPT","H-1B","Vol")),
        Role("Operations Research Analyst", ("operations research analyst", "or analyst"), ("OPT","STEM","H-1B")),
        Role("Statistician",            ("statistician", "biostatistician"), ("OPT","STEM","H-1B")),
    )),
    Category("Finance & Accounting", "DollarSign", (
        Role("Financial Analyst",       ("financial analyst", "fp&a analyst", "corporate finance analyst"), ("OPT","H-1B"), hot=True),
        Role("Investment Banking Analyst",("investment banking analyst", "ib analyst"), ("OPT","H-1B")),
        Role("Accountant / CPA",        ("accountant", "staff accountant", "senior accountant", "auditor"), ("OPT","H-1B"), hot=True),
        Role("Risk Analyst",            ("risk analyst", "credit risk analyst", "operational risk analyst"), ("OPT","H-1B")),
        Role("Financial Consultant",    ("financial consultant", "wealth management analyst"), ("OPT","H-1B")),
        Role("Actuary",                 ("actuary", "actuarial analyst"), ("OPT","STEM","H-1B")),
        Role("Compliance Analyst",      ("compliance analyst", "kyc analyst", "aml analyst"), ("OPT","H-1B")),
        Role("Treasury Analyst",        ("treasury analyst",), ("OPT","H-1B")),
        Role("Tax Analyst",             ("tax analyst", "tax associate", "international tax analyst"), ("OPT","H-1B")),
    )),
    Category("Healthcare & Biotech", "Activity", (
        Role("Clinical Research Associate", ("clinical research associate", "cra", "clinical trial associate"), ("OPT","STEM","H-1B")),
        Role("Biomedical Engineer",     ("biomedical engineer", "medical device engineer"), ("OPT","STEM","H-1B")),
        Role("Pharmaceutical Scientist", ("pharmaceutical scientist", "drug discovery scientist", "formulation scientist"), ("OPT","STEM","H-1B")),
        Role("Healthcare Data Analyst",  ("healthcare data analyst", "clinical data analyst"), ("OPT","STEM","H-1B")),
        Role("Bioinformatics Scientist", ("bioinformatics scientist", "computational biologist", "genomics scientist"), ("OPT","STEM","H-1B")),
        Role("Regulatory Affairs Specialist", ("regulatory affairs specialist", "regulatory affairs associate"), ("OPT","H-1B")),
        Role("Public Health Analyst",   ("public health analyst", "epidemiologist"), ("OPT","H-1B","Vol")),
        Role("Lab Technician / Research Assistant", ("lab technician", "research assistant", "laboratory technician"), ("OPT","STEM","Vol")),
        Role("Medical Technologist",    ("medical technologist", "clinical laboratory scientist", "medical laboratory scientist"), ("OPT","STEM","H-1B")),
    )),
    Category("Mechanical & Civil Engineering", "Wrench", (
        Role("Mechanical Engineer",     ("mechanical engineer", "mechanical design engineer", "design engineer mechanical", "product design engineer", "hvac engineer"), ("OPT","STEM","H-1B"), hot=True),
        Role("Civil Engineer",          ("civil engineer", "civil designer", "transportation engineer", "land development engineer", "water resources engineer"), ("OPT","STEM","H-1B")),
        Role("Electrical Engineer",     ("electrical engineer", "power engineer", "electronics engineer", "hardware engineer", "battery engineer", "controls engineer"), ("OPT","STEM","H-1B")),
        Role("Chemical Engineer",       ("chemical engineer", "process engineer", "process development engineer", "materials engineer"), ("OPT","STEM","H-1B")),
        Role("Industrial Engineer",     ("industrial engineer", "manufacturing engineer", "manufacturing process engineer", "quality manufacturing engineer", "lean engineer"), ("OPT","STEM","H-1B")),
        Role("Aerospace Engineer",      ("aerospace engineer", "aeronautical engineer"), ("OPT","STEM","H-1B")),
        Role("Environmental Engineer",  ("environmental engineer",), ("OPT","STEM","H-1B")),
        Role("Structural Engineer",     ("structural engineer", "structural designer", "bridge engineer"), ("OPT","STEM","H-1B")),
    )),
    Category("Business & Management", "Briefcase", (
        Role("Management Consultant",   ("management consultant", "strategy consultant", "business consultant"), ("OPT","H-1B"), hot=True),
        Role("Operations Manager",      ("operations manager", "ops manager"), ("OPT","H-1B")),
        Role("Project Manager",         ("project manager", "program manager", "delivery manager"), ("OPT","H-1B"), hot=True),
        Role("Supply Chain Analyst",    ("supply chain analyst", "logistics analyst", "procurement analyst"), ("OPT","STEM","H-1B")),
        Role("Human Resources Generalist", ("hr generalist", "hr business partner", "people operations"), ("OPT","H-1B")),
        Role("Strategy Analyst",        ("strategy analyst", "corporate strategy analyst", "business strategy analyst", "strategic planning analyst"), ("OPT","H-1B")),
        Role("Scrum Master / Agile Coach", ("scrum master", "agile coach", "agile project manager"), ("OPT","H-1B")),
        Role("Technical Program Manager", ("technical program manager", "tpm program manager", "engineering program manager"), ("OPT","H-1B"), hot=True),
    )),
    Category("Marketing & Communications", "Megaphone", (
        Role("Digital Marketing Analyst", ("digital marketing analyst", "performance marketing analyst", "seo analyst", "paid search analyst", "marketing analyst"), ("OPT","H-1B")),
        Role("Content Strategist",      ("content strategist", "content marketing manager"), ("OPT","H-1B")),
        Role("Marketing Data Analyst",  ("marketing data analyst", "marketing analytics manager"), ("OPT","STEM","H-1B")),
        Role("Social Media Manager",    ("social media manager", "community manager"), ("OPT","H-1B")),
        Role("Brand Manager",           ("brand manager", "associate brand manager"), ("OPT","H-1B")),
        Role("Growth Hacker / Growth Analyst", ("growth analyst", "growth marketing manager", "growth hacker"), ("OPT","STEM","H-1B")),
        Role("Marketing Operations Specialist", ("marketing operations specialist", "marketing automation specialist", "crm marketing specialist", "salesforce marketing cloud specialist"), ("OPT","H-1B")),
    )),
    Category("Education & Research", "GraduationCap", (
        Role("Research Assistant / Associate", ("research associate", "research assistant", "graduate research assistant", "lab research assistant"), ("OPT","STEM","H-1B","Vol")),
        Role("Teaching Assistant",      ("teaching assistant", "graduate teaching assistant", "ta instructor"), ("OPT","Vol")),
        Role("Instructional Designer",  ("instructional designer", "learning designer"), ("OPT","H-1B")),
        Role("Education Program Coordinator", ("education program coordinator", "academic program coordinator"), ("OPT","Vol","H-1B")),
        Role("Academic Advisor",        ("academic advisor", "student success advisor"), ("OPT","H-1B")),
        Role("ESL / Language Instructor", ("esl instructor", "english instructor", "language instructor"), ("OPT","Vol")),
    )),
    Category("Government & Policy", "Landmark", (
        Role("Policy Analyst",          ("policy analyst", "public policy analyst", "legislative analyst"), ("OPT","H-1B","Vol")),
        Role("Government IT Specialist", ("government it specialist", "federal it specialist", "information technology specialist", "it specialist government", "public sector it specialist"), ("OPT","STEM","H-1B")),
        Role("Intelligence Analyst",    ("intelligence analyst",), ("OPT","H-1B")),
        Role("Urban / City Planner",    ("urban planner", "city planner"), ("OPT","STEM","H-1B")),
        Role("Environmental Policy Analyst", ("environmental policy analyst", "climate policy analyst"), ("OPT","H-1B","Vol")),
        Role("Grant Writer / Nonprofit Program Manager", ("grant writer", "nonprofit program manager"), ("OPT","Vol")),
    )),
    Category("Design & Creative", "Palette", (
        Role("Product / UX Designer",   ("product designer", "ux designer", "ui ux designer", "ui/ux designer", "user experience designer"), ("OPT","H-1B"), hot=True),
        Role("Graphic Designer",        ("graphic designer", "visual designer"), ("OPT","H-1B")),
        Role("Video / Motion Designer", ("motion designer", "video editor", "motion graphics designer"), ("OPT","H-1B")),
        Role("Architect",               ("architect", "junior architect", "intern architect"), ("OPT","STEM","H-1B")),
        Role("Game Designer / Developer", ("game designer", "game developer", "unity developer", "unreal developer"), ("OPT","STEM","H-1B")),
    )),
    Category("Legal & Compliance", "Scale", (
        Role("Paralegal",               ("paralegal", "legal assistant"), ("OPT","H-1B")),
        Role("Contract Analyst",        ("contract analyst", "contract manager"), ("OPT","H-1B")),
        Role("Immigration Paralegal",   ("immigration paralegal", "immigration legal assistant"), ("OPT","H-1B"), hot=True),
        Role("IP / Patent Analyst",     ("patent analyst", "ip analyst", "patent agent"), ("OPT","STEM","H-1B")),
        Role("Compliance Officer",      ("compliance officer", "compliance manager"), ("OPT","H-1B")),
    )),
    Category("Volunteer & OPT-qualifying", "Heart", (
        Role("Nonprofit Program Assistant", ("nonprofit program assistant", "nonprofit coordinator", "nonprofit program coordinator", "program assistant nonprofit", "program coordinator nonprofit", "nonprofit", "non-profit", "program assistant", "program coordinator"), ("OPT","Vol")),
        Role("Open Source Contributor", ("open source contributor", "open source maintainer", "open source engineer", "open source developer", "developer advocate open source", "open source", "developer advocate", "github maintainer"), ("OPT","STEM","Vol")),
        Role("University Research Volunteer", ("research volunteer", "university research volunteer", "clinical research volunteer", "student research volunteer", "research lab volunteer", "research assistant", "student research", "clinical research assistant"), ("OPT","STEM","Vol")),
        Role("Community Tech Educator", ("tech educator", "coding instructor", "stem volunteer"), ("OPT","Vol")),
        Role("Health Clinic Volunteer", ("clinic volunteer", "hospital volunteer"), ("OPT","Vol")),
        Role("Environmental Volunteer", ("environmental volunteer", "conservation volunteer", "environmental program coordinator", "environmental program assistant", "conservation coordinator", "sustainability volunteer"), ("OPT","Vol")),
        Role("Legal Aid Volunteer",     ("legal aid volunteer", "legal aid intern", "legal volunteer", "pro bono intern", "legal clinic volunteer", "legal intern", "pro bono", "legal aid"), ("OPT","Vol")),
        Role("UN / International Org Intern", ("united nations intern", "international organization intern", "un intern", "un internship", "intern united nations", "intergovernmental affairs intern", "united nations", "programme management intern", "public administration intern", "international affairs intern", "international organization", "ngo intern"), ("OPT","H-1B","Vol")),
    )),
)


# ─── Synonym expansion ─────────────────────────────────────────────────
#
# Job boards rarely post a role as exactly "Software Engineer" — they
# post "Senior Software Engineer", "Software Engineer II", "Staff
# Backend Engineer", etc. The synonyms in CATEGORIES are the BASE
# titles; this expansion adds the common seniority/level prefixes
# that every modern HR system uses so the scraper's title matcher
# can recognize them as the same role.
#
# We expand at call sites (not in CATEGORIES) so the UI role pickers
# stay tidy with the 88 canonical names while the scraper still has
# the full firehose of ~600+ matchable variants.

SENIORITY_PREFIXES: tuple[str, ...] = (
    "junior", "associate", "entry level", "entry-level", "new grad", "new graduate",
    "senior", "sr", "sr.", "staff", "principal", "lead", "head of",
)

LEVEL_SUFFIXES: tuple[str, ...] = (
    "i", "ii", "iii", "iv", "1", "2", "3", "4",
    "intern", "internship", "co-op", "coop", "apprentice", "trainee",
)

# Extra modern-day synonyms NOT covered by CATEGORIES that we want the
# scraper / title matcher to also catch. Each entry is
# (canonical_role_name, extra_synonyms).
EXTRA_ROLE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Software Engineer": (
        "software development engineer", "sde", "sde i", "sde ii", "sde iii",
        "developer", "applications engineer", "platform software engineer",
        "associate software engineer", "engineer i", "engineer ii",
        "software engineer ii", "software engineer iii",
    ),
    "Frontend Engineer": (
        "frontend software engineer", "front end software engineer", "react engineer",
        "javascript engineer", "typescript engineer", "ui software engineer",
    ),
    "Backend Engineer": (
        "backend software engineer", "back end software engineer", "server engineer",
        "api developer", "microservices engineer", "distributed systems engineer",
    ),
    "Full Stack Engineer": (
        "full stack software engineer", "fullstack software engineer",
        "full-stack software engineer", "node react developer",
    ),
    "Machine Learning Engineer": (
        "ai/ml engineer", "ai ml engineer", "ml ops engineer", "generative ai engineer",
        "applied ml engineer", "ml infrastructure engineer",
    ),
    "Data Engineer": (
        "data infrastructure engineer", "data ops engineer", "dataops engineer",
        "analytics platform engineer",
    ),
    "DevOps / Cloud Engineer": (
        "aws engineer", "azure engineer", "gcp engineer", "kubernetes engineer",
        "reliability engineer", "production engineer", "build engineer",
    ),
    "Solutions Architect": (
        "aws solutions architect", "azure solutions architect", "gcp solutions architect",
        "customer engineer", "pre sales engineer", "sales engineer technical",
    ),
    "Network Engineer": (
        "junior network engineer", "network operations engineer", "network support engineer",
    ),
    "CRM / ERP Developer": (
        "salesforce administrator", "salesforce admin", "servicenow administrator",
        "netsuite developer", "workday analyst",
    ),
    "Data Scientist": (
        "ml scientist", "research scientist", "quantitative scientist",
        "applied ai scientist",
    ),
    "Product Manager (Tech)": (
        "product owner", "senior product manager", "principal product manager",
        "group product manager", "associate product manager",
    ),
    "Cybersecurity Analyst": (
        "application security engineer", "appsec engineer", "cloud security engineer",
        "security operations analyst", "threat intel analyst",
    ),
    "Security Engineer": (
        "security developer", "security automation engineer", "detection engineer",
        "devsecops engineer", "information security engineer",
    ),
    "Business Analyst": (
        "business intelligence analyst", "operations analyst", "process analyst",
        "junior business analyst",
    ),
    "Analytics Engineer": (
        "senior analytics engineer", "junior analytics engineer", "data modeler",
        "dbt analytics engineer",
    ),
    "Financial Analyst": (
        "associate financial analyst", "senior financial analyst", "corporate financial analyst",
        "fp&a", "fp and a analyst",
    ),
    "Project Manager": (
        "technical program manager", "agile project manager", "associate project manager",
        "junior project manager", "it project manager",
    ),
    "Technical Program Manager": (
        "technical project manager", "program manager technical", "release program manager",
    ),
    "Mechanical Engineer": (
        "associate mechanical engineer", "senior mechanical engineer", "mechanical design engineer ii",
    ),
    "Electrical Engineer": (
        "associate electrical engineer", "senior electrical engineer", "rf engineer",
        "embedded electrical engineer",
    ),
    "Civil Engineer": (
        "associate civil engineer", "senior civil engineer", "geotechnical engineer",
    ),
    "Digital Marketing Analyst": (
        "growth marketing analyst", "performance marketing manager", "ppc analyst",
    ),
    "Research Assistant / Associate": (
        "postdoctoral researcher", "postdoc researcher", "phd research assistant",
    ),
}


def _expand_with_seniority(base: str) -> list[str]:
    """Generate Senior/Staff/Junior/level prefixes for a base title."""
    base = base.strip()
    if not base:
        return []
    low = base.lower()
    out: list[str] = [base]
    # Skip prefixing titles that already contain a seniority marker — would
    # produce "senior senior X" gibberish.
    if any(p in low for p in SENIORITY_PREFIXES):
        return out
    for p in SENIORITY_PREFIXES:
        out.append(f"{p} {base}")
    # Level suffixes (only for titles that look like engineering roles —
    # nonsensical for "Paralegal II", "Treasury Analyst IV", etc).
    if any(t in low for t in ("engineer", "developer", "scientist", "analyst", "designer")):
        for suf in LEVEL_SUFFIXES:
            out.append(f"{base} {suf}")
    return out


def all_search_terms() -> list[str]:
    """All synonyms across every role + a sponsorship-keyword variant for each."""
    seen: set[str] = set()
    out: list[str] = []
    for cat in CATEGORIES:
        for role in cat.roles:
            # Base synonyms straight from CATEGORIES.
            for syn in (role.name, *role.synonyms, *EXTRA_ROLE_SYNONYMS.get(role.name, ())):
                key = syn.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(syn)
            # Plus modern-day aliases we want the scraper to recognize.
            for extra in EXTRA_ROLE_SYNONYMS.get(role.name, ()):
                key = extra.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(extra)
            # Plus auto-generated seniority + level variants for the
            # canonical name. This catches "Senior Software Engineer",
            # "Software Engineer II", etc. without us having to enumerate
            # every combination by hand.
            for variant in _expand_with_seniority(role.name):
                key = variant.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(variant)
    # Add a visa-friendly variant for the most popular roles to bias toward sponsoring employers.
    sponsorship_terms = [
        "software engineer visa sponsorship",
        "data scientist OPT friendly",
        "machine learning engineer H1B",
        "data engineer visa sponsor",
        "frontend developer OPT",
        "backend engineer H1B",
        "product manager visa sponsorship",
        "business analyst OPT",
        "financial analyst visa sponsor",
        "mechanical engineer H1B",
    ]
    for s in sponsorship_terms:
        if s.lower() not in seen:
            out.append(s)
            seen.add(s.lower())
    return out


def all_role_names() -> list[str]:
    """Canonical UI role names across every category."""
    return [role.name for cat in CATEGORIES for role in cat.roles]


def all_role_backfill_search_terms() -> list[str]:
    """Focused cloud backfill queries for every visible category role.

    The 6h scraper intentionally casts a wide early-career net. This list is
    narrower and role-by-role so production can fill each Jobs-page category
    position without relying on one broad query to happen to cover it.
    """
    seen: set[str] = set()
    out: list[str] = []

    def add(term: str) -> None:
        clean = " ".join((term or "").replace("/", " ").split())
        key = clean.lower()
        if len(clean) >= 3 and key not in seen:
            seen.add(key)
            out.append(clean)

    for cat in CATEGORIES:
        for role in cat.roles:
            add(role.name)
            for synonym in role.synonyms[:2]:
                add(synonym)
            if cat.name == "Volunteer & OPT-qualifying":
                for synonym in role.synonyms:
                    add(synonym)
    return out


def all_taxonomy_scrape_search_terms() -> list[str]:
    """Comprehensive scheduled scrape queries for every Jobs-page position.

    This is intentionally role/synonym based, not prefix-heavy. The scraper
    already filters roles down to 0-10 years after fetch, so broad role terms
    collect more complete source coverage than hundreds of narrow "entry level"
    variants that many job boards do not index consistently.
    """
    seen: set[str] = set()
    out: list[str] = []

    def add(term: str) -> None:
        clean = " ".join((term or "").replace("/", " ").split())
        key = clean.lower()
        if len(clean) >= 3 and key not in seen:
            seen.add(key)
            out.append(clean)

    for cat in CATEGORIES:
        for role in cat.roles:
            add(role.name)
            for synonym in role.synonyms:
                add(synonym)

    coverage_terms = [
        "entry level visa sponsorship",
        "junior OPT friendly",
        "new grad H1B sponsor",
        "associate OPT STEM",
        "internship OPT",
        "visa sponsorship",
        "H1B sponsor",
        "OPT eligible",
        "STEM OPT",
        "early career",
        "new graduate",
    ]
    for term in coverage_terms:
        add(term)

    return out


def all_early_career_search_terms() -> list[str]:
    """Search terms biased toward 0-10 year roles across the taxonomy."""
    seen: set[str] = set()
    out: list[str] = []
    prefixes = ("entry level", "junior", "associate", "new grad")
    suffixes = ("0-10 years",)

    def add(term: str) -> None:
        key = " ".join(term.lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(term)

    for cat in CATEGORIES:
        for role in cat.roles:
            add(role.name)
            for prefix in prefixes:
                add(f"{prefix} {role.name}")
            for suffix in suffixes:
                add(f"{role.name} {suffix}")
            for synonym in role.synonyms:
                add(synonym)

    sponsorship_terms = [
        "entry level visa sponsorship",
        "junior OPT friendly",
        "new grad H1B sponsor",
        "associate OPT STEM",
        "0-2 years visa sponsorship",
        "3-5 years H1B sponsor",
        "5-10 years visa sponsor",
    ]
    for term in sponsorship_terms:
        add(term)
    return out


def categorize(title: str) -> tuple[str, str]:
    """Return (category_name, role_name) best match for an incoming job title."""
    if not title:
        return ("Other", "Other")
    t = title.lower()
    best: tuple[int, str, str] = (0, "Other", "Other")
    for cat in CATEGORIES:
        for role in cat.roles:
            for syn in role.synonyms:
                needle = syn.lower()
                if len(needle) <= 4:
                    matched = bool(re.search(rf"\b{re.escape(needle)}\b", t))
                else:
                    matched = needle in t
                if matched:
                    score = len(syn)  # prefer longest match
                    if score > best[0]:
                        best = (score, cat.name, role.name)
    return (best[1], best[2])


def to_payload() -> dict:
    """Serialize the full taxonomy for the frontend."""
    return {
        "categories": [
            {
                "name": cat.name,
                "icon": cat.icon,
                "roles": [
                    {
                        "name": role.name,
                        "synonyms": list(role.synonyms),
                        "visa": list(role.visa),
                        "hot": role.hot,
                    }
                    for role in cat.roles
                ],
            }
            for cat in CATEGORIES
        ]
    }
