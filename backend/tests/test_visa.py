"""
Tests for Visa Classifier — validates keyword scoring logic.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.visa_classifier import classify_job


def test_h1b_positive_classification():
    """Job with clear H1B sponsorship signals should score high."""
    result = classify_job(
        title="Senior Software Engineer",
        company="Google",
        description=(
            "We are looking for a Senior Software Engineer to join our Cloud team. "
            "H-1B visa sponsorship is available for qualified candidates. "
            "We are an equal opportunity employer and welcome international applicants."
        ),
    )
    assert result.visa_h1b is True
    assert result.score >= 50
    assert result.h1b_verified is True  # Google is a known sponsor
    assert not result.should_discard


def test_negative_visa_classification():
    """Job with 'no sponsorship' should score low."""
    result = classify_job(
        title="Analyst",
        company="Small Corp",
        description=(
            "We are looking for an Analyst. "
            "No visa sponsorship is available for this position. "
            "US citizens only."
        ),
    )
    assert result.score < 20
    assert len(result.negative_hits) > 0
    assert result.should_discard is True


def test_opt_classification():
    """Job mentioning OPT should flag OPT eligibility."""
    result = classify_job(
        title="Data Scientist Intern",
        company="TechStartup",
        description=(
            "Great opportunity for international students on OPT. "
            "STEM OPT extension eligible. F-1 students welcome."
        ),
    )
    assert result.visa_opt is True
    assert result.visa_stem_opt is True
    assert result.score >= 30


def test_neutral_job():
    """Job with no visa keywords should score low."""
    result = classify_job(
        title="Marketing Manager",
        company="Local Business",
        description=(
            "We need a marketing manager to lead our campaigns. "
            "Experience with social media and content creation required."
        ),
    )
    assert result.score < 30
    assert result.confidence == "low"


def test_major_sponsor_bonus():
    """Known major sponsors should get automatic verification."""
    result = classify_job(
        title="Product Manager",
        company="Microsoft",
        description="Join the Azure team as a Product Manager.",
    )
    assert result.h1b_verified is True
    assert result.visa_h1b is True
    assert result.score >= 25


def test_security_clearance_penalty():
    """Jobs requiring security clearance should be penalized."""
    result = classify_job(
        title="Systems Engineer",
        company="Defense Corp",
        description=(
            "Top Secret clearance required. "
            "Must be a U.S. person per ITAR regulations."
        ),
    )
    assert result.score < 10
    assert len(result.negative_hits) >= 2


if __name__ == "__main__":
    test_h1b_positive_classification()
    test_negative_visa_classification()
    test_opt_classification()
    test_neutral_job()
    test_major_sponsor_bonus()
    test_security_clearance_penalty()
    print("✅ All visa classifier tests passed!")
