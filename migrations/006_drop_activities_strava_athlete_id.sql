-- Migration 006: drop the legacy strava_athlete_id column from activities
--
-- Why
--   activities now carries the canonical athlete_id (uuid) linking to athletes,
--   populated for all providers. The old strava_athlete_id column is redundant
--   (Strava-specific, null for Garmin/COROS/Wahoo) and no longer referenced by
--   any application code or by the dashboard views (migration 005 rewrote them
--   onto athlete_id).
--
-- Safety
--   Idempotent. The dashboard views no longer select strava_athlete_id, so this
--   does not break them. No app code reads activities.strava_athlete_id.
--
-- Run in the Supabase SQL editor.

alter table public.activities drop column if exists strava_athlete_id;
