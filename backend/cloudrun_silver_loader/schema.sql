CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS silver_posts (
  job_id BIGINT PRIMARY KEY,
  title TEXT NOT NULL,
  organization TEXT,
  organization_url TEXT,
  job_url TEXT,
  source_type TEXT,
  source TEXT,
  source_domain TEXT,
  employer_domain TEXT,
  date_posted TIMESTAMPTZ,
  date_created TIMESTAMPTZ,
  date_valid_through TIMESTAMPTZ,
  location_type TEXT,
  employment_type TEXT[],
  remote_flag BOOLEAN NOT NULL DEFAULT FALSE,
  city TEXT,
  county TEXT,
  region TEXT,
  country TEXT,
  full_location TEXT,
  timezone TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  street_address TEXT,
  postal_code TEXT,
  address_locality TEXT,
  address_region TEXT,
  address_country TEXT,
  description_text TEXT,
  locations_raw JSONB,
  salary_raw JSONB,
  record_source TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  silver_created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  silver_updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_silver_posts_active_posted
  ON silver_posts (is_active, date_posted);

CREATE INDEX IF NOT EXISTS ix_silver_posts_location
  ON silver_posts (country, region, city);

CREATE INDEX IF NOT EXISTS ix_silver_posts_organization
  ON silver_posts (organization);

CREATE INDEX IF NOT EXISTS ix_silver_posts_source
  ON silver_posts (source);

CREATE TABLE IF NOT EXISTS master_jobs (
  id TEXT PRIMARY KEY,
  canonical_key TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  company TEXT NOT NULL DEFAULT '',
  location TEXT,
  country TEXT,
  source_name TEXT NOT NULL,
  source_job_id TEXT,
  source_url TEXT,
  description TEXT,
  employment_type TEXT,
  remote_type TEXT,
  salary_min NUMERIC(12, 2),
  salary_max NUMERIC(12, 2),
  currency TEXT,
  visa_opt BOOLEAN NOT NULL DEFAULT FALSE,
  visa_stem_opt BOOLEAN NOT NULL DEFAULT FALSE,
  visa_h1b BOOLEAN NOT NULL DEFAULT FALSE,
  h1b_verified BOOLEAN NOT NULL DEFAULT FALSE,
  visa_score INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  posted_at TIMESTAMPTZ,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  source_priority INTEGER NOT NULL DEFAULT 50,
  merged_sources JSONB NOT NULL DEFAULT '[]',
  extra_metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_master_jobs_status_seen
  ON master_jobs (status, last_seen_at);

CREATE INDEX IF NOT EXISTS ix_master_jobs_company
  ON master_jobs (company);

CREATE INDEX IF NOT EXISTS ix_master_jobs_source
  ON master_jobs (source_name);

CREATE INDEX IF NOT EXISTS ix_master_jobs_visa
  ON master_jobs (visa_score);
