"""Country-aware visa and English-friendly rules for global job ingestion.

This module is intentionally data-first. Scrapers, normalizers, API filters,
and the classifier all need the same country/program vocabulary, so keep the
shared rules here instead of scattering country-specific strings through the
pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


@dataclass(frozen=True)
class VisaProgram:
    code: str
    name: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class CountryVisaRule:
    code: str
    name: str
    english_native: bool
    programs: tuple[VisaProgram, ...]
    sponsor_sources: tuple[str, ...] = ()


TARGET_COUNTRIES: tuple[str, ...] = (
    "US", "CA", "GB", "IE", "DE", "NL", "AU", "NZ", "SG", "AE", "JP", "PT",
    "FR", "ES", "SE", "DK", "NO", "CH", "FI", "BE", "AT", "PL", "EE", "QA", "SA",
    "IT", "LU", "KR", "TW", "HK", "CZ",
)


COUNTRY_RULES: dict[str, CountryVisaRule] = {
    "US": CountryVisaRule("US", "United States", True, (
        VisaProgram("h1b", "H-1B", ("h-1b", "h1b", "h1-b", "specialty occupation")),
        VisaProgram("stem_opt", "STEM OPT", ("stem opt", "stem extension", "24-month extension")),
        VisaProgram("opt", "OPT", ("opt", "optional practical training", "f-1", "f1 visa")),
        VisaProgram("o1", "O-1", ("o-1", "extraordinary ability")),
        VisaProgram("l1", "L-1", ("l-1", "intracompany transfer")),
        VisaProgram("eb23", "EB-2/EB-3", ("green card", "perm", "permanent residency")),
    ), ("uscis_h1b", "dol_lca")),
    "CA": CountryVisaRule("CA", "Canada", True, (
        VisaProgram("lmia_work_permit", "LMIA Work Permit", ("lmia", "labour market impact assessment", "work permit support")),
        VisaProgram("global_talent_stream", "Global Talent Stream", ("global talent stream", "gts")),
        VisaProgram("express_entry", "Express Entry", ("express entry", "federal skilled worker")),
    ), ("lmia", "job_bank")),
    "GB": CountryVisaRule("GB", "United Kingdom", True, (
        VisaProgram("skilled_worker", "Skilled Worker", ("skilled worker visa", "tier 2", "certificate of sponsorship", "cos", "sponsor licence")),
        VisaProgram("global_talent", "Global Talent", ("global talent visa", "global talent")),
        VisaProgram("health_care_worker", "Health and Care Worker", ("health and care worker", "health care worker visa")),
    ), ("uk_licensed_sponsors",)),
    "IE": CountryVisaRule("IE", "Ireland", True, (
        VisaProgram("critical_skills", "Critical Skills Employment Permit", ("critical skills employment permit", "critical skills permit")),
        VisaProgram("general_employment", "General Employment Permit", ("general employment permit",)),
    ), ("ie_employment_permits",)),
    "DE": CountryVisaRule("DE", "Germany", False, (
        VisaProgram("eu_blue_card", "EU Blue Card", ("eu blue card", "blue card", "blaue karte")),
        VisaProgram("skilled_worker", "Skilled Worker Visa", ("skilled worker visa", "skilled immigration act", "feg")),
        VisaProgram("opportunity_card", "Opportunity Card", ("opportunity card", "chancenkarte")),
    )),
    "NL": CountryVisaRule("NL", "Netherlands", False, (
        VisaProgram("highly_skilled_migrant", "Highly Skilled Migrant", ("highly skilled migrant", "kennismigrant")),
        VisaProgram("eu_blue_card", "EU Blue Card", ("eu blue card", "blue card")),
    ), ("ind_recognised_sponsors",)),
    "AU": CountryVisaRule("AU", "Australia", True, (
        VisaProgram("skills_in_demand_482", "Skills in Demand (Subclass 482)", ("skills in demand", "subclass 482", "482 visa", "sid visa")),
        VisaProgram("employer_nomination_186", "Employer Nomination Scheme (Subclass 186)", ("subclass 186", "employer nomination scheme")),
        VisaProgram("skilled_nominated_190", "Skilled Nominated (Subclass 190)", ("subclass 190", "skilled nominated")),
    ), ("au_approved_sponsors",)),
    "NZ": CountryVisaRule("NZ", "New Zealand", True, (
        VisaProgram("aewv", "Accredited Employer Work Visa", ("accredited employer work visa", "aewv")),
        VisaProgram("green_list", "Green List", ("green list", "straight to residence")),
    ), ("nz_accredited_employers",)),
    "SG": CountryVisaRule("SG", "Singapore", True, (
        VisaProgram("employment_pass", "Employment Pass", ("employment pass", " ep ", "compass framework")),
        VisaProgram("s_pass", "S Pass", ("s pass", "s-pass")),
        VisaProgram("tech_pass", "Tech.Pass", ("tech.pass", "tech pass")),
    ), ("mycareersfuture",)),
    "AE": CountryVisaRule("AE", "United Arab Emirates", True, (
        VisaProgram("standard_work_permit", "Standard Work Permit", ("work permit", "employment visa", "residence visa")),
        VisaProgram("golden_visa", "Golden Visa", ("golden visa",)),
    )),
    "JP": CountryVisaRule("JP", "Japan", False, (
        VisaProgram("engineer_specialist", "Engineer/Specialist in Humanities/International Services", ("engineer/specialist", "specialist in humanities", "international services")),
        VisaProgram("highly_skilled_professional", "Highly Skilled Professional", ("highly skilled professional", "hsp")),
        VisaProgram("specified_skilled_worker", "Specified Skilled Worker", ("specified skilled worker", "ssw")),
    )),
    "PT": CountryVisaRule("PT", "Portugal", False, (
        VisaProgram("d3_highly_qualified", "D3 Highly Qualified Activity Visa", ("d3 visa", "highly qualified activity")),
        VisaProgram("tech_visa", "Tech Visa", ("tech visa",)),
    ), ("pt_tech_visa",)),
}


_EU_BLUE_CARD_COUNTRIES = ("FR", "ES", "SE", "FI", "BE", "AT", "PL", "EE", "IT", "LU", "CZ")
for _code, _name in {
    "FR": "France", "ES": "Spain", "SE": "Sweden", "FI": "Finland",
    "BE": "Belgium", "AT": "Austria", "PL": "Poland", "EE": "Estonia",
    "IT": "Italy", "LU": "Luxembourg", "CZ": "Czech Republic",
}.items():
    COUNTRY_RULES.setdefault(_code, CountryVisaRule(_code, _name, False, (
        VisaProgram("eu_blue_card", "EU Blue Card", ("eu blue card", "blue card")),
        VisaProgram("work_permit", "Work Permit", ("work permit", "visa sponsorship", "sponsorship available")),
    )))

COUNTRY_RULES.setdefault("DK", CountryVisaRule("DK", "Denmark", False, (
    VisaProgram("positive_list", "Positive List", ("positive list",)),
    VisaProgram("pay_limit_scheme", "Pay Limit Scheme", ("pay limit scheme",)),
    VisaProgram("fast_track", "Fast-track Scheme", ("fast-track scheme", "fast track scheme")),
)))
COUNTRY_RULES.setdefault("NO", CountryVisaRule("NO", "Norway", False, (
    VisaProgram("skilled_worker", "Skilled Worker Permit", ("skilled worker permit", "skilled worker")),
)))
COUNTRY_RULES.setdefault("CH", CountryVisaRule("CH", "Switzerland", False, (
    VisaProgram("work_permit", "Work Permit", ("work permit", "b permit", "l permit")),
)))
COUNTRY_RULES.setdefault("QA", CountryVisaRule("QA", "Qatar", True, (
    VisaProgram("work_residence_permit", "Work Residence Permit", ("work residence permit", "work visa", "residence permit")),
)))
COUNTRY_RULES.setdefault("SA", CountryVisaRule("SA", "Saudi Arabia", True, (
    VisaProgram("work_visa", "Work Visa", ("work visa", "employment visa")),
    VisaProgram("premium_residency", "Premium Residency", ("premium residency",)),
)))
COUNTRY_RULES.setdefault("KR", CountryVisaRule("KR", "South Korea", False, (
    VisaProgram("e7_special_occupation", "E-7 Special Occupation", ("e-7", "e7 visa", "special occupation")),
    VisaProgram("d10_job_seeker", "D-10 Job Seeker", ("d-10", "d10 visa", "job seeker visa")),
)))
COUNTRY_RULES.setdefault("TW", CountryVisaRule("TW", "Taiwan", False, (
    VisaProgram("employment_gold_card", "Employment Gold Card", ("employment gold card", "gold card")),
    VisaProgram("work_permit", "Work Permit", ("work permit", "visa sponsorship")),
)))
COUNTRY_RULES.setdefault("HK", CountryVisaRule("HK", "Hong Kong", True, (
    VisaProgram("general_employment_policy", "General Employment Policy", ("general employment policy", "gep visa")),
    VisaProgram("top_talent_pass", "Top Talent Pass", ("top talent pass", "ttps")),
)))


COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "US": ("united states", "usa", "u.s.", " u s ", "remote us", "remote, us", "new york", "california", "texas", "washington dc"),
    "CA": ("canada", "toronto", "vancouver", "ontario", "british columbia", "montreal", "ottawa"),
    "GB": ("united kingdom", " uk", "england", "london", "manchester", "scotland", "wales"),
    "IE": ("ireland", "dublin", "cork"),
    "DE": ("germany", "berlin", "munich", "hamburg", "frankfurt"),
    "NL": ("netherlands", "amsterdam", "rotterdam", "eindhoven", "utrecht"),
    "AU": ("australia", "sydney", "melbourne", "brisbane", "perth"),
    "NZ": ("new zealand", "auckland", "wellington"),
    "SG": ("singapore",),
    "AE": ("united arab emirates", "uae", "dubai", "abu dhabi"),
    "JP": ("japan", "tokyo", "osaka"),
    "PT": ("portugal", "lisbon", "porto"),
    "FR": ("france", "paris"),
    "ES": ("spain", "madrid", "barcelona"),
    "SE": ("sweden", "stockholm", "gothenburg"),
    "DK": ("denmark", "copenhagen"),
    "NO": ("norway", "oslo"),
    "CH": ("switzerland", "zurich", "geneva", "lausanne"),
    "FI": ("finland", "helsinki"),
    "BE": ("belgium", "brussels", "antwerp"),
    "AT": ("austria", "vienna"),
    "PL": ("poland", "warsaw", "krakow"),
    "EE": ("estonia", "tallinn"),
    "QA": ("qatar", "doha"),
    "SA": ("saudi arabia", "riyadh", "jeddah", "neom"),
    "IT": ("italy", "rome", "milan", "torino", "turin"),
    "LU": ("luxembourg",),
    "KR": ("south korea", "korea", "seoul", "busan"),
    "TW": ("taiwan", "taipei", "taichung"),
    "HK": ("hong kong",),
    "CZ": ("czech republic", "czechia", "prague", "brno"),
}

NON_TARGET_COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "IN": ("india", "bangalore", "bengaluru", "coimbatore", "hyderabad", "pune", "mumbai", "chennai", "gurgaon", "gurugram", "noida"),
    "MX": ("mexico", "mexico city", "ciudad de mexico", "guadalajara"),
    "CO": ("colombia", "bogota", "medellin"),
    "BR": ("brazil", "sao paulo", "rio de janeiro"),
    "AR": ("argentina", "buenos aires"),
    "CL": ("chile", "santiago"),
}


STATE_OR_PROVINCE_TO_COUNTRY = {
    **{code: "US" for code in (
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
        "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
        "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
        "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
        "WI", "WY", "DC", "PR",
    )},
    **{code: "CA" for code in ("AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT")},
}

GLOBAL_POSITIVE_KEYWORDS: dict[str, int] = {
    "visa sponsorship": 45,
    "visa sponsorship available": 55,
    "work visa sponsorship": 50,
    "work permit support": 45,
    "will sponsor": 50,
    "sponsorship available": 50,
    "relocation support": 25,
    "international candidates": 25,
    "immigration support": 35,
}

GLOBAL_NEGATIVE_KEYWORDS: dict[str, int] = {
    "no sponsorship": -70,
    "no visa sponsorship": -75,
    "cannot sponsor": -70,
    "unable to sponsor": -70,
    "will not sponsor": -70,
    "without sponsorship": -65,
    "citizens only": -55,
    "must have existing work authorization": -35,
    "must already have the right to work": -35,
}

ENGLISH_SIGNALS = (
    "english required", "fluent english", "english fluency", "english-speaking",
    "english speaking", "english is our working language", "international team",
    "global team", "business english",
)

ENGLISH_STOPWORDS = (
    " the ", " and ", " with ", " for ", " you ", " our ", " are ", " will ",
    " experience ", " responsibilities ", " requirements ", " qualifications ",
)


def normalize_country_code(value: str | None) -> str | None:
    text = (value or "").strip().upper()
    if not text:
        return None
    if text == "UK":
        return "GB"
    return text if text in TARGET_COUNTRIES else None


def _contains_alias(haystack: str, aliases: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(alias)}\b", haystack) for alias in aliases)


def resolve_country(text: str | None, *, default: str | None = None) -> str | None:
    haystack = f" {(text or '').lower()} "
    explicit = normalize_country_code((text or "").strip())
    if explicit:
        return explicit
    for code, aliases in NON_TARGET_COUNTRY_ALIASES.items():
        if _contains_alias(haystack, aliases):
            return code
    m_any_country = re.search(r"(?:,\s*|\s)([A-Z]{2})\b\s*$", (text or "").strip(), re.I)
    if m_any_country:
        suffix = m_any_country.group(1).upper()
        if suffix in TARGET_COUNTRIES:
            return suffix
        if suffix not in STATE_OR_PROVINCE_TO_COUNTRY:
            return suffix
    m = re.search(r"\b([A-Z]{2})\b\s*$", (text or "").strip())
    if m and m.group(1) in STATE_OR_PROVINCE_TO_COUNTRY:
        return STATE_OR_PROVINCE_TO_COUNTRY[m.group(1)]
    for code, aliases in COUNTRY_ALIASES.items():
        if _contains_alias(haystack, aliases):
            return code
    return normalize_country_code(default)


def in_target_country(location_text: str | None, *, default: str | None = None) -> tuple[bool, str | None]:
    country = resolve_country(location_text, default=default)
    if country:
        return country in TARGET_COUNTRIES, country
    # Remote/unspecified roles are allowed through; sponsor verification and JD
    # signals decide later. This avoids dropping public ATS roles whose location
    # is stored separately.
    lowered = (location_text or "").lower()
    if not lowered or any(token in lowered for token in ("remote", "anywhere", "global")):
        return True, None
    return False, None


def _keyword_score(text: str, keywords: dict[str, int]) -> tuple[int, list[str]]:
    score = 0
    hits: list[str] = []
    for keyword, points in keywords.items():
        if keyword in text:
            score += points
            hits.append(keyword)
    return score, hits


def _looks_english(text: str) -> bool:
    if not text:
        return False
    ascii_letters = sum(1 for char in text if ("a" <= char <= "z") or ("A" <= char <= "Z"))
    letters = sum(1 for char in text if char.isalpha())
    if letters and ascii_letters / letters < 0.82:
        return False
    lowered = f" {text.lower()} "
    return sum(1 for token in ENGLISH_STOPWORDS if token in lowered) >= 4


def classify_global_visa(
    *,
    title: str,
    company: str,
    description: str,
    location: str = "",
    country_code: str | None = None,
    sponsor_verified: bool = False,
    sponsor_source: str | None = None,
) -> dict:
    country = normalize_country_code(country_code) or resolve_country(location) or "US"
    rule = COUNTRY_RULES.get(country)
    text = f"{title or ''}\n{company or ''}\n{location or ''}\n{description or ''}".lower()
    score, keyword_hits = _keyword_score(text, GLOBAL_POSITIVE_KEYWORDS)
    negative_score, negative_hits = _keyword_score(text, GLOBAL_NEGATIVE_KEYWORDS)
    score += negative_score

    visa_programs: list[str] = []
    visa_program_names: list[str] = []
    if rule:
        for program in rule.programs:
            if any(keyword in text for keyword in program.keywords):
                visa_programs.append(program.code)
                visa_program_names.append(program.name)
                score += 35
                keyword_hits.append(program.name)

    if sponsor_verified:
        score += 35
        keyword_hits.append(f"sponsor verified: {sponsor_source or country}")
        if rule and not visa_programs and rule.programs:
            visa_programs.append(rule.programs[0].code)
            visa_program_names.append(rule.programs[0].name)

    english_native = bool(rule and rule.english_native)
    english_friendly = english_native or _looks_english(text) or any(signal in text for signal in ENGLISH_SIGNALS)
    if english_friendly:
        score += 10

    hard_block = bool(negative_hits and score < 35)
    if hard_block:
        visa_programs = []
        visa_program_names = []

    score = max(0, min(100, score))
    return {
        "country_code": country,
        "country_name": rule.name if rule else country,
        "visa_programs": list(dict.fromkeys(visa_programs)),
        "visa_program_names": list(dict.fromkeys(visa_program_names)),
        "sponsor_verified": bool(sponsor_verified and not hard_block),
        "sponsor_source": sponsor_source,
        "english_friendly": english_friendly,
        "keyword_hits": keyword_hits,
        "negative_hits": negative_hits,
        "score": score,
        "should_discard": hard_block,
        "confidence": "high" if sponsor_verified or len(keyword_hits) >= 3 else "medium" if keyword_hits else "low",
    }


def country_options() -> list[dict[str, str]]:
    return [
        {"code": code, "name": COUNTRY_RULES.get(code, CountryVisaRule(code, code, False, ())).name}
        for code in TARGET_COUNTRIES
    ]


def visa_program_options(country_code: str | None = None) -> list[dict[str, str]]:
    countries: Iterable[str] = [normalize_country_code(country_code)] if country_code else TARGET_COUNTRIES
    options: list[dict[str, str]] = []
    for code in countries:
        if not code or code not in COUNTRY_RULES:
            continue
        for program in COUNTRY_RULES[code].programs:
            options.append({"country_code": code, "code": program.code, "name": program.name})
    return options
