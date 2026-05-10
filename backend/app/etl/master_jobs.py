"""Build the deduplicated master job table from all production sources."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.db.postgres import PostgresClient

logger = logging.getLogger("placeup.etl.master_jobs")


MASTER_SYNC_SQL = """
WITH source_rows AS (
    SELECT
        j.id::text AS id,
        encode(digest(lower(trim(coalesce(j.title, ''))) || '|' || lower(trim(coalesce(c.name, ''))) || '|' || lower(trim(coalesce(j.location, ''))), 'sha256'), 'hex') AS canonical_key,
        j.title,
        coalesce(c.name, '') AS company,
        j.location,
        j.country,
        j.source_name,
        j.source_job_id,
        j.source_url,
        j.description,
        j.employment_type,
        j.remote_type,
        j.salary_min,
        j.salary_max,
        j.currency,
        j.visa_opt,
        j.visa_stem_opt,
        j.visa_h1b,
        j.h1b_verified,
        j.visa_score,
        j.status,
        j.posted_at,
        j.first_seen_at,
        j.last_seen_at,
        10 AS source_priority,
        jsonb_build_array(j.source_name) AS merged_sources,
        coalesce(j.extra_metadata, '{}'::jsonb) || jsonb_build_object('source_table', 'jobs', 'category', j.category) AS extra_metadata
    FROM jobs j
    LEFT JOIN companies c ON c.id = j.company_id
    WHERE coalesce(j.title, '') <> ''

    UNION ALL

    SELECT
        ('silver_' || sp.job_id::text) AS id,
        encode(digest(lower(trim(coalesce(sp.title, ''))) || '|' || lower(trim(coalesce(sp.organization, ''))) || '|' || lower(trim(coalesce(sp.full_location, sp.city, ''))), 'sha256'), 'hex') AS canonical_key,
        sp.title,
        coalesce(sp.organization, '') AS company,
        coalesce(sp.full_location, sp.city, sp.region, sp.country, '') AS location,
        sp.country,
        coalesce(sp.source, sp.source_type, 'silver_loader') AS source_name,
        sp.job_id::text AS source_job_id,
        sp.job_url AS source_url,
        sp.description_text AS description,
        array_to_string(sp.employment_type, ', ') AS employment_type,
        sp.location_type AS remote_type,
        NULL::numeric AS salary_min,
        NULL::numeric AS salary_max,
        'USD' AS currency,
        false AS visa_opt,
        false AS visa_stem_opt,
        false AS visa_h1b,
        false AS h1b_verified,
        0 AS visa_score,
        CASE WHEN sp.is_active THEN 'active' ELSE 'inactive' END AS status,
        sp.date_posted AS posted_at,
        sp.silver_created_at AS first_seen_at,
        sp.silver_updated_at AS last_seen_at,
        30 AS source_priority,
        jsonb_build_array(coalesce(sp.source, sp.source_type, 'silver_loader')) AS merged_sources,
        jsonb_build_object(
            'source_table', 'silver_posts',
            'organization_url', sp.organization_url,
            'source_domain', sp.source_domain,
            'employer_domain', sp.employer_domain,
            'locations_raw', sp.locations_raw,
            'salary_raw', sp.salary_raw
        ) AS extra_metadata
    FROM silver_posts sp
    WHERE coalesce(sp.title, '') <> ''
),
ranked AS (
    SELECT *,
        row_number() OVER (
            PARTITION BY canonical_key
            ORDER BY source_priority ASC, coalesce(posted_at, last_seen_at) DESC NULLS LAST
        ) AS rn,
        min(first_seen_at) OVER (PARTITION BY canonical_key) AS min_first_seen_at,
        max(last_seen_at) OVER (PARTITION BY canonical_key) AS max_last_seen_at
    FROM source_rows
),
source_groups AS (
    SELECT canonical_key, jsonb_agg(DISTINCT source_name) AS all_sources
    FROM source_rows
    GROUP BY canonical_key
)
INSERT INTO master_jobs (
    id, canonical_key, title, company, location, country, source_name, source_job_id,
    source_url, description, employment_type, remote_type, salary_min, salary_max,
    currency, visa_opt, visa_stem_opt, visa_h1b, h1b_verified, visa_score, status,
    posted_at, first_seen_at, last_seen_at, source_priority, merged_sources, extra_metadata
)
SELECT
    id, canonical_key, title, company, location, country, source_name, source_job_id,
    source_url, description, employment_type, remote_type, salary_min, salary_max,
    currency, visa_opt, visa_stem_opt, visa_h1b, h1b_verified, visa_score, status,
    posted_at, min_first_seen_at, max_last_seen_at, source_priority, sg.all_sources, extra_metadata
FROM ranked
JOIN source_groups sg USING (canonical_key)
WHERE rn = 1
ON CONFLICT (canonical_key) DO UPDATE SET
    title = EXCLUDED.title,
    company = EXCLUDED.company,
    location = EXCLUDED.location,
    country = EXCLUDED.country,
    source_name = EXCLUDED.source_name,
    source_job_id = EXCLUDED.source_job_id,
    source_url = EXCLUDED.source_url,
    description = EXCLUDED.description,
    employment_type = EXCLUDED.employment_type,
    remote_type = EXCLUDED.remote_type,
    salary_min = EXCLUDED.salary_min,
    salary_max = EXCLUDED.salary_max,
    currency = EXCLUDED.currency,
    visa_opt = EXCLUDED.visa_opt,
    visa_stem_opt = EXCLUDED.visa_stem_opt,
    visa_h1b = EXCLUDED.visa_h1b,
    h1b_verified = EXCLUDED.h1b_verified,
    visa_score = EXCLUDED.visa_score,
    status = EXCLUDED.status,
    posted_at = EXCLUDED.posted_at,
    last_seen_at = EXCLUDED.last_seen_at,
    source_priority = EXCLUDED.source_priority,
    merged_sources = EXCLUDED.merged_sources,
    extra_metadata = EXCLUDED.extra_metadata;
"""


def rebuild_master_jobs(client: PostgresClient | None = None) -> int:
    client = client or PostgresClient()
    with client.session() as db:
        result = db.execute(text(MASTER_SYNC_SQL))
        count = int(result.rowcount or 0)
    logger.info("Master jobs sync complete: %s rows upserted", count)
    return count


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    rebuild_master_jobs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
