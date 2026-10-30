-- Migration 002: provider-neutral identity model
--
-- Goal
--   Stop using a provider's id (strava_athlete_id) as the canonical identity.
--   Introduce an app-owned canonical athlete id (uuid) and move per-provider
--   accounts + tokens into a dedicated athlete_providers table. COROS becomes
--   just another provider alongside Strava.
--
-- Strategy (safe for a live beta)
--   This migration is ADDITIVE and idempotent. It does NOT drop the existing
--   strava_* columns or inline tokens. Old Strava code keeps working on the old
--   columns until the application is reworked to use the new model; a later
--   cleanup migration (003) will drop the legacy columns once the code cutover
--   is verified.
--
-- Data at time of writing: 10 athletes, 74 activities, 0 families.
-- Run in the Supabase SQL editor. Safe to run more than once.

-- 0. Extensions ------------------------------------------------------------
create extension if not exists pgcrypto;   -- gen_random_uuid()

-- 1. athletes: add canonical uuid -----------------------------------------
alter table public.athletes
    add column if not exists athlete_id uuid;

-- Backfill a canonical id for every existing athlete.
update public.athletes
    set athlete_id = gen_random_uuid()
    where athlete_id is null;

-- Default + not null going forward.
alter table public.athletes
    alter column athlete_id set default gen_random_uuid();

alter table public.athletes
    alter column athlete_id set not null;

-- created_at for provenance (existing rows get "now"; acceptable for beta).
alter table public.athletes
    add column if not exists created_at timestamptz default now();

update public.athletes
    set created_at = coalesce(created_at, now())
    where created_at is null;

-- Promote athlete_id to a unique key so it can be referenced by FKs.
-- (strava_athlete_id remains as-is for now; not dropped.)
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'athletes_athlete_id_key'
    ) then
        alter table public.athletes
            add constraint athletes_athlete_id_key unique (athlete_id);
    end if;
end $$;

-- 2. athlete_providers: one row per (athlete x provider) ------------------
create table if not exists public.athlete_providers (
    id               uuid primary key default gen_random_uuid(),
    athlete_id       uuid not null
                        references public.athletes (athlete_id)
                        on delete cascade,
    provider         text not null
                        check (provider in ('strava', 'coros', 'garmin', 'wahoo')),
    provider_user_id text not null,
    access_token     text,
    refresh_token    text,
    expires_at       timestamptz,
    scope            text,
    status           text not null default 'active'
                        check (status in ('active', 'revoked', 'error')),
    error_message    text,
    connected_at     timestamptz default now(),
    revoked_at       timestamptz,
    last_sync        timestamptz,
    updated_at       timestamptz default now(),
    -- A given external account links to exactly one athlete.
    unique (provider, provider_user_id)
);

create index if not exists athlete_providers_athlete_idx
    on public.athlete_providers (athlete_id);
create index if not exists athlete_providers_provider_idx
    on public.athlete_providers (provider);

-- Backfill: every existing athlete currently has a Strava link. Create its
-- athlete_providers row from the inline Strava columns.
insert into public.athlete_providers (
    athlete_id, provider, provider_user_id,
    access_token, refresh_token, expires_at,
    status, connected_at, revoked_at, last_sync, updated_at
)
select
    a.athlete_id,
    'strava',
    a.strava_athlete_id::text,
    a.access_token,
    a.refresh_token,
    a.expires_at::timestamptz,
    coalesce(a.status, 'active'),
    a.consent_date::timestamptz,
    a.revoked_at::timestamptz,
    a.last_sync::timestamptz,
    coalesce(a.updated_at::timestamptz, now())
from public.athletes a
where a.strava_athlete_id is not null
  and not exists (
      select 1 from public.athlete_providers p
      where p.provider = 'strava'
        and p.provider_user_id = a.strava_athlete_id::text
  );

-- 3. activities: add canonical athlete link -------------------------------
alter table public.activities
    add column if not exists athlete_id uuid
        references public.athletes (athlete_id);

-- Backfill from the existing strava_athlete_id on activities.
update public.activities act
    set athlete_id = a.athlete_id
    from public.athletes a
    where act.athlete_id is null
      and act.strava_athlete_id is not null
      and a.strava_athlete_id = act.strava_athlete_id;

create index if not exists activities_athlete_idx
    on public.activities (athlete_id);

-- 4. oauth_states: short-lived PKCE/state store for OAuth round-trips -----
-- Holds the PKCE code_verifier and CSRF state between the authorize redirect
-- and the callback. athlete_id is nullable: provider-first signups (COROS
-- model B) create the athlete in the callback, not before.
create table if not exists public.oauth_states (
    state          text primary key,
    provider       text not null
                      check (provider in ('strava', 'coros', 'garmin', 'wahoo')),
    code_verifier  text,
    athlete_id     uuid references public.athletes (athlete_id) on delete set null,
    redirect_after text,
    created_at     timestamptz not null default now(),
    expires_at     timestamptz not null default (now() + interval '15 minutes')
);

create index if not exists oauth_states_expires_idx
    on public.oauth_states (expires_at);

-- Note: legacy columns (athletes.access_token/refresh_token/expires_at/
-- strava_athlete_id, activities.strava_athlete_id) are intentionally retained.
-- They are removed in migration 003 after the application cutover is verified.

-- 5. Row Level Security on the NEW tables ---------------------------------
--
-- CRITICAL: new tables are created with RLS DISABLED by default. Both new
-- tables hold sensitive data (OAuth access/refresh tokens; PKCE verifiers), so
-- we lock them down.
--
-- The application accesses Supabase exclusively via the SERVICE ROLE key
-- (see config.py). The service role BYPASSES RLS, so enabling RLS with NO
-- permissive policies gives the desired result:
--   - service role          -> full access (bypasses RLS)
--   - anon / authenticated   -> no access at all (RLS on, no policy = deny)
-- This keeps tokens strictly server-side.
--
-- Reporting (Google Looker/Data Studio) reads a dedicated VIEW via a dedicated
-- account, NOT these base tables, so locking these tables does not affect it.

alter table public.athlete_providers enable row level security;
alter table public.oauth_states      enable row level security;

-- Force RLS so even the table owner is subject to it. Belt-and-suspenders for
-- token data. (The service role still bypasses RLS.)
alter table public.athlete_providers force row level security;
alter table public.oauth_states      force row level security;

-- Defense-in-depth: revoke any direct API-role grants Supabase may auto-create
-- for new tables, so they are never reachable through the public API.
revoke all on public.athlete_providers from anon, authenticated;
revoke all on public.oauth_states      from anon, authenticated;

-- Intentionally NO anon/authenticated policies are created: with RLS enabled
-- and no policy, those roles are denied. The service role is unaffected.

-- 5b. Backup role access ---------------------------------------------------
--
-- The backup workflow connects as the restricted `malborska_backup` role and
-- runs `pg_dump --enable-row-security`, so it only dumps rows that role can
-- SELECT. Each existing table has a `malborska_backup_<table>_select` policy.
--
-- DECISION (see docs/multi-provider.md):
--   * athlete_providers IS backed up. After this refactor it holds the OAuth
--     tokens that previously lived inline on `athletes` (which is already
--     backed up), so excluding it would silently regress disaster recovery —
--     a restore would leave every athlete disconnected. It therefore needs a
--     SELECT grant + policy for malborska_backup.
--   * oauth_states is NOT backed up. It holds only ephemeral 15-minute PKCE
--     verifiers with no recovery value, and should stay service-role-only.
--
-- NOTE: backing up athlete_providers means S3 backups contain live tokens.
-- This matches today's posture (inline tokens on `athletes` are already
-- dumped); keep S3 backup access controlled accordingly.

grant select on public.athlete_providers to malborska_backup;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename  = 'athlete_providers'
          and policyname = 'malborska_backup_athlete_providers_select'
    ) then
        create policy malborska_backup_athlete_providers_select
            on public.athlete_providers
            for select
            to malborska_backup
            using (true);
    end if;
end $$;

-- No grant/policy for oauth_states on malborska_backup: intentionally excluded
-- from backups.

-- 6. RLS posture of EXISTING tables (athletes, activities) ----------------
--
-- RLS is a TABLE-level setting; the new athlete_id columns inherit whatever
-- policies already exist on athletes/activities. This migration does NOT alter
-- those tables' RLS, so your current posture (and the reporting view) is
-- preserved. Inspect the baseline before running if desired:
--
--   select schemaname, tablename, rowsecurity
--   from pg_tables where schemaname = 'public'
--     and tablename in ('athletes','activities','athlete_providers','oauth_states');
--
--   select tablename, policyname, roles, cmd, qual
--   from pg_policies where schemaname = 'public' order by tablename, policyname;

-- Note: legacy columns (athletes.access_token/refresh_token/expires_at/
-- strava_athlete_id, activities.strava_athlete_id) are intentionally retained.
-- They are removed in migration 003 after the application cutover is verified,
-- AFTER confirming the reporting view does not reference them.
