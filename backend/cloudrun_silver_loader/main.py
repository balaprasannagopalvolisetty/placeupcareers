import json
import logging
import os
from datetime import datetime

import functions_framework
import psycopg2
from google.cloud import firestore
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "ra-jobs")
FIRESTORE_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "jobs")

DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS")
DB_NAME = os.environ.get("DB_NAME", "jobssilverdb")
DB_HOST = os.environ.get("DB_HOST", "/cloudsql/steel-shine-492401-u6:us-east1:placeup-backend")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))

db = firestore.Client(database=FIRESTORE_DATABASE)


def get_db_connection():
    if not DB_PASS:
        raise RuntimeError("DB_PASS is required. Store it in Secret Manager and map it to the function.")
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
    )


def parse_iso_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def first_or_none(arr):
    return arr[0] if isinstance(arr, list) and len(arr) > 0 else None


def ensure_text(value):
    if value is None:
        return None
    return str(value)


def ensure_text_array(value):
    if value is None:
        return None
    if isinstance(value, list):
        cleaned = [str(v) for v in value if v is not None and str(v).strip() != ""]
        return cleaned if cleaned else None
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return None


def ensure_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def ensure_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def ensure_json_string(value):
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except Exception:
        return None


def log_record_types(record, label="record"):
    try:
        type_map = [type(v).__name__ for v in record]
        logger.info("%s field types: %s", label, type_map)
    except Exception:
        logger.exception("Failed to log record types")


@functions_framework.http
def clean_and_load_jobs(request):
    """Fetch raw jobs from Firestore bronze layer, transform to silver, and upsert into Cloud SQL."""

    try:
        docs = db.collection(FIRESTORE_COLLECTION).stream()
        logger.info("Data read success from Firestore.")
    except Exception as e:
        logger.exception("Error reading Firestore")
        return (f"Error reading Firestore: {e}", 500)

    clean_records = []
    skipped_count = 0

    for doc in docs:
        try:
            raw_job = doc.to_dict() or {}

            job_id_raw = raw_job.get("id")
            if not job_id_raw:
                skipped_count += 1
                continue

            try:
                job_id = int(str(job_id_raw))
            except Exception:
                logger.warning("Skipping record with invalid id: %s", job_id_raw)
                skipped_count += 1
                continue

            title = ensure_text(raw_job.get("title")) or "Untitled"
            organization = ensure_text(raw_job.get("organization"))
            organization_url = ensure_text(raw_job.get("organization_url"))
            job_url = ensure_text(raw_job.get("url"))
            source_type = ensure_text(raw_job.get("source_type"))
            source = ensure_text(raw_job.get("source"))
            source_domain = ensure_text(raw_job.get("source_domain"))
            employer_domain = ensure_text(raw_job.get("domain_derived"))

            date_posted = parse_iso_timestamp(raw_job.get("date_posted"))
            date_created = parse_iso_timestamp(raw_job.get("date_created"))
            date_valid_through = parse_iso_timestamp(raw_job.get("date_validthrough"))

            location_type = ensure_text(raw_job.get("location_type")) or None
            employment_type = ensure_text_array(raw_job.get("employment_type"))
            remote_flag = ensure_bool(raw_job.get("remote_derived"), False)

            city = ensure_text(first_or_none(raw_job.get("cities_derived")))
            county = ensure_text(first_or_none(raw_job.get("counties_derived")))
            region = ensure_text(first_or_none(raw_job.get("regions_derived")))
            country = ensure_text(first_or_none(raw_job.get("countries_derived")))
            full_location = ensure_text(first_or_none(raw_job.get("locations_derived")))
            timezone = ensure_text(first_or_none(raw_job.get("timezones_derived")))
            latitude = ensure_float(first_or_none(raw_job.get("lats_derived")))
            longitude = ensure_float(first_or_none(raw_job.get("lngs_derived")))

            locations_raw_obj = raw_job.get("locations_raw")
            salary_raw_obj = raw_job.get("salary_raw")

            locations_raw = ensure_json_string(locations_raw_obj)
            salary_raw = ensure_json_string(salary_raw_obj)

            first_location = first_or_none(locations_raw_obj) if isinstance(locations_raw_obj, list) else None
            address = first_location.get("address") if isinstance(first_location, dict) else {}

            street_address = ensure_text(address.get("streetAddress")) if isinstance(address, dict) else None
            postal_code = ensure_text(address.get("postalCode")) if isinstance(address, dict) else None
            address_locality = ensure_text(address.get("addressLocality")) if isinstance(address, dict) else None
            address_region = ensure_text(address.get("addressRegion")) if isinstance(address, dict) else None
            address_country = ensure_text(address.get("addressCountry")) if isinstance(address, dict) else None

            description_text = ensure_text(raw_job.get("description_text"))
            record_source = "firestore.jobs"
            is_active = True

            clean_records.append((
                job_id,
                title,
                organization,
                organization_url,
                job_url,
                source_type,
                source,
                source_domain,
                employer_domain,
                date_posted,
                date_created,
                date_valid_through,
                location_type,
                employment_type,
                remote_flag,
                city,
                county,
                region,
                country,
                full_location,
                timezone,
                latitude,
                longitude,
                street_address,
                postal_code,
                address_locality,
                address_region,
                address_country,
                description_text,
                locations_raw,
                salary_raw,
                record_source,
                is_active,
            ))

        except Exception as row_error:
            skipped_count += 1
            logger.exception("Skipping one record due to transform error: %s", row_error)
            continue

    if not clean_records:
        return ("No records found to process.", 200)

    insert_query = """
        INSERT INTO silver_posts (
            job_id, title, organization, organization_url, job_url, source_type, source,
            source_domain, employer_domain, date_posted, date_created, date_valid_through,
            location_type, employment_type, remote_flag, city, county, region, country,
            full_location, timezone, latitude, longitude, street_address, postal_code,
            address_locality, address_region, address_country, description_text,
            locations_raw, salary_raw, record_source, is_active
        )
        VALUES %s
        ON CONFLICT (job_id) DO UPDATE SET
            title = EXCLUDED.title,
            organization = EXCLUDED.organization,
            organization_url = EXCLUDED.organization_url,
            job_url = EXCLUDED.job_url,
            source_type = EXCLUDED.source_type,
            source = EXCLUDED.source,
            source_domain = EXCLUDED.source_domain,
            employer_domain = EXCLUDED.employer_domain,
            date_posted = EXCLUDED.date_posted,
            date_created = EXCLUDED.date_created,
            date_valid_through = EXCLUDED.date_valid_through,
            location_type = EXCLUDED.location_type,
            employment_type = EXCLUDED.employment_type,
            remote_flag = EXCLUDED.remote_flag,
            city = EXCLUDED.city,
            county = EXCLUDED.county,
            region = EXCLUDED.region,
            country = EXCLUDED.country,
            full_location = EXCLUDED.full_location,
            timezone = EXCLUDED.timezone,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            street_address = EXCLUDED.street_address,
            postal_code = EXCLUDED.postal_code,
            address_locality = EXCLUDED.address_locality,
            address_region = EXCLUDED.address_region,
            address_country = EXCLUDED.address_country,
            description_text = EXCLUDED.description_text,
            locations_raw = EXCLUDED.locations_raw,
            salary_raw = EXCLUDED.salary_raw,
            record_source = EXCLUDED.record_source,
            is_active = EXCLUDED.is_active,
            silver_updated_at = CURRENT_TIMESTAMP;
    """

    row_template = """(
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s::jsonb, %s::jsonb, %s, %s
    )"""

    master_sync_query = """
        WITH source_rows AS (
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
            posted_at, first_seen_at, last_seen_at, source_priority, merged_sources, extra_metadata
        FROM source_rows
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
            status = EXCLUDED.status,
            posted_at = EXCLUDED.posted_at,
            last_seen_at = EXCLUDED.last_seen_at,
            merged_sources = (
                SELECT jsonb_agg(DISTINCT value)
                FROM jsonb_array_elements_text(master_jobs.merged_sources || EXCLUDED.merged_sources) AS t(value)
            ),
            extra_metadata = master_jobs.extra_metadata || EXCLUDED.extra_metadata
        WHERE master_jobs.source_priority >= EXCLUDED.source_priority;
    """

    try:
        logger.info("Trying to establish connection with PostgreSQL...")
        conn = get_db_connection()
        logger.info("Connection successful.")
        cursor = conn.cursor()

        if clean_records:
            log_record_types(clean_records[0], label="first_clean_record")

        execute_values(cursor, insert_query, clean_records, template=row_template, page_size=500)
        cursor.execute(master_sync_query)
        conn.commit()

        cursor.close()
        conn.close()

    except Exception as e:
        logger.exception("Error writing to Cloud SQL")
        if clean_records:
            try:
                log_record_types(clean_records[0], label="failed_first_record")
                logger.info("Failed first record sample: %s", clean_records[0])
            except Exception:
                logger.exception("Could not log failed record sample")
        return (f"Error writing to Cloud SQL: {e}", 500)

    return (
        f"Success! {len(clean_records)} jobs transformed from bronze and loaded into silver. "
        f"Skipped: {skipped_count}",
        200,
    )
