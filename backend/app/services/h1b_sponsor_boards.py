"""
Curated mapping of major H1B sponsors → their public ATS career boards.

Each entry tells the orchestrator which ATS-specific scraper to call and
with what board token. This catalog focuses on companies that:
  - Filed 100+ H1B petitions in any year 2022–2026
  - Expose a publicly scrapable ATS endpoint (no auth required)

The catalog is intentionally hand-curated (not auto-discovered) so we get
high signal-to-noise. Add new entries as you find more boards.

Format (per entry):
    {
        "company": "Stripe",         # canonical display name
        "ats": "greenhouse",          # one of greenhouse|lever|ashby|smartrecruiters|workday|recruitee|personio|teamtailor|jazzhr|rippling|bamboohr
        "token": "stripe",            # ATS-specific board token (string, OR tuple for workday)
        "h1b_tier": "T1",             # T1 = top 100 sponsor, T2 = top 500, T3 = active sponsor
    }
"""

from __future__ import annotations

# H1B-active companies with publicly scrapable ATS boards.
# Curated from USCIS H-1B Hub leaderboards (FY2022-FY2024) and known career-page ATS providers.
H1B_SPONSOR_BOARDS: list[dict] = [
    # ─── Tier 1 — Big Tech / FAANG-adjacent (high H1B volume) ───
    {"company": "Stripe",            "ats": "greenhouse",      "token": "stripe",          "h1b_tier": "T1"},
    {"company": "Airbnb",            "ats": "greenhouse",      "token": "airbnb",          "h1b_tier": "T1"},
    {"company": "Coinbase",          "ats": "greenhouse",      "token": "coinbase",        "h1b_tier": "T1", "active": False},
    {"company": "Robinhood",         "ats": "greenhouse",      "token": "robinhood",       "h1b_tier": "T1"},
    {"company": "Pinterest",         "ats": "greenhouse",      "token": "pinterest",       "h1b_tier": "T1"},
    {"company": "Reddit",            "ats": "greenhouse",      "token": "reddit",          "h1b_tier": "T1"},
    {"company": "Lyft",              "ats": "greenhouse",      "token": "lyft",            "h1b_tier": "T1"},
    {"company": "DoorDash",          "ats": "greenhouse",      "token": "doordash",        "h1b_tier": "T1", "active": False},
    {"company": "Instacart",         "ats": "greenhouse",      "token": "instacart",       "h1b_tier": "T1"},
    {"company": "Cloudflare",        "ats": "greenhouse",      "token": "cloudflare",      "h1b_tier": "T1"},
    {"company": "Datadog",           "ats": "greenhouse",      "token": "datadog",         "h1b_tier": "T1"},
    {"company": "Snowflake",         "ats": "greenhouse",      "token": "snowflake",       "h1b_tier": "T1", "active": False},
    {"company": "MongoDB",           "ats": "greenhouse",      "token": "mongodbinc",      "h1b_tier": "T1", "active": False},
    {"company": "Confluent",         "ats": "greenhouse",      "token": "confluent",       "h1b_tier": "T1", "active": False},
    {"company": "HashiCorp",         "ats": "greenhouse",      "token": "hashicorp",       "h1b_tier": "T1", "active": False},
    {"company": "Twilio",            "ats": "smartrecruiters", "token": "Twilio",          "h1b_tier": "T1"},
    {"company": "Okta",              "ats": "greenhouse",      "token": "okta",            "h1b_tier": "T1"},
    {"company": "GitHub",            "ats": "greenhouse",      "token": "github",          "h1b_tier": "T1", "active": False},
    {"company": "GitLab",            "ats": "greenhouse",      "token": "gitlab",          "h1b_tier": "T1"},
    {"company": "Square (Block)",    "ats": "greenhouse",      "token": "square",          "h1b_tier": "T1", "active": False},
    {"company": "Affirm",            "ats": "greenhouse",      "token": "affirm",          "h1b_tier": "T1"},
    {"company": "Plaid",             "ats": "lever",           "token": "plaid",           "h1b_tier": "T1"},
    {"company": "Brex",              "ats": "greenhouse",      "token": "brex",            "h1b_tier": "T1"},
    {"company": "Roblox",            "ats": "greenhouse",      "token": "roblox",          "h1b_tier": "T1"},
    {"company": "Unity",             "ats": "greenhouse",      "token": "unity3d",         "h1b_tier": "T1"},
    {"company": "Figma",             "ats": "greenhouse",      "token": "figma",           "h1b_tier": "T1"},
    {"company": "Notion",            "ats": "greenhouse",      "token": "notion",          "h1b_tier": "T1", "active": False},
    {"company": "Asana",             "ats": "greenhouse",      "token": "asana",           "h1b_tier": "T1"},
    {"company": "Slack",             "ats": "greenhouse",      "token": "slack",           "h1b_tier": "T1", "active": False},
    {"company": "Atlassian",         "ats": "lever",           "token": "atlassian",       "h1b_tier": "T1"},
    {"company": "Zoom",              "ats": "greenhouse",      "token": "zoom",            "h1b_tier": "T1", "active": False},
    {"company": "Dropbox",           "ats": "greenhouse",      "token": "dropbox",         "h1b_tier": "T1"},
    {"company": "Box",               "ats": "greenhouse",      "token": "box",             "h1b_tier": "T1", "active": False},
    {"company": "Splunk",            "ats": "greenhouse",      "token": "splunkinc",       "h1b_tier": "T1", "active": False},
    {"company": "Palo Alto Networks","ats": "greenhouse",      "token": "paloaltonetworks","h1b_tier": "T1", "active": False},
    {"company": "Palantir",          "ats": "lever",           "token": "palantir",        "h1b_tier": "T1"},
    {"company": "Anthropic",         "ats": "greenhouse",      "token": "anthropic",       "h1b_tier": "T1"},
    {"company": "OpenAI",            "ats": "greenhouse",      "token": "openai",          "h1b_tier": "T1", "active": False},
    {"company": "Scale AI",          "ats": "ashby",           "token": "scaleai",         "h1b_tier": "T1", "active": False},
    {"company": "Databricks",        "ats": "greenhouse",      "token": "databricks",      "h1b_tier": "T1"},

    # ─── Workday (tenant, site) tuples ────────────────────────
    {"company": "NVIDIA",            "ats": "workday",         "token": ("nvidia", "External_Career_Site"),               "h1b_tier": "T1"},
    {"company": "Salesforce",        "ats": "workday",         "token": ("salesforce", "External_Career_Site"),           "h1b_tier": "T1"},
    {"company": "Adobe",             "ats": "workday",         "token": ("adobe", "external_experienced"),                "h1b_tier": "T1"},
    {"company": "Cisco",             "ats": "workday",         "token": ("cisco", "External"),                            "h1b_tier": "T1"},
    {"company": "Intel",             "ats": "workday",         "token": ("intel", "External"),                            "h1b_tier": "T1"},
    {"company": "AMD",               "ats": "workday",         "token": ("amd", "External"),                              "h1b_tier": "T1"},
    {"company": "Qualcomm",          "ats": "workday",         "token": ("qualcomm", "External"),                         "h1b_tier": "T1"},
    {"company": "Apple",             "ats": "workday",         "token": ("apple", "External"),                            "h1b_tier": "T1"},
    {"company": "Workday",           "ats": "workday",         "token": ("workday", "Workday"),                           "h1b_tier": "T1"},
    {"company": "ServiceNow",        "ats": "workday",         "token": ("servicenow", "ServiceNowExternal"),             "h1b_tier": "T1"},
    {"company": "VMware",            "ats": "workday",         "token": ("vmware", "VMware"),                             "h1b_tier": "T1"},
    {"company": "Oracle",            "ats": "workday",         "token": ("oracle", "Oracle"),                             "h1b_tier": "T1"},

    # ─── Lever ────────────────────────────────────────────────
    {"company": "Netflix",           "ats": "lever",           "token": "netflix",         "h1b_tier": "T1"},
    {"company": "Spotify",           "ats": "lever",           "token": "spotify",         "h1b_tier": "T1"},
    {"company": "Shopify",           "ats": "lever",           "token": "shopify",         "h1b_tier": "T1", "active": False},
    {"company": "Twitch",            "ats": "lever",           "token": "twitch",          "h1b_tier": "T1", "active": False},
    {"company": "KKR",               "ats": "lever",           "token": "kkr",             "h1b_tier": "T2", "active": False},

    # ─── Ashby ────────────────────────────────────────────────
    {"company": "Ramp",              "ats": "ashby",           "token": "Ramp",            "h1b_tier": "T1"},
    {"company": "Linear",            "ats": "ashby",           "token": "Linear",          "h1b_tier": "T2"},
    {"company": "Mercury",           "ats": "ashby",           "token": "MercuryTechnologies", "h1b_tier": "T1", "active": False},
    {"company": "Vercel",            "ats": "greenhouse",      "token": "vercel",          "h1b_tier": "T1"},
    {"company": "Anysphere (Cursor)","ats": "ashby",           "token": "Anysphere",       "h1b_tier": "T2", "active": False},
    {"company": "Perplexity",        "ats": "ashby",           "token": "Perplexity",      "h1b_tier": "T1"},

    # ─── SmartRecruiters ──────────────────────────────────────
    {"company": "Visa Inc.",         "ats": "smartrecruiters", "token": "Visa",            "h1b_tier": "T1"},
    {"company": "McDonald's",        "ats": "smartrecruiters", "token": "McDonalds",       "h1b_tier": "T2"},
    {"company": "LVMH",              "ats": "smartrecruiters", "token": "LVMH",            "h1b_tier": "T2"},
    {"company": "Bosch",             "ats": "smartrecruiters", "token": "BoschGroup",      "h1b_tier": "T2"},

    # ─── Recruitee ────────────────────────────────────────────
    {"company": "HelloFresh",        "ats": "recruitee",       "token": "hellofresh",      "h1b_tier": "T2", "active": False},

    # ─── Teamtailor ───────────────────────────────────────────
    {"company": "Klarna",            "ats": "teamtailor",      "token": "klarna",          "h1b_tier": "T1", "active": False},

    # ─── Greenhouse (more H1B-active) ─────────────────────────
    {"company": "Asana",             "ats": "greenhouse",      "token": "asana",           "h1b_tier": "T1"},
    {"company": "Discord",           "ats": "greenhouse",      "token": "discord",         "h1b_tier": "T1"},
    {"company": "Duolingo",          "ats": "greenhouse",      "token": "duolingo",        "h1b_tier": "T1"},
    {"company": "Twilio",            "ats": "greenhouse",      "token": "twilio",          "h1b_tier": "T1"},
    {"company": "Yelp",              "ats": "greenhouse",      "token": "yelp",            "h1b_tier": "T2", "active": False},
    {"company": "Wayfair",           "ats": "greenhouse",      "token": "wayfair",         "h1b_tier": "T1", "active": False},
    {"company": "Etsy",              "ats": "greenhouse",      "token": "etsy",            "h1b_tier": "T1", "active": False},
    {"company": "Compass",           "ats": "greenhouse",      "token": "urbancompass",    "h1b_tier": "T2"},
    {"company": "Peloton",           "ats": "greenhouse",      "token": "peloton",         "h1b_tier": "T1"},
    {"company": "Carvana",           "ats": "greenhouse",      "token": "carvana",         "h1b_tier": "T2"},
    {"company": "Toast",             "ats": "greenhouse",      "token": "toast",           "h1b_tier": "T1"},
    {"company": "Block (Cash App)",  "ats": "greenhouse",      "token": "cashapp",         "h1b_tier": "T1", "active": False},
    {"company": "BetterUp",          "ats": "greenhouse",      "token": "betterup",        "h1b_tier": "T2", "active": False},
    {"company": "Discord",           "ats": "greenhouse",      "token": "discord",         "h1b_tier": "T1"},
    {"company": "Roku",              "ats": "greenhouse",      "token": "roku",            "h1b_tier": "T1"},
    {"company": "Pure Storage",      "ats": "greenhouse",      "token": "purestorage",     "h1b_tier": "T1"},
    {"company": "Elastic",           "ats": "greenhouse",      "token": "elastic",         "h1b_tier": "T1"},
    {"company": "Sumo Logic",        "ats": "greenhouse",      "token": "sumologic",       "h1b_tier": "T2"},
    {"company": "New Relic",         "ats": "greenhouse",      "token": "newrelic",        "h1b_tier": "T1"},
    {"company": "PagerDuty",         "ats": "greenhouse",      "token": "pagerduty",       "h1b_tier": "T1"},
    {"company": "Auth0",             "ats": "greenhouse",      "token": "auth0",           "h1b_tier": "T1", "active": False},
    {"company": "Twitter (X)",       "ats": "greenhouse",      "token": "x",               "h1b_tier": "T1", "active": False},
    {"company": "Anduril",           "ats": "greenhouse",      "token": "anduril",         "h1b_tier": "T1", "active": False},
    {"company": "Rivian",            "ats": "greenhouse",      "token": "rivian",          "h1b_tier": "T1", "active": False},
    {"company": "Lucid Motors",      "ats": "greenhouse",      "token": "lucidmotors",     "h1b_tier": "T1"},
    {"company": "Tesla",             "ats": "greenhouse",      "token": "tesla",           "h1b_tier": "T1", "active": False},
    {"company": "Wish",              "ats": "greenhouse",      "token": "wish",            "h1b_tier": "T2", "active": False},
    {"company": "Rappi",             "ats": "greenhouse",      "token": "rappi",           "h1b_tier": "T2", "active": False},
    {"company": "Grab",              "ats": "greenhouse",      "token": "grab",            "h1b_tier": "T2", "active": False},
    {"company": "Squarespace",       "ats": "greenhouse",      "token": "squarespace",     "h1b_tier": "T1"},
    {"company": "Warby Parker",      "ats": "greenhouse",      "token": "warbyparker",     "h1b_tier": "T2", "active": False},
    {"company": "ZipRecruiter",      "ats": "greenhouse",      "token": "ziprecruiter",    "h1b_tier": "T2"},
    {"company": "Glassdoor",         "ats": "greenhouse",      "token": "glassdoor",       "h1b_tier": "T2"},
    {"company": "Indeed",            "ats": "smartrecruiters", "token": "Indeed",          "h1b_tier": "T1"},
    {"company": "Bumble",            "ats": "greenhouse",      "token": "bumble",          "h1b_tier": "T2", "active": False},
    {"company": "Hinge",             "ats": "greenhouse",      "token": "matchgroup",      "h1b_tier": "T2", "active": False},
    {"company": "Roblox Corporation","ats": "greenhouse",      "token": "roblox",          "h1b_tier": "T1"},
    {"company": "Coursera",          "ats": "greenhouse",      "token": "coursera",        "h1b_tier": "T1"},
    {"company": "Udemy",             "ats": "greenhouse",      "token": "udemy",           "h1b_tier": "T2"},
    {"company": "Khan Academy",      "ats": "greenhouse",      "token": "khanacademy",     "h1b_tier": "T2"},
    {"company": "Discord",           "ats": "greenhouse",      "token": "discord",         "h1b_tier": "T1"},

    # ─── Indian-IT services giants (top H1B sponsors by volume) ─
    # These typically use Workday or custom careers; we list known board tokens where available.
    {"company": "Infosys",           "ats": "workday",         "token": ("infosys", "career"),                            "h1b_tier": "T1"},
    {"company": "Tata Consultancy Services", "ats": "workday", "token": ("tcs", "TCS_External"),                          "h1b_tier": "T1"},
    {"company": "Wipro",             "ats": "workday",         "token": ("wipro", "wipro_careers"),                       "h1b_tier": "T1"},
    {"company": "HCL Technologies",  "ats": "workday",         "token": ("hcl", "HCL_External"),                          "h1b_tier": "T1"},
    {"company": "Cognizant",         "ats": "workday",         "token": ("cognizant", "external_career_site"),            "h1b_tier": "T1"},
    {"company": "Capgemini",         "ats": "smartrecruiters", "token": "Capgemini",       "h1b_tier": "T1"},
    {"company": "Accenture",         "ats": "workday",         "token": ("accenture", "AccentureCareers"),                "h1b_tier": "T1"},
    {"company": "IBM",               "ats": "workday",         "token": ("ibm", "IBMCareers"),                            "h1b_tier": "T1"},
    {"company": "Deloitte",          "ats": "workday",         "token": ("deloitte", "External"),                         "h1b_tier": "T1"},

    # ─── Finance / Banking ─────────────────────────────────────
    {"company": "JPMorgan Chase",    "ats": "workday",         "token": ("jpmc", "external_experienced"),                 "h1b_tier": "T1"},
    {"company": "Goldman Sachs",     "ats": "workday",         "token": ("goldmansachs", "GS_External"),                  "h1b_tier": "T1"},
    {"company": "Morgan Stanley",    "ats": "workday",         "token": ("ms", "External"),                               "h1b_tier": "T1"},
    {"company": "Citi",              "ats": "workday",         "token": ("citi", "Citi"),                                 "h1b_tier": "T1"},
    {"company": "Bank of America",   "ats": "workday",         "token": ("bankofamerica", "BACAREERS"),                   "h1b_tier": "T1"},
    {"company": "Wells Fargo",       "ats": "workday",         "token": ("wellsfargo", "WellsFargo_External"),            "h1b_tier": "T1"},

    # ─── Healthcare / Pharma ───────────────────────────────────
    {"company": "Pfizer",            "ats": "workday",         "token": ("pfizer", "PfizerCareers"),                      "h1b_tier": "T1"},
    {"company": "Moderna",           "ats": "greenhouse",      "token": "moderna",         "h1b_tier": "T1", "active": False},
    {"company": "Genentech",         "ats": "workday",         "token": ("roche", "roche-ext"),                           "h1b_tier": "T1"},
    {"company": "Johnson & Johnson", "ats": "workday",         "token": ("jnj", "jnj"),                                   "h1b_tier": "T1"},
]


def filter_by_tier(tiers: tuple[str, ...] = ("T1", "T2")) -> list[dict]:
    """Return only entries matching the given H1B tier(s)."""
    return [s for s in H1B_SPONSOR_BOARDS if s.get("h1b_tier") in tiers and s.get("active", True)]


def by_ats(ats_name: str) -> list[dict]:
    """Return only entries for a single ATS provider."""
    return [s for s in H1B_SPONSOR_BOARDS if s.get("ats") == ats_name.lower() and s.get("active", True)]
