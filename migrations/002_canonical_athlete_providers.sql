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
