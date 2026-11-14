-- Migration 007: stop storing profile_picture, country, city on athletes
--
-- Why
--   Data minimization (Strava API Policy, and good practice generally): the app
--   only needs name, sex and activity totals for the ranking. Profile picture,
--   country and city are not used by any view, endpoint or report.
--
-- Safety
--   - Dashboard views (dashboard_athletes / dashboard_activities) select only
--     firstname, lastname, sex -> unaffected.
--   - Application code no longer writes or reads these columns (deploy that
--     change BEFORE running this migration).
--   - The drop removes the stored values permanently from the live table.
--     Earlier S3 backups still contain them until those backups age out.
--
-- Run in the Supabase SQL editor, AFTER the code deploy.

alter table public.athletes drop column if exists profile_picture;
alter table public.athletes drop column if exists country;
alter table public.athletes drop column if exists city;
