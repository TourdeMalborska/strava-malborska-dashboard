-- Migration 003: record each athlete's origin provider on the athletes row
--
-- Goal
--   Capture, on the canonical athletes row, WHICH provider that athlete first
--   entered the system through (strava / coros / garmin / wahoo). This is the
--   athlete's origin/source, distinct from:
--     - activities.source       (provider per activity)
--     - athlete_providers.provider (each linked provider account)
--   It answers "where did this person come from" at a glance.
--
-- Safety
--   Additive and idempotent. Run in the Supabase SQL editor. Backfills existing
--   athletes to 'strava' (all pre-dated multi-provider onboarding and came in
--   via the Strava OAuth flow).
--
-- NOTE: This is NOT the legacy-column cleanup migration. Dropping
--   strava_athlete_id / inline tokens remains deferred until the reporting view
--   is confirmed not to reference them (see docs/multi-provider.md).

alter table public.athletes
    add column if not exists source text;

-- Backfill: every existing athlete onboarded via Strava.
update public.athletes
    set source = 'strava'
    where source is null;

-- Constrain to the known provider set (mirrors activities.source).
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'athletes_source_check'
    ) then
        alter table public.athletes
            add constraint athletes_source_check
            check (source in ('strava', 'coros', 'garmin', 'wahoo'));
    end if;
end $$;

create index if not exists athletes_source_idx
    on public.athletes (source);
