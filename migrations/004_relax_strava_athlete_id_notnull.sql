-- Migration 004: allow non-Strava athletes by removing the Strava-based PK
--
-- Why
--   athletes.strava_athlete_id is the PRIMARY KEY (legacy Strava-centric model).
--   A primary key is implicitly NOT NULL, so a model-B athlete originating from
--   COROS/Garmin (no Strava account) cannot be created.
--
-- What (minimal, dependency-safe)
--   Drop ONLY the primary key on strava_athlete_id. That makes the column
--   nullable so non-Strava athletes can exist.
--
--   We intentionally DO NOT touch athletes_athlete_id_key (the UNIQUE
--   constraint/index on athlete_id). It is depended on by foreign keys from
--   athlete_providers, activities, and oauth_states, and a UNIQUE constraint
--   satisfies those FKs just as well as a PRIMARY KEY would. So athlete_id
--   remains the de-facto canonical key via its unique index; we simply stop
--   forcing strava_athlete_id to be the table PK.
--
-- strava_athlete_id is retained (not dropped) until the deferred legacy cleanup.
-- Run in the Supabase SQL editor. Idempotent.

do $$
declare
    pk_name text;
begin
    select conname into pk_name
    from pg_constraint
    where conrelid = 'public.athletes'::regclass
      and contype = 'p';

    if pk_name is not null then
        execute format('alter table public.athletes drop constraint %I', pk_name);
    end if;
end $$;
