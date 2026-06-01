"""
PlaceUp Career — Deduplication Utilities
Content hashing for job deduplication, inspired by JobFunnel's approach.
"""

import hashlib
from difflib import SequenceMatcher


def generate_content_hash(title: str, company: str, location: str, visa_country: str | None = None) -> str:
    """Generate a SHA256 hash for deduplication.

    Creates a unique fingerprint from the core job identifiers.
    Used to prevent duplicate job entries during scraping cycles.

    Args:
        title: Job title
        company: Company name
        location: Job location
        visa_country: Optional ISO country code for global duplicate separation.

    Returns:
        SHA256 hex digest string
    """
    normalized = f"{title.lower().strip()}|{company.lower().strip()}|{location.lower().strip()}"
    if visa_country:
        normalized = f"{normalized}|{visa_country.lower().strip()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def is_near_duplicate(
    title1: str, company1: str,
    title2: str, company2: str,
    threshold: float = 0.90,
) -> bool:
    """Check if two jobs are near-duplicates using fuzzy string matching.

    Uses SequenceMatcher ratio (0-1) to compare title + company.
    A threshold of 0.90 catches minor variations like:
    - "Sr. Software Engineer" vs "Senior Software Engineer"
    - "Google LLC" vs "Google Inc."

    Args:
        title1, company1: First job identifiers
        title2, company2: Second job identifiers
        threshold: Minimum similarity ratio (default 0.90)

    Returns:
        True if the jobs are likely duplicates
    """
    combined1 = f"{title1.lower()} @ {company1.lower()}"
    combined2 = f"{title2.lower()} @ {company2.lower()}"
    ratio = SequenceMatcher(None, combined1, combined2).ratio()
    return ratio >= threshold


def generate_job_id(title: str, company: str, location: str, visa_country: str | None = None) -> str:
    """Generate a unique job ID from core identifiers.

    Uses the first 12 characters of the content hash as a short ID.
    This is used as the Firestore document ID.

    Args:
        title: Job title
        company: Company name
        location: Job location

    Returns:
        12-character hex string
    """
    return generate_content_hash(title, company, location, visa_country=visa_country)[:12]
