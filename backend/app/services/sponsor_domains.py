"""
Curated H1B sponsor name → real corporate domain mapping.

Maps the legal employer names from USCIS/h1bdata leaderboards to the actual
domain that Hunter / company-page crawlers should use. Without this, the
domain guesser produces garbage like "inbase.com" (for COINBASE INC) or
"university.com" (for any university).

Lookups are case-insensitive and use longest-prefix substring matching,
so "AMAZONCOM SERVICES LLC" and "AMAZON WEB SERVICES INC" both map to
amazon.com.

Add new entries to this dict as you find them. Built from the top ~200
sponsors in data/h1b/sponsors_2024_2025_2026.csv.
"""

from __future__ import annotations
import re

# Hand-curated mapping. Key = lowercase substring of employer name.
# First match wins (so put more-specific entries first if needed).
SPONSOR_DOMAIN_MAP: dict[str, str] = {
    # ─── IT services giants ─────────────────────────────────────
    "cognizant": "cognizant.com",
    "tata consultancy": "tcs.com",
    "ernst and young u s llp": "ey.com",
    "fidelity technology group": "fidelity.com",
    "tata consultancy services limited": "tcs.com",
    "infosys": "infosys.com",
    "wipro": "wipro.com",
    "hcl america": "hcltech.com",
    "hcl tech": "hcltech.com",
    "tech mahindra": "techmahindra.com",
    "capgemini": "capgemini.com",
    "accenture": "accenture.com",
    "deloitte": "deloitte.com",
    "ernst & young": "ey.com",
    "ey": "ey.com",
    "kpmg": "kpmg.com",
    "pwc": "pwc.com",
    "pricewaterhousecoopers": "pwc.com",
    "ibm": "ibm.com",
    "ntt data": "nttdata.com",
    "mphasis": "mphasis.com",
    "ltimindtree": "ltimindtree.com",
    "l&t": "lntinfotech.com",
    "larsen & toubro": "lntinfotech.com",
    "yash": "yash.com",
    "syntel": "atos.net",
    "atos": "atos.net",
    "happiest minds": "happiestminds.com",
    "kpit": "kpit.com",
    "persistent": "persistent.com",
    "tigeranalytics": "tigeranalytics.com",
    "tiger analytics": "tigeranalytics.com",
    "fractal": "fractal.ai",
    "iris software": "irissoftware.com",
    "intraedge": "intraedge.com",
    "yash technologies": "yash.com",
    "people tech": "peopletech.com",
    "perficient": "perficient.com",
    "slk america": "slksoftware.com",
    "kastech": "kastechsolutions.com",
    "eficens": "eficens.com",
    "satin": "satinsolutions.com",
    "astir": "astirit.com",
    "photon": "photon.com",
    "headstrong": "headstrong.com",
    "technosoft": "technosoftcorp.com",
    "technumen": "technumen.com",
    "e-giants": "egiantstechnologies.com",
    "federal soft": "federalsoftsystems.com",
    "sapphire software": "sapphiresoftwaresolutions.com",
    "quest global": "questglobal.com",
    "mpg": "mpgoperations.com",
    "slalom": "slalom.com",
    "headstrong services": "headstrong.com",

    # ─── Big Tech / FAANG ───────────────────────────────────────
    "google": "google.com",
    "alphabet": "google.com",
    "amazon": "amazon.com",
    "amazon web services": "amazon.com",
    "amazoncom": "amazon.com",
    "microsoft": "microsoft.com",
    "meta platforms": "meta.com",
    "meta ": "meta.com",
    "facebook": "meta.com",
    "apple": "apple.com",
    "netflix": "netflix.com",
    "tesla": "tesla.com",

    # ─── Other tech ─────────────────────────────────────────────
    "intel": "intel.com",
    "nvidia": "nvidia.com",
    "amd ": "amd.com",
    "advanced micro devices": "amd.com",
    "qualcomm": "qualcomm.com",
    "salesforce": "salesforce.com",
    "oracle": "oracle.com",
    "cisco": "cisco.com",
    "vmware": "vmware.com",
    "servicenow": "servicenow.com",
    "adobe": "adobe.com",
    "workday": "workday.com",
    "snowflake": "snowflake.com",
    "databricks": "databricks.com",
    "mongodb": "mongodb.com",
    "splunk": "splunk.com",
    "datadog": "datadoghq.com",
    "cloudflare": "cloudflare.com",
    "stripe": "stripe.com",
    "square": "block.xyz",
    "paypal": "paypal.com",
    "ebay": "ebay.com",
    "reddit": "reddit.com",
    "pinterest": "pinterest.com",
    "linkedin": "linkedin.com",
    "twitter": "x.com",
    "x corp": "x.com",
    "x.ai": "x.ai",
    "tiktok": "tiktok.com",
    "bytedance": "bytedance.com",
    "uber": "uber.com",
    "lyft": "lyft.com",
    "airbnb": "airbnb.com",
    "doordash": "doordash.com",
    "instacart": "instacart.com",
    "maplebear": "instacart.com",
    "zillow": "zillow.com",
    "wayfair": "wayfair.com",
    "etsy": "etsy.com",
    "shopify": "shopify.com",
    "spotify": "spotify.com",
    "zoom": "zoom.us",
    "slack": "slack.com",
    "atlassian": "atlassian.com",
    "github": "github.com",
    "gitlab": "gitlab.com",
    "okta": "okta.com",
    "twilio": "twilio.com",
    "confluent": "confluent.io",
    "hashicorp": "hashicorp.com",
    "fastly": "fastly.com",
    "elastic": "elastic.co",
    "splunkinc": "splunk.com",
    "palantir": "palantir.com",
    "anduril": "anduril.com",
    "scale ai": "scale.com",
    "openai": "openai.com",
    "anthropic": "anthropic.com",
    "perplexity": "perplexity.ai",
    "chewy": "chewy.com",
    "cruise": "getcruise.com",
    "carnegie mellon": "cmu.edu",
    "cigna": "cigna.com",
    "evernorth": "evernorth.com",
    "abbvie": "abbvie.com",
    "bristol-myers": "bms.com",
    "bristol myers": "bms.com",
    "zscaler": "zscaler.com",
    "deutsche bank securities": "db.com",
    "deutsche bank": "db.com",
    "db usa": "db.com",
    "db global": "db.com",
    "atlassian us": "atlassian.com",
    "kla": "kla.com",
    "mckesson": "mckesson.com",
    "qualcomm atheros": "qualcomm.com",
    "health care service corporation": "hcsc.com",
    "intercontinental exchange": "ice.com",
    "regeneron": "regeneron.com",
    "capital one": "capitalone.com",
    "starbucks": "starbucks.com",
    "geico": "geico.com",
    "samsung semiconductor": "samsung.com",
    "robinhood": "robinhood.com",
    "ericsson": "ericsson.com",
    "lam research": "lamresearch.com",
    "fortinet": "fortinet.com",
    "cardinal health": "cardinalhealth.com",
    "dell": "dell.com",
    "sony interactive": "playstation.com",
    "rockwell collins": "collinsaerospace.com",
    "aecom": "aecom.com",
    "centene": "centene.com",
    "best buy": "bestbuy.com",
    "uchicago argonne": "anl.gov",
    "duke university": "duke.edu",
    "twitter inc": "x.com",
    "zimmer": "zimmerbiomet.com",
    "california institute of technology": "caltech.edu",
    "indiana university": "iu.edu",
    "eli lilly": "lilly.com",
    "lilly": "lilly.com",
    "hcl america solutions": "hcltech.com",
    "black & veatch": "bv.com",
    "citigroup global markets": "citi.com",
    "citigroup": "citi.com",
    "citi": "citi.com",
    "jpmorgan chase": "jpmchase.com",
    "jpmorgan": "jpmchase.com",
    "morgan stanley": "morganstanley.com",
    "wells fargo": "wellsfargo.com",
    "bank of america": "bankofamerica.com",
    "the northern trust": "ntrs.com",
    "northern trust": "ntrs.com",
    "northwestern mutual": "northwesternmutual.com",
    "schlumberger": "slb.com",
    "splunk inc": "splunk.com",
    "texas instruments": "ti.com",
    "teladoc": "teladochealth.com",
    "amgen": "amgen.com",
    "synopsys": "synopsys.com",
    "cox automotive": "coxautoinc.com",
    "the bank of new york mellon": "bnymellon.com",
    "bnymellon": "bnymellon.com",
    "bny mellon": "bnymellon.com",
    "home depot": "homedepot.com",
    "zoom video": "zoom.us",
    "nyu grossman": "nyulangone.org",
    "cornell university": "cornell.edu",
    "netapp": "netapp.com",
    "tiktok us": "tiktok.com",
    "jacobs engineering": "jacobs.com",
    "brigham and women": "brighamandwomens.org",
    "splunk inc": "splunk.com",
    "becton dickinson": "bd.com",
    "takeda": "takeda.com",
    "battelle": "battelle.org",
    "dish network": "dish.com",
    "dish wireless": "dish.com",
    "the university of southern california": "usc.edu",
    "ev ernorth": "evernorth.com",
    "evernorth": "evernorth.com",
    "ge ico": "geico.com",

    # ─── Universities (.edu) ────────────────────────────────────
    "carnegie mellon university": "cmu.edu",
    "the pennsylvania state university": "psu.edu",
    "pennsylvania state": "psu.edu",
    "penn state": "psu.edu",
    "university of kentucky": "uky.edu",
    "university of colorado denver": "ucdenver.edu",
    "arizona state university": "asu.edu",
    "university of washington": "uw.edu",
    "the university of southern california": "usc.edu",
    "university of southern california": "usc.edu",
    "university of california berkeley": "berkeley.edu",
    "university of california davis": "ucdavis.edu",
    "university of california los angeles": "ucla.edu",
    "university of california san diego": "ucsd.edu",
    "university of california san francisco": "ucsf.edu",
    "university of california irvine": "uci.edu",
    "university of california santa barbara": "ucsb.edu",
    "university of california": "universityofcalifornia.edu",
    "university of utah": "utah.edu",
    "new york university": "nyu.edu",
    "stanford university": "stanford.edu",
    "harvard university": "harvard.edu",
    "massachusetts institute of technology": "mit.edu",
    "princeton university": "princeton.edu",
    "yale university": "yale.edu",
    "columbia university": "columbia.edu",
    "duke university": "duke.edu",
    "indiana university": "iu.edu",
    "cornell university": "cornell.edu",
    "temple university": "temple.edu",
    "university of arkansas for medical sciences": "uams.edu",
    "university of texas": "utexas.edu",
    "university of michigan": "umich.edu",
    "university of illinois": "illinois.edu",
    "university of pennsylvania": "upenn.edu",
    "university of chicago": "uchicago.edu",
    "university of wisconsin": "wisc.edu",
    "university of minnesota": "umn.edu",
    "university of maryland": "umd.edu",
    "university of pittsburgh": "pitt.edu",
    "university of virginia": "virginia.edu",
    "university of north carolina": "unc.edu",
    "university of florida": "ufl.edu",
    "university of arizona": "arizona.edu",
    "university of iowa": "uiowa.edu",
    "university of oregon": "uoregon.edu",
    "university of nebraska": "unl.edu",
    "georgia institute of technology": "gatech.edu",
    "georgia tech": "gatech.edu",
    "ohio state university": "osu.edu",
    "michigan state university": "msu.edu",
    "florida state university": "fsu.edu",
    "louisiana state university": "lsu.edu",
    "louisiana state": "lsu.edu",

    # ─── Hospitals / Medical ────────────────────────────────────
    "mayo clinic": "mayoclinic.org",
    "cleveland clinic": "clevelandclinic.org",
    "kaiser permanente": "kp.org",
    "johns hopkins": "jhu.edu",
    "memorial sloan kettering": "mskcc.org",
    "dana-farber": "dana-farber.org",
    "brigham and womens hospital": "brighamandwomens.org",
    "massachusetts general hospital": "massgeneral.org",
    "mass general brigham": "massgeneralbrigham.org",
    "icahn school of medicine": "mountsinai.org",
    "mount sinai": "mountsinai.org",
    "uhealth": "umiamihealth.org",
    "ucsf medical": "ucsf.edu",

    # ─── Pharma / Biotech ───────────────────────────────────────
    "moderna": "modernatx.com",
    "pfizer": "pfizer.com",
    "merck": "merck.com",
    "novartis": "novartis.com",
    "roche": "roche.com",
    "genentech": "gene.com",
    "bayer": "bayer.com",
    "sanofi": "sanofi.com",
    "gilead": "gilead.com",
    "astrazeneca": "astrazeneca.com",
    "abbvie": "abbvie.com",
    "bristol-myers squibb": "bms.com",
    "regeneron": "regeneron.com",
    "amgen": "amgen.com",
    "vertex pharmaceuticals": "vrtx.com",
    "biogen": "biogen.com",

    # ─── Retail / Consumer ──────────────────────────────────────
    "wal-mart": "walmart.com",
    "walmart": "walmart.com",
    "target": "target.com",
    "costco": "costco.com",
    "kroger": "kroger.com",
    "lowe's": "lowes.com",
    "lowes": "lowes.com",
    "home depot": "homedepot.com",
    "cvs": "cvshealth.com",
    "walgreens": "walgreens.com",
    "cvs pharmacy": "cvshealth.com",
}


_SPECIAL_TLDS = {".edu", ".gov", ".org", ".io", ".ai", ".co"}


def lookup_domain(employer_name: str) -> str | None:
    """Look up real corporate domain for an employer name.

    Tries exact lowercase match first, then substring containment.
    Returns None if no curated entry matches.
    """
    if not employer_name:
        return None
    n = employer_name.lower().strip()
    # Exact match
    if n in SPONSOR_DOMAIN_MAP:
        return SPONSOR_DOMAIN_MAP[n]
    # Substring containment — longer key wins
    matches = [(k, v) for k, v in SPONSOR_DOMAIN_MAP.items() if k in n]
    if not matches:
        return None
    matches.sort(key=lambda kv: -len(kv[0]))
    return matches[0][1]


# Words that are too generic to ever be a valid domain by themselves
GENERIC_DOMAIN_BLACKLIST = {
    "university", "college", "institute", "bank", "corp", "corporation",
    "company", "co", "inc", "llc", "ltd", "limited", "global", "americas",
    "north", "south", "east", "west", "us", "usa", "national", "federal",
    "state", "city", "general", "international", "group", "holdings",
    "services", "solutions", "technology", "technologies", "consulting",
    "the", "and", "or", "of", "for", "to",
    "best", "first", "new", "great", "big", "small",
    "lam", "db", "x", "ja", "ae", "ern", "rnell",  # observed garbage from broken heuristic
}


def is_safe_domain(domain: str) -> bool:
    """Reject domains that look like garbage (single generic word .com)."""
    if not domain or "." not in domain:
        return False
    # Allow special TLDs (.edu, .gov, .ai, etc.) without further checks
    for tld in _SPECIAL_TLDS:
        if domain.endswith(tld):
            return True
    # For .com, the local part must be >3 chars and not in blacklist
    local = domain.rsplit(".", 1)[0].lower()
    if len(local) < 2:
        return False
    if local in GENERIC_DOMAIN_BLACKLIST:
        return False
    return True


_SUFFIX_STRIP_RE = re.compile(
    r"\b(inc|llc|ltd|limited|llp|lp|corporation|corp|co|company|"
    r"the|us|usa|america|americas|global|services|solutions|"
    r"technology|technologies|consulting|holdings|enterprises|group|"
    r"north america|of america)\b\.?",
    re.IGNORECASE,
)


def fallback_guess_domain(employer_name: str) -> str | None:
    """Last-resort heuristic: take the first significant token of the name.

    Returns None if the result would be a generic/blacklisted word.
    """
    if not employer_name:
        return None
    n = _SUFFIX_STRIP_RE.sub(" ", employer_name.lower())
    n = re.sub(r"[^a-z0-9 ]", " ", n).strip()
    tokens = [t for t in n.split() if t and t not in {"and", "of", "the", "a", "&"}]
    if not tokens:
        return None
    # Prefer multi-token brand for better disambiguation (e.g. "morgan stanley")
    if len(tokens) >= 2 and len(tokens[0]) <= 6:
        candidate = f"{tokens[0]}{tokens[1]}.com"
    else:
        candidate = f"{tokens[0]}.com"
    return candidate if is_safe_domain(candidate) else None


def best_domain(employer_name: str) -> str | None:
    """Public API: return the best-guess domain or None.

    1. Curated mapping lookup (covers ~200 top sponsors)
    2. Fallback heuristic with safety checks
    3. None (caller should skip Hunter for this company)
    """
    return lookup_domain(employer_name) or fallback_guess_domain(employer_name)


def confident_domain(employer_name: str) -> str | None:
    """Return ONLY a curated-mapping domain match. Never falls back to heuristic.

    Use this when you don't want to waste a paid API call on a guessed domain
    that's likely wrong (e.g. "stateuniversity.com", "district.com").

    Returns None for entities not in the curated map -- caller should skip
    paid enrichment and use only free harvesters (team-page, GitHub, etc.).
    """
    d = lookup_domain(employer_name)
    return d if (d and is_safe_domain(d)) else None

