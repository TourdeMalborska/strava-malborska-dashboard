-- Migration 004: allow non-Strava athletes (relax strava_athlete_id NOT NULL)
--
-- Why
--   The legacy model keyed every athlete on Strava, so athletes.strava_athlete_id
--   was NOT NULL. Under the provider-neutral model (model B), an athlete can
--   originate from COROS or Garmin and have NO Strava account, so a non-Strava
--   athlete legitimately has strava_athlete_id = NULL. The NOT NULL constraint
--   blocks creating such athletes (fails with code 23502).
--
-- What
--   Make strava_athlete_id NULLABLE. The column is NOT dropped (that remains
--   deferred to a later cleanup, pending the reporting-view review). This only
--   relaxes nullability, so it is safe regardless of what the reporting view
--   selects.
--
-- Safe + idempotent. Run in the Supabase SQL editor.

alter table public.athletes
    alter column strava_athlete_id drop not null;
