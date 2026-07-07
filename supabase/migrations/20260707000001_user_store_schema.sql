-- ============================================================================
-- PlaceUp — User-domain schema (migrated from Firestore)
-- Applied via: supabase db push
--
-- Timestamps are stored as ISO-8601 text to preserve exact Firestore
-- behaviour (the app sorts/returns them as strings). All tables carry an
-- `extra` JSONB catch-all so no Firestore field is ever silently dropped.
-- ============================================================================

create table if not exists public.users (
    id               text primary key,
    email            text not null,
    password_hash    text not null default '',
    first_name       text not null default '',
    last_name        text not null default '',
    plan             text not null default 'Pro',
    visa_status      text,
    experience_years text,
    phone            text,
    location         text,
    "current_role"   text,    -- quoted: CURRENT_ROLE is a reserved word
    current_company  text,
    summary          text,
    linkedin_url     text,
    github_url       text,
    portfolio_url    text,
    email_verified   boolean not null default false,
    email_verified_at text,
    created_at       text not null,
    updated_at       text not null,
    extra            jsonb not null default '{}'::jsonb
);
create unique index if not exists users_email_lower_uidx on public.users (lower(email));

create table if not exists public.user_preferences (
    user_id          text primary key,
    visa_status      text,
    experience_level text,
    target_roles     jsonb not null default '[]'::jsonb,
    target_locations jsonb not null default '[]'::jsonb,
    job_preferences  jsonb,
    notification_new_jobs        boolean,
    notification_daily_digest    boolean,
    notification_weekly_summary  boolean,
    notification_ats_updates     boolean,
    notification_marketing_emails boolean,
    updated_at       text not null,
    extra            jsonb not null default '{}'::jsonb
);

create table if not exists public.user_alert_settings (
    user_id      text primary key,
    email_alerts boolean not null default true,
    daily_digest boolean not null default true,
    weekly_report boolean not null default false,
    extra        jsonb not null default '{}'::jsonb
);

create table if not exists public.user_alerts (
    id          text primary key,
    user_id     text not null,
    title       text not null default '',
    company     text not null default '',
    location    text not null default '',
    salary      text not null default '',
    match_score integer not null default 0,
    visa        text not null default '',
    message     text,
    unread      boolean not null default true,
    created_at  text not null,
    extra       jsonb not null default '{}'::jsonb
);
create index if not exists user_alerts_user_idx on public.user_alerts (user_id, created_at desc);

create table if not exists public.user_resumes (
    id           text primary key,
    user_id      text not null,
    name         text not null default '',
    uploaded_at  text not null,
    score        integer not null default 0,
    size_bytes   integer not null default 0,
    active       boolean not null default false,
    storage_path text,
    parsed_text  text not null default '',
    parsed_json  jsonb not null default '{}'::jsonb,
    extra        jsonb not null default '{}'::jsonb
);
create index if not exists user_resumes_user_idx on public.user_resumes (user_id);

create table if not exists public.user_applications (
    id                 text primary key,          -- "<user_id>_<job_id>"
    user_id            text not null,
    job_id             text not null,
    title              text not null default '',
    company            text not null default '',
    location           text not null default '',
    job_url            text not null default '',
    description        text not null default '',
    match_score        integer not null default 0,
    status             text not null default 'applied',
    not_applied_reason text not null default '',
    heard_back         boolean,
    position_open      boolean,
    salary_offered     text not null default '',
    notes              text not null default '',
    created_at         text,
    updated_at         text not null,
    extra              jsonb not null default '{}'::jsonb
);
create index if not exists user_applications_user_idx on public.user_applications (user_id);

create table if not exists public.user_tailor_queue (
    id              text primary key,             -- "<user_id>_<job_id>"
    user_id         text not null,
    job_id          text not null,
    title           text not null default '',
    company         text not null default '',
    location        text not null default '',
    job_url         text not null default '',
    description     text not null default '',
    match_score     integer not null default 0,
    status          text not null default 'queued',
    queued_day      text not null default '',
    ats_score       integer,
    generated_at    text,
    keyword_targets jsonb,
    last_format     text,
    filename        text,
    summary         text,
    created_at      text,
    updated_at      text not null,
    extra           jsonb not null default '{}'::jsonb
);
create index if not exists user_tailor_queue_user_idx on public.user_tailor_queue (user_id, queued_day);

create table if not exists public.auth_sessions (
    id           text primary key,
    user_id      text not null,
    refresh_hash text not null,
    created_at   text not null,
    updated_at   text not null,
    expires_at   text not null,
    revoked      boolean not null default false,
    user_agent   text not null default '',
    ip_address   text not null default '',
    extra        jsonb not null default '{}'::jsonb
);
create index if not exists auth_sessions_refresh_idx on public.auth_sessions (refresh_hash) where not revoked;
create index if not exists auth_sessions_user_idx on public.auth_sessions (user_id) where not revoked;

create table if not exists public.password_resets (
    token_hash text primary key,                  -- sha-256 hex, trimmed to 128
    user_id    text not null,
    expires_at text not null,
    created_at text not null
);
create index if not exists password_resets_user_idx on public.password_resets (user_id);

create table if not exists public.email_verifications (
    token_hash text primary key,
    user_id    text not null,
    expires_at text not null,
    created_at text not null
);
create index if not exists email_verifications_user_idx on public.email_verifications (user_id);

create table if not exists public.agreements (
    id         text primary key,
    user_id    text not null,
    email      text not null default '',
    version    text not null default '',
    documents  jsonb not null default '["terms","privacy"]'::jsonb,
    accepted   boolean not null default true,
    ip_address text not null default '',
    user_agent text not null default '',
    created_at text not null,
    extra      jsonb not null default '{}'::jsonb
);
create index if not exists agreements_user_idx on public.agreements (user_id);

create table if not exists public.role_requests (
    id         text primary key,
    user_id    text not null,
    email      text not null default '',
    role       text not null default '',
    country    text not null default '',
    note       text not null default '',
    status     text not null default 'pending',   -- pending | approved | rejected
    admin_note text not null default '',
    decided_by text not null default '',
    decided_at text not null default '',
    created_at text not null,
    updated_at text not null,
    extra      jsonb not null default '{}'::jsonb
);
create index if not exists role_requests_status_idx on public.role_requests (status);
create index if not exists role_requests_user_idx on public.role_requests (user_id);

create table if not exists public.admin_events (
    id         text primary key,
    kind       text not null,
    label      text not null default '',
    user_id    text not null default '',
    email      text not null default '',
    actor      text not null default '',
    level      text not null default 'info',
    meta       jsonb not null default '{}'::jsonb,
    created_at text not null
);
create index if not exists admin_events_user_idx on public.admin_events (user_id);
create index if not exists admin_events_kind_idx on public.admin_events (kind);

create table if not exists public.waitlist (
    id              text primary key,             -- sha-256(email)[:32]
    email           text not null,
    name            text not null default '',
    source          text not null default 'invite_gate',
    last_ip         text not null default '',
    last_user_agent text not null default '',
    notified        boolean not null default false,
    created_at      text not null,
    updated_at      text not null,
    extra           jsonb not null default '{}'::jsonb
);

create table if not exists public.user_feedback (
    id         text primary key,
    user_id    text not null default '',
    email      text not null default '',
    rating     integer not null default 0,
    category   text not null default 'general',
    message    text not null default '',
    page       text not null default '',
    user_agent text not null default '',
    status     text not null default 'new',       -- new | reviewed | resolved
    created_at text not null,
    updated_at text,
    extra      jsonb not null default '{}'::jsonb
);
create index if not exists user_feedback_category_idx on public.user_feedback (category);
