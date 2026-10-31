-- Migration 005: point reporting views at the canonical athlete_id, then drop
-- the legacy Strava-shaped columns from athletes.
--
-- Why
--   dashboard_activities and dashboard_athletes JOIN on strava_athlete_id, so
--   Garmin/COROS activities (strava_athlete_id = NULL) never appear in the
--   ranking. The canonical athlete_id now links activities -> athletes for ALL
--   providers. Rewriting the views on athlete_id both fixes multi-provider
--   reporting AND removes the last dependency on strava_athlete_id, allowing
--   the legacy columns to be dropped.
--
-- What
--   1. Recreate both views keyed on athlete_id.
--   2. Drop now-redundant legacy columns from athletes:
--        strava_athlete_id, access_token, refresh_token, expires_at
--      (tokens live in athlete_providers; the per-provider external id is
--       athlete_providers.provider_user_id; canonical id is athlete_id).
--
-- Run in the Supabase SQL editor. The CREATE OR REPLACE for a view fails if the
-- output columns change incompatibly, so we DROP then CREATE.

-- 1. dashboard_activities -------------------------------------------------
drop view if exists public.dashboard_activities;
create view public.dashboard_activities as
  select
    a.activity_id,
    a.athlete_id,
    a.source,
    a.activity_date,
    a.distance,
    a.moving_time,
    a.sport_type,
    a.activity_name,
    concat_ws(' ', ath.firstname, ath.lastname) as athlete_name,
    a.manual
  from public.activities a
  left join public.athletes ath on a.athlete_id = ath.athlete_id
  where a.activity_date >= (date_trunc('month', (now() at time zone 'Europe/Warsaw'))::date)
    and a.activity_date <  ((date_trunc('month', (now() at time zone 'Europe/Warsaw')) + interval '1 mon')::date);

-- Cycling sport-type keys across providers (observed in live data). REAL
-- OUTDOOR cycling only — virtual/indoor rides are deliberately EXCLUDED
-- (trainer "distance" is simulated and should not count toward the ranking):
--   Strava: Ride, GravelRide, MountainBikeRide   (NOT VirtualRide)
--   Garmin: road_biking, cycling, gravel_cycling, mountain_biking
--           (NOT indoor_cycling / virtual_ride)
--   COROS : Ride
-- PROPER FOLLOW-UP: normalize sport_type at ingestion (strava/coros/garmin.py)
-- to a single canonical value so this list need not grow per provider.

-- 2. dashboard_athletes ---------------------------------------------------
drop view if exists public.dashboard_athletes;
create view public.dashboard_athletes as
  select
    concat_ws(' ', ath.firstname, ath.lastname) as athlete_name,
    count(a.activity_id) as activity_count,
    round(coalesce(sum(
      case when a.sport_type = any (array[
             'Ride','GravelRide','MountainBikeRide',
             'road_biking','cycling','gravel_cycling','mountain_biking'])
           then a.distance else 0 end) / 1000.0, 0), 1) as cycling_distance_km,
    round(coalesce((sum(
      case when a.sport_type = any (array[
             'Ride','GravelRide','MountainBikeRide',
             'road_biking','cycling','gravel_cycling','mountain_biking'])
           then a.moving_time else 0 end))::numeric / 3600.0, 0), 1) as cycling_hours,
    ath.sex
  from public.activities a
  left join public.athletes ath on a.athlete_id = ath.athlete_id
  where a.activity_date >= (date_trunc('month', (now() at time zone 'Europe/Warsaw'))::date)
    and a.activity_date <  ((date_trunc('month', (now() at time zone 'Europe/Warsaw')) + interval '1 mon')::date)
  group by a.athlete_id, ath.firstname, ath.lastname, ath.sex;

-- 3. Drop legacy columns from athletes now that nothing references them ----
alter table public.athletes drop column if exists strava_athlete_id;
alter table public.athletes drop column if exists access_token;
alter table public.athletes drop column if exists refresh_token;
alter table public.athletes drop column if exists expires_at;
