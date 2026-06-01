from app.models.job import JobPost, JobSource
from app.services.linkedin_job_details import apply_linkedin_details, parse_linkedin_job_html


def test_parse_linkedin_jobposting_jsonld_extracts_company_and_full_description():
    html = """
    <html>
      <head>
        <meta property="og:url" content="https://www.linkedin.com/jobs/view/1234567890/">
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Emerging Technology / Cybersecurity Engineer",
          "hiringOrganization": {"@type": "Organization", "name": "Zermount, Inc."},
          "jobLocation": {
            "@type": "Place",
            "address": {
              "@type": "PostalAddress",
              "addressLocality": "Arlington",
              "addressRegion": "VA",
              "addressCountry": "United States"
            }
          },
          "employmentType": "FULL_TIME",
          "datePosted": "2026-05-27",
          "description": "<p>Company Description</p><p>Zermount specializes in Cybersecurity.</p><h3>Duties</h3><ul><li>Conduct Security Architecture Reviews.</li><li>Evaluate AI-specific threats.</li></ul>"
        }
        </script>
      </head>
      <body></body>
    </html>
    """

    details = parse_linkedin_job_html(html)

    assert details.company == "Zermount, Inc."
    assert details.title == "Emerging Technology / Cybersecurity Engineer"
    assert details.location == "Arlington, VA, United States"
    assert details.employment_type == "Full Time"
    assert details.source_job_id == ""
    assert details.canonical_url == "https://www.linkedin.com/jobs/view/1234567890"
    assert "Company Description" in details.description
    assert "Conduct Security Architecture Reviews." in details.description
    assert "<p>" not in details.description


def test_apply_linkedin_details_replaces_board_company_and_recomputes_identity():
    job = JobPost(
        id="old",
        title="Emerging Technology / Cybersecurity Engineer",
        company="LinkedIn",
        location="United States",
        description="Emerging Technology / Cybersecurity Engineer Zermount, Inc. Arlington, VA",
        job_url="https://www.linkedin.com/jobs/view/1234567890/?trackingId=abc",
        source=JobSource.LINKEDIN,
        source_job_id="linkedin:old",
        content_hash="old",
    )
    details = parse_linkedin_job_html(
        """
        <script type="application/ld+json">
        {
          "@type": "JobPosting",
          "title": "Emerging Technology / Cybersecurity Engineer",
          "hiringOrganization": {"name": "Zermount, Inc."},
          "jobLocation": {"address": {"addressLocality": "Arlington", "addressRegion": "VA", "addressCountry": "United States"}},
          "description": "A much longer full job description with responsibilities, requirements, cloud security, RMF, ATO, and AI security testing details."
        }
        </script>
        """
    )
    details.source_job_id = "1234567890"
    details.canonical_url = "https://www.linkedin.com/jobs/view/1234567890"

    changed = apply_linkedin_details(job, details)

    assert changed is True
    assert job.company == "Zermount, Inc."
    assert job.location == "Arlington, VA, United States"
    assert job.job_url == "https://www.linkedin.com/jobs/view/1234567890"
    assert job.source_job_id == "linkedin:1234567890"
    assert job.id != "old"
    assert job.content_hash != "old"
    assert job.extra_metadata["linkedin_detail_enriched"] is True
