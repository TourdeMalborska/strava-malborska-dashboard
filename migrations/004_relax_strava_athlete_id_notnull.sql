-- Migration 004: make athlete_id the primary key (allow non-Strava athletes)
--
-- Why
--   Discovered that athletes.strava_athlete_id is the PRIMARY KEY (legacy model
--   keyed every athlete on Strava). A primary key is implicitly NOT NULL, so a
--   model-B athlete originating from COROS/Garmin (no Strava account) cannot be
--   created — insert fails. The canonical athlete_id (uuid) must become the PK.
--
-- What
--   1. Move the primary key from strava_athlete_id to athlete_id.
--   2. Leave strava_athlete_id in place but NULLABLE (not dropped — full
--      legacy cleanup is still deferred pending the reporting-view review).
--   3. Drop the now-redundant UNIQUE constraint on athlete_id (the PK provides
--      uniqueness). athlete_providers.athlete_id / activities.athlete_id FKs
--      reference athlete_id and remain valid (a PK still satisfies them).
--
-- Preconditions (verified): all 10 athletes have athlete_id populated.
-- Run in the Supabase SQL editor. Idempotent-ish; see guards below.

do $$
declare
    pk_name text;
begin
    -- 1. Drop whatever primary key currently exists on athletes
    --    (expected: keyed on strava_athlete_id).
    select conname into pk_name
    from pg_constraint
    where conrelid = 'public.athletes'::regclass
      and contype = 'p';

    if pk_name is not null then
        execute format('alter table public.athletes drop constraint %I', pk_name);
    end if;

    -- 2. Drop the redundant unique constraint on athlete_id if present
    --    (migration 002 added athletes_athlete_id_key; the new PK replaces it).
    if exists (
        select 1 from pg_constraint
        where conrelid = 'public.athletes'::regclass
          and conname = 'athletes_athlete_id_key'
    ) then
        alter table public.athletes drop constraint athletes_athlete_id_key;
    end if;

    -- 3. Promote athlete_id to primary key (implies NOT NULL + unique).
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'public.athletes'::regclass
          and contype = 'p'
    ) then
        alter table public.athletes add primary key (athlete_id);
    end if;
end $$;

-- strava_athlete_id is now a plain nullable column; non-Strava athletes leave
-- it NULL. It is retained (not dropped) until the legacy cleanup migration.
