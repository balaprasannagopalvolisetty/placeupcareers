"""
Curated targets for the ScrapeGraphAI discovery source.

Why a curated list (not "scrape everything"):
  - Each SmartScraperGraph call costs ~$0.001-0.005 in LLM tokens. Running
    against 10K random career pages each scrape would be ~$50/run, ~$1500/mo.
  - Hand-picked targets concentrate spend on pages that (a) actually have
    visa-friendly roles, and (b) cannot be reached via the free Tier-1 ATS
    APIs (Greenhouse/Lever/etc) we already scrape directly.
  - Operations can extend this list via the SCRAPEGRAPH_CAREER_PAGES env
    var (comma-separated URLs) without touching code.

Three target buckets are exposed:

  1. CAREER_PAGES    — direct company careers pages on Workday, iCIMS,
                       Taleo, SuccessFactors, or custom CMSs. These do NOT
                       have a public JSON ATS API.
  2. GOOGLE_JOBS_URLS — Google's job-search widget URL, one per top taxonomy
                        role × top metro. Indexes Indeed/LinkedIn/Glassdoor
                        for us in a single page that SmartScraperGraph can
                        read.
  3. LINKEDIN_URLS    — LinkedIn public guest job-search URLs (no login
                        required). Title + location parameters.
"""

from __future__ import annotations

from typing import Iterable
from urllib.parse import quote_plus

from app.job_taxonomy import all_role_names


# ─── 1. Direct career pages (companies with no public ATS API) ───────
# Focus: large H-1B sponsors on Workday/iCIMS/Taleo/SuccessFactors where
# the JSON API requires auth, OR custom-built career sites. Greenhouse/
# Lever/Ashby/Workable/SmartRecruiters/Recruitee are NOT here — they're
# already handled by tier1_ats.
CAREER_PAGES: tuple[dict, ...] = (
    # Big tech (Workday tenants — scrape the HTML, the JSON needs auth)
    {"company": "Amazon",         "url": "https://www.amazon.jobs/en/search?base_query=engineer&loc_query=United+States"},
    {"company": "Microsoft",      "url": "https://jobs.careers.microsoft.com/global/en/search?lc=United%20States"},
    {"company": "Google",         "url": "https://www.google.com/about/careers/applications/jobs/results?location=United%20States"},
    {"company": "Meta",           "url": "https://www.metacareers.com/jobs?offices[0]=United%20States"},
    {"company": "Tesla",          "url": "https://www.tesla.com/careers/search/?country=US"},
    {"company": "SpaceX",         "url": "https://www.spacex.com/careers/jobs/"},
    {"company": "TikTok",         "url": "https://careers.tiktok.com/position?keywords=&category=&location=CT_117&start=0&limit=20"},
    {"company": "ByteDance",      "url": "https://jobs.bytedance.com/en/position?keywords=&category=&location=CT_117"},
    {"company": "Capital One",    "url": "https://www.capitalonecareers.com/search-jobs/United%20States/1732/4/6252001"},
    {"company": "JPMorgan Chase", "url": "https://careers.jpmorgan.com/us/en/students/programs"},
    {"company": "Goldman Sachs",  "url": "https://www.goldmansachs.com/careers/students/programs/"},
    {"company": "Morgan Stanley", "url": "https://www.morganstanley.com/people-opportunities/students-graduates"},
    {"company": "Deloitte",       "url": "https://www2.deloitte.com/us/en/careers/careers.html"},
    {"company": "Accenture",      "url": "https://www.accenture.com/us-en/careers/jobsearch"},
    {"company": "EY",             "url": "https://www.ey.com/en_us/careers"},
    {"company": "PwC",            "url": "https://jobs.us.pwc.com/"},
    {"company": "KPMG",           "url": "https://www.kpmguscareers.com/job-search/"},
    {"company": "McKinsey",       "url": "https://www.mckinsey.com/careers/search-jobs"},
    {"company": "BCG",            "url": "https://careers.bcg.com/global"},
    {"company": "Bain",           "url": "https://www.bain.com/careers/find-a-role/"},
    {"company": "IBM",            "url": "https://www.ibm.com/careers/search"},
    # Top H-1B filers that don't fit ATS conventions
    {"company": "Infosys",        "url": "https://www.infosys.com/careers/apply.html"},
    {"company": "TCS",            "url": "https://www.tcs.com/careers"},
    {"company": "Wipro",          "url": "https://careers.wipro.com/careers-home/jobs?country=United%20States"},
    {"company": "HCL",            "url": "https://www.hcltech.com/careers"},
    {"company": "Cognizant",      "url": "https://careers.cognizant.com/us/en/search-results?keywords=&location=United%20States"},
)


# ─── 2. Google Jobs (Google's universal job search widget) ───────────
# The `ibp=htl;jobs` parameter forces Google to render the structured
# Jobs panel — every result there comes with company, title, location,
# and a direct apply link. One URL = one Google "Jobs" search result page.
def google_jobs_queries() -> list[str]:
    """One Google Jobs query for every Jobs-page role."""
    return [f"{role} OPT H-1B visa sponsor" for role in all_role_names()]


def google_jobs_url(query: str) -> str:
    """Render a Google Jobs widget URL for the given search query.

    Returns a URL pointing at the rendered Jobs panel, not generic search
    results — so the extractor sees a clean list of postings.
    """
    return f"https://www.google.com/search?q={quote_plus(query)}&ibp=htl;jobs"


# ─── 3. LinkedIn public job search (guest mode, no login needed) ─────
# LinkedIn's `jobs/search` URL with `f_AL=true` filters to easy-apply,
# which loads cleanly without a logged-in session. We keep the count
# low because LinkedIn rate-limits aggressively.
LINKEDIN_GEO_IDS: dict[str, str] = {
    # geoId values from LinkedIn's location autocomplete API. These rarely
    # change; mapped here so we don't have to scrape them on the fly.
    "United States": "103644278",
    "San Francisco Bay Area": "90000084",
    "New York City Metropolitan Area": "90000070",
    "Seattle, Washington Metropolitan Area": "90000099",
    "Greater Boston": "90000007",
    "Greater Chicago Area": "90000049",
    "Austin, Texas Metropolitan Area": "90000060",
    "Dallas-Fort Worth Metroplex": "90000022",
}

def linkedin_keywords() -> list[str]:
    """One LinkedIn keyword for every Jobs-page role."""
    return all_role_names()


def linkedin_search_url(keyword: str, location_name: str = "United States") -> str:
    """Build a LinkedIn guest-mode job search URL.

    f_TPR=r604800 = posted in the last week (keeps each scrape fresh).
    f_E=2,3       = entry- and associate-level (matches our 0-10yr filter).
    """
    geo_id = LINKEDIN_GEO_IDS.get(location_name, LINKEDIN_GEO_IDS["United States"])
    params = {
        "keywords": quote_plus(keyword),
        "geoId": geo_id,
        "f_TPR": "r604800",
        "f_E": "2,3",
        "sortBy": "DD",  # date descending
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://www.linkedin.com/jobs/search/?{qs}"


# ─── Targets enumerator ──────────────────────────────────────────────

def iter_targets(
    *,
    extra_career_urls: Iterable[str] = (),
    max_career: int = 30,
    max_google: int | None = None,
    max_linkedin: int | None = None,
) -> list[dict]:
    """Yield up to N targets per bucket — caller decides the global cap.

    Each dict has shape: {kind, url, company?, query?, location?}.
    """
    out: list[dict] = []

    for entry in CAREER_PAGES[:max_career]:
        out.append({"kind": "career_page", "url": entry["url"], "company": entry["company"]})
    for raw_url in extra_career_urls:
        clean = raw_url.strip()
        if clean:
            out.append({"kind": "career_page", "url": clean, "company": None})

    google_queries = google_jobs_queries()
    if max_google is not None:
        google_queries = google_queries[:max_google]
    for query in google_queries:
        out.append({"kind": "google_jobs", "url": google_jobs_url(query), "query": query})

    seen_linkedin: set[str] = set()
    linkedin_target_count = 0
    for kw in linkedin_keywords():
        for loc in ("United States",):
            if max_linkedin is not None and linkedin_target_count >= max_linkedin:
                break
            url = linkedin_search_url(kw, loc)
            if url in seen_linkedin:
                continue
            seen_linkedin.add(url)
            linkedin_target_count += 1
            out.append({"kind": "linkedin", "url": url, "query": kw, "location": loc})
    return out
