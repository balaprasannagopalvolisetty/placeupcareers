-- ============================================================================
-- PlaceUp — Supabase security lockdown ("no API leaks")
--
-- The backend talks to this database ONLY via DATABASE_URL (the postgres
-- role over SSL). Nothing should ever be readable through the Supabase
-- Data API (PostgREST) with the anon or authenticated keys.
--
-- Defence in depth, 4 layers:
--   1. Revoke every privilege from anon / authenticated on public schema.
--   2. Default privileges: future tables grant them nothing either.
--   3. Enable RLS on every table in public with NO policies -> deny all,
--      even if a grant slips through later.
--   4. (Dashboard, see runbook) remove `public` from the Data API exposed
--      schemas and keep service_role key server-side only.
--
-- IDEMPOTENT: safe to re-run. Re-run this file (psql -f) after importing
-- the Cloud SQL dump so the restored jobs tables get locked down too.
-- ============================================================================

-- Layer 1: strip API roles of everything in public
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;
revoke usage on schema public from anon, authenticated;

-- Layer 2: future objects get no grants for API roles
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;

-- Layer 3: RLS on with zero policies = deny-by-default for API roles.
-- (The backend's `postgres` role bypasses RLS via BYPASSRLS/ownership,
-- so the app keeps working unchanged.)
do $$
declare
    t record;
begin
    for t in
        select schemaname, tablename
        from pg_tables
        where schemaname = 'public'
    loop
        execute format('alter table %I.%I enable row level security', t.schemaname, t.tablename);
    end loop;
end $$;

-- Drop any leftover permissive policies (none expected; belt-and-braces)
do $$
declare
    p record;
begin
    for p in
        select schemaname, tablename, policyname
        from pg_policies
        where schemaname = 'public'
    loop
        execute format('drop policy %I on %I.%I', p.policyname, p.schemaname, p.tablename);
    end loop;
end $$;
