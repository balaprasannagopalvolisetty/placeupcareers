"""
Tests for text processing utilities.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.text_processing import (
    clean_text,
    extract_keywords,
    extract_skills_from_text,
    compute_keyword_overlap,
    truncate_text,
)
from app.utils.deduplication import (
    generate_content_hash,
    generate_job_id,
    is_near_duplicate,
)
from app.utils.job_quality import (
    clean_job_company,
    clean_job_description,
    infer_posted_at,
    is_probably_job_search_page,
)


# ─── Text Processing Tests ────────────────────────────────────

def test_clean_text_removes_html():
    """HTML tags should be stripped."""
    result = clean_text("<p>Hello <b>world</b></p>")
    assert "<" not in result
    assert "Hello" in result


def test_clean_text_removes_urls():
    """URLs should be removed."""
    result = clean_text("Visit https://example.com for details")
    assert "https://" not in result


def test_extract_keywords():
    """Should extract relevant keywords excluding stop words."""
    text = "Python developer with experience in React and AWS cloud computing"
    keywords = extract_keywords(text, top_n=10)
    assert "python" in keywords
    assert "react" in keywords
    assert "aws" in keywords
    # Stop words should not appear
    assert "with" not in keywords
    assert "and" not in keywords


def test_extract_skills():
    """Should recognize known technical skills."""
    text = "Proficient in Python, JavaScript, React, Docker, and Kubernetes"
    skills = extract_skills_from_text(text)
    assert "python" in skills
    assert "javascript" in skills
    assert "react" in skills
    assert "docker" in skills
    assert "kubernetes" in skills


def test_keyword_overlap():
    """Should correctly compute overlap between keyword lists."""
    kw1 = ["python", "react", "docker", "aws"]
    kw2 = ["python", "react", "kubernetes", "aws", "terraform"]

    matched, missing, pct = compute_keyword_overlap(kw1, kw2)
    assert "python" in matched
    assert "react" in matched
    assert "kubernetes" in missing
    assert "terraform" in missing
    assert pct == 60.0  # 3 out of 5


def test_truncate_text():
    """Should truncate text at sentence boundary."""
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    result = truncate_text(text, max_chars=40)
    assert len(result) <= 45  # Allow for sentence boundary
    assert result.endswith(".")


# ─── Deduplication Tests ───────────────────────────────────────

def test_content_hash_deterministic():
    """Same inputs should produce same hash."""
    hash1 = generate_content_hash("Engineer", "Google", "NYC")
    hash2 = generate_content_hash("Engineer", "Google", "NYC")
    assert hash1 == hash2


def test_content_hash_case_insensitive():
    """Hash should be case-insensitive."""
    hash1 = generate_content_hash("Engineer", "Google", "NYC")
    hash2 = generate_content_hash("ENGINEER", "GOOGLE", "nyc")
    assert hash1 == hash2


def test_near_duplicate_detection():
    """Similar job titles should be detected as duplicates."""
    assert is_near_duplicate(
        "Senior Software Engineer", "Google",
        "Sr. Software Engineer", "Google",
    ) is True


def test_non_duplicate_detection():
    """Different jobs should not be flagged as duplicates."""
    assert is_near_duplicate(
        "Software Engineer", "Google",
        "Data Scientist", "Meta",
    ) is False


def test_job_id_generation():
    """Job ID should be 12 characters."""
    job_id = generate_job_id("Engineer", "Google", "NYC")
    assert len(job_id) == 12


def test_linkedin_company_is_extracted_from_description():
    description = """
Security Engineer, AWS Security
LinkedIn
United States
Company logo for, Amazon Web Services (AWS).
Amazon Web Services (AWS)
About the job
Description
We're looking for a Security Engineer.
"""
    assert clean_job_company("LinkedIn", description) == "Amazon Web Services (AWS)"


def test_linkedin_company_is_extracted_from_short_snippet():
    description = "Security Engineer Security Engineer Google Atlanta, GA 5 hours ago"
    assert clean_job_company("LinkedIn", description, "Security Engineer") == "Google"


def test_linkedin_search_page_titles_are_rejected():
    assert is_probably_job_search_page(
        "Senior Security Engineer jobs",
        "LinkedIn",
        "Senior Security Engineer jobs",
        "linkedin",
    )


def test_relative_posted_date_is_inferred():
    from datetime import datetime, timezone

    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    posted = infer_posted_at(None, "Seattle, WA · Reposted 6 days ago", now=now)
    assert posted.date().isoformat() == "2026-05-20"


def test_linkedin_description_chrome_is_trimmed():
    description = "Header junk\nApply\nAbout the job\nDescription\nReal job description"
    assert clean_job_description(description).startswith("About the job")
    assert "Header junk" not in clean_job_description(description)


if __name__ == "__main__":
    test_clean_text_removes_html()
    test_clean_text_removes_urls()
    test_extract_keywords()
    test_extract_skills()
    test_keyword_overlap()
    test_truncate_text()
    test_content_hash_deterministic()
    test_content_hash_case_insensitive()
    test_near_duplicate_detection()
    test_non_duplicate_detection()
    test_job_id_generation()
    print("✅ All utility tests passed!")
