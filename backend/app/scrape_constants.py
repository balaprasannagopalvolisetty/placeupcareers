"""
Shared scraping defaults — pulled from the central job taxonomy so the
scraper, frontend filters, and category sidebar all stay in lock-step.

Add a new role to `app.job_taxonomy.CATEGORIES` and it automatically
becomes a scrape query and a UI filter chip.
"""
from app.job_taxonomy import all_search_terms

DEFAULT_SCRAPE_SEARCH_TERMS: tuple[str, ...] = tuple(all_search_terms())

# Sources that serve first-party employer data (direct ATS boards + curated
# company-career pipelines). Shared by the DB pool query (guaranteed pool
# representation) and the API feed ranking (first-party before aggregator).
FIRST_PARTY_ATS_SOURCES: frozenset[str] = frozenset({
    "greenhouse", "lever", "ashby", "smartrecruiters", "workday", "recruitee",
    "personio", "teamtailor", "jazzhr", "rippling", "bamboohr", "workable",
    "h1b_sponsor", "tier1_ats",
    "icims", "jobvite", "breezyhr", "oracle_recruiting", "paylocity", "ukg",
    "zoho_recruit", "adp", "dover", "gem", "successfactors", "pinpoint",
    "polymer", "phenom", "dayforce", "join", "hireology",
})
