-- Migration 001: add provider provenance to activities
--
-- Purpose
--   Record which provider each activity was ingested from (strava, coros,
--   garmin, wahoo, ...). This enables:
--     1. Cross-provider dedup (same ride can arrive from both Strava and COROS).
--     2. Measuring per-source volume (e.g. the ">20 COROS users" threshold).
--     3. Debugging / data provenance.
--
-- Safety
--   Run in the Supabase SQL editor. Idempotent: safe to run more than once.
--   All existing activity data predates multi-provider support and is Strava,
--   so existing rows are backfilled to 'strava'.

-- 1. Add the column as nullable so the ALTER does not fail on existing rows.
alter table public.activities
    add column if not exists source text;

-- 2. Backfill existing rows. Everything currently stored came from Strava.
update public.activities
    set source = 'strava'
    where source is null;

-- 3. Default new inserts to 'strava' for backward compatibility with any
--    code path that does not set source explicitly yet.
alter table public.activities
    alter column source set default 'strava';

-- 4. Enforce that source is always present going forward.
alter table public.activities
    alter column source set not null;

-- 5. Constrain to the known provider set. Extend this list as providers are
--    added. Using a CHECK keeps the value clean without a separate lookup table
--    (appropriate for the current small, fixed provider set).
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'activities_source_check'
    ) then
        alter table public.activities
            add constraint activities_source_check
            check (source in ('strava', 'coros', 'garmin', 'wahoo'));
    end if;
end $$;

-- 6. Index for per-source queries (counts, threshold checks, filtering).
create index if not exists activities_source_idx
    on public.activities (source);
