-- Migration 008: restore reporting access to the dashboard views and close
-- public access to them.
--
-- What went wrong
--   1. Migration 005 dropped and recreated dashboard_activities and
--      dashboard_athletes. Dropping a view discards its grants, so the
--      reporting role used by Looker Studio (dashboard_reader) lost SELECT and
--      the dashboard stopped reading data.
--   2. The recreated views received Supabase's default grants: ALL privileges to
--      anon, authenticated and service_role. The views are owned by postgres and
--      therefore bypass the RLS on athletes/activities, so anon and
--      authenticated could read member names and ride data through the Supabase
--      API. Only the reporting role should be able to read them.
--
-- Fix
--   - grant SELECT on both views to dashboard_reader
--   - revoke everything on both views from anon and authenticated
--     (the app uses the service role; Looker uses dashboard_reader)
--
-- IMPORTANT: re-run these grants any time either view is dropped and recreated.
--
-- Run in the Supabase SQL editor. Idempotent.

grant usage on schema public to dashboard_reader;

grant select on public.dashboard_activities to dashboard_reader;
grant select on public.dashboard_athletes   to dashboard_reader;

revoke all on public.dashboard_activities from anon, authenticated;
revoke all on public.dashboard_athletes   from anon, authenticated;
