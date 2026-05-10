"""
PlaceUp Career — Visa Classification Service
Classifies job postings for visa sponsorship compatibility.

Direct port of the JavaScript classifier from backend-pipeline.md.
Uses keyword scoring matrix + USCIS cross-reference for verification.
"""

import re
import logging
from typing import Optional

from app.models.visa import VisaScore

logger = logging.getLogger(__name__)


# ─── Keyword Scoring Matrix ───────────────────────────────────
# Positive keywords with their score contributions
POSITIVE_KEYWORDS = {
    # OPT-friendly signals (+30)
    "opt": 30, "optional practical training": 30,
    "f-1": 30, "f1 visa": 30, "international students welcome": 30,
    "work authorization will be considered": 30,
    "all candidates considered": 25,

    # STEM OPT signals (+40)
    "stem opt": 40, "stem extension": 40, "stem opt extension": 40,
    "24-month extension": 40, "36 months opt": 40,

    # H-1B signals (+50)
    "h-1b": 50, "h1b": 50, "h1-b": 50,
    "visa sponsorship available": 50,
    "visa sponsorship provided": 50,
    "will sponsor": 50, "sponsorship available": 50,
    "we sponsor": 45, "sponsor visa": 45,
    "willing to sponsor": 50,
    "immigration sponsorship": 45,
    "work visa sponsorship": 50,
    "visa transfer": 40,

    # Green Card signals (+35)
    "green card": 35, "permanent residency": 35,
    "gc sponsorship": 35, "perm": 30,

    # General openness (+20)
    "equal opportunity employer": 20,
    "diversity": 15,
    "regardless of immigration status": 40,
    "employment eligibility": 15,
}

# Negative keywords (reduce score)
NEGATIVE_KEYWORDS = {
    "no sponsorship": -60,
    "no visa sponsorship": -60,
    "not sponsor": -50,
    "unable to sponsor": -60,
    "will not sponsor": -60,
    "cannot sponsor": -60,
    "us citizen": -30,
    "us citizens only": -60,
    "citizen only": -50,
    "citizenship required": -50,
    "permanent resident required": -30,
    "must be authorized": -20,
    "clearance required": -40,
    "security clearance": -35,
    "secret clearance": -50,
    "top secret": -55,
    "must be a u.s. person": -50,
    "itar": -45,
    "export controlled": -40,
}


def classify_job(
    title: str,
    company: str,
    description: str,
    uscis_data: Optional[dict] = None,
) -> VisaScore:
    """Classify a job posting for visa sponsorship compatibility.

    Scoring pipeline:
    1. Scan description for positive/negative keywords
    2. Apply score contributions from keyword matrix
    3. Cross-reference employer against USCIS H1B data
    4. Determine visa type flags and confidence level

    Args:
        title: Job title
        company: Company name
        description: Full job description text
        uscis_data: Optional pre-loaded USCIS data for employer

    Returns:
        VisaScore with classification results
    """
    description_lower = description.lower()
    title_lower = title.lower()
    full_text = f"{title_lower} {description_lower}"

    score = 0
    keyword_hits: list[str] = []
    negative_hits: list[str] = []

    # Visa type flags
    visa_opt = False
    visa_stem_opt = False
    visa_h1b = False
    green_card = False

    # ─── Step 1: Positive keyword scanning ─────────────────
    for keyword, points in POSITIVE_KEYWORDS.items():
        if keyword in full_text:
            score += points
            keyword_hits.append(keyword)

            # Set type flags based on keyword category
            if "opt" in keyword and "stem" not in keyword:
                visa_opt = True
            if "stem" in keyword:
                visa_stem_opt = True
                visa_opt = True  # STEM OPT implies OPT
            if any(h in keyword for h in ["h-1b", "h1b", "h1-b", "sponsor", "immigration"]):
                visa_h1b = True
            if any(g in keyword for g in ["green card", "permanent resid", "perm", "gc"]):
                green_card = True

    # ─── Step 2: Negative keyword scanning ─────────────────
    for keyword, penalty in NEGATIVE_KEYWORDS.items():
        if keyword in full_text:
            score += penalty  # penalty is negative
            negative_hits.append(keyword)

    # ─── Step 3: USCIS cross-reference ─────────────────────
    h1b_verified = False
    uscis_petition_count = 0

    if uscis_data:
        uscis_petition_count = uscis_data.get("total_petitions", 0)
        if uscis_petition_count >= 5:
            score += 30
            h1b_verified = True
            visa_h1b = True
            keyword_hits.append(f"USCIS verified ({uscis_petition_count} petitions)")

            if uscis_petition_count >= 50:
                score += 20  # Major sponsor bonus
                keyword_hits.append("Major H1B sponsor (50+ petitions)")

    # ─── Step 4: Industry heuristics ───────────────────────
    # Tech companies are more likely to sponsor
    tech_signals = ["software", "engineer", "developer", "data", "machine learning",
                    "cloud", "devops", "ai ", "artificial intelligence", "ml ",
                    "platform", "infrastructure", "backend", "frontend"]
    tech_count = sum(1 for s in tech_signals if s in full_text)
    if tech_count >= 3:
        score += 10
        keyword_hits.append("Tech industry role")

    # Known major sponsors bonus (top H1B sponsors by petition count)
    major_sponsors = [
        "google", "meta", "amazon", "microsoft", "apple", "nvidia",
        "salesforce", "oracle", "ibm", "intel", "cisco", "adobe",
        "uber", "lyft", "airbnb", "stripe", "coinbase", "databricks",
        "snowflake", "palantir", "tesla", "spacex",
        "infosys", "tcs", "wipro", "cognizant", "hcl", "accenture",
        "deloitte", "kpmg", "ey", "pwc", "mckinsey", "bcg",
        "jpmorgan", "goldman sachs", "morgan stanley", "citadel",
    ]
    company_lower = company.lower()
    if any(sponsor in company_lower for sponsor in major_sponsors):
        score += 25
        h1b_verified = True
        visa_h1b = True
        keyword_hits.append(f"Known major H1B sponsor: {company}")

    # ─── Step 5: Normalize score ───────────────────────────
    score = max(0, min(100, score))

    # Determine confidence level
    total_signals = len(keyword_hits) + len(negative_hits)
    if total_signals >= 5:
        confidence = "high"
    elif total_signals >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # Should discard? (Strong negative signals)
    should_discard = score < 10 and len(negative_hits) > 0

    return VisaScore(
        score=score,
        visa_opt=visa_opt,
        visa_stem_opt=visa_stem_opt,
        visa_h1b=visa_h1b,
        h1b_verified=h1b_verified,
        green_card=green_card,
        keyword_hits=keyword_hits,
        negative_hits=negative_hits,
        uscis_match=uscis_petition_count > 0,
        uscis_petition_count=uscis_petition_count,
        should_discard=should_discard,
        confidence=confidence,
    )
