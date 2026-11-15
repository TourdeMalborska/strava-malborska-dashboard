-- Migration 009: Strava data minimisation / 7-day retention with permanent totals
--
-- Goal (Strava API Policy 6.2 / 7.4 / 5.7)
--   * Keep Strava activity-level data for at most 7 days (7 calendar days
--     including today).
--   * Older Strava activities are folded into per-athlete MONTHLY TOTALS
--     (count, outdoor-cycling distance, outdoor-cycling moving time) and then
--     deleted, so the monthly ranking keeps working.
--   * Stop keeping Strava's raw payload (contains location data).
--
-- Contents
--   1. activities.raw becomes nullable and existing Strava raw payloads are wiped
--   2. athlete_monthly_totals (RLS on, service-role only, backed up)
--   3. is_outdoor_cycling(): single source of truth for the cycling sport list
--   4. rollup_old_activities(): atomic fold-then-delete, callable by service role
--   5. dashboard_athletes rebuilt as live activities + rolled-up totals
--      (same column names/types/order, so Looker Studio fields are unaffected)
--
-- NOT done here (deliberately): running the rollup. After this migration run, as
-- a separate step:   select public.rollup_old_activities('strava', 7);
--
-- Run in the Supabase SQL editor. Idempotent.

-- 1. raw payload -------------------------------------------------------------
alter table public.activities alter column raw drop not null;

-- Wipe stored Strava raw payloads (irreversible; earlier S3 backups still hold
-- them until those backups expire).
update public.activities set raw = null where source = 'strava' and raw is not null;

-- 2. totals table ---------------------------------------------------------------
create table if not exists public.athlete_monthly_totals (
    athlete_id            uuid    not null
                             references public.athletes (athlete_id) on delete cascade,
    source                text    not null
                             check (source in ('strava', 'coros', 'garmin', 'wahoo')),
    month                 date    not null,              -- first day of the month
    activity_count        integer not null default 0,    -- all sports
    cycling_distance_m    numeric not null default 0,    -- outdoor cycling only
    cycling_moving_time_s bigint  not null default 0,    -- outdoor cycling only
    updated_at            timestamptz not null default now(),
    primary key (athlete_id, source, month)
);

-- Same access model as athletes/activities: RLS on, no anon/authenticated access.
-- (Not FORCEd: the dashboard view runs as its owner and must be able to read it.)
alter table public.athlete_monthly_totals enable row level security;
revoke all on public.athlete_monthly_totals from anon, authenticated;

-- Backups run as malborska_backup with row security enforced, so it needs an
-- explicit grant + policy (scripts/backup_supabase.sh now expects this table).
grant select on public.athlete_monthly_totals to malborska_backup;
do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'athlete_monthly_totals'
          and policyname = 'malborska_backup_athlete_monthly_totals_select'
    ) then
        create policy malborska_backup_athlete_monthly_totals_select
            on public.athlete_monthly_totals
            for select to malborska_backup using (true);
    end if;
end $$;

-- 3. cycling sport list: one definition for the view and the rollup ------------
-- Real OUTDOOR cycling only; virtual/indoor rides are excluded on purpose.
--   Strava: Ride, GravelRide, MountainBikeRide     Garmin: road_biking, cycling,
--   gravel_cycling, mountain_biking                COROS: Ride
create or replace function public.is_outdoor_cycling(t text)
returns boolean
language sql
immutable
as $$
    select t = any (array[
        'Ride', 'GravelRide', 'MountainBikeRide',
        'road_biking', 'cycling', 'gravel_cycling', 'mountain_biking'
    ])
$$;

-- 4. atomic rollup -----------------------------------------------------------------
-- Keeps activities dated within the last p_keep_days calendar days INCLUDING
-- today (Europe/Warsaw). Everything older for p_source is added to the monthly
-- totals and deleted in ONE statement: the insert and the delete see the same
-- snapshot, so rows are counted exactly once and never lost on failure.
-- Re-running is safe (nothing old is left to count the second time).
create or replace function public.rollup_old_activities(p_source text, p_keep_days integer default 7)
returns table (activities_deleted integer, totals_rows_touched integer)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_cutoff date := ((now() at time zone 'Europe/Warsaw')::date - (p_keep_days - 1));
begin
    return query
    with stale as (
        select activity_id, athlete_id, activity_date, sport_type, distance, moving_time
        from public.activities
        where source = p_source
          and athlete_id is not null
          and activity_date < v_cutoff
    ),
    agg as (
        select athlete_id,
               date_trunc('month', activity_date)::date as month,
               count(*)::integer as activity_count,
               coalesce(sum(case when public.is_outdoor_cycling(sport_type)
                                 then distance else 0 end), 0)::numeric as dist_m,
               coalesce(sum(case when public.is_outdoor_cycling(sport_type)
                                 then moving_time else 0 end), 0)::bigint as secs
        from stale
        group by athlete_id, date_trunc('month', activity_date)
    ),
    ins as (
        insert into public.athlete_monthly_totals as t
            (athlete_id, source, month, activity_count, cycling_distance_m, cycling_moving_time_s)
        select athlete_id, p_source, month, activity_count, dist_m, secs from agg
        on conflict (athlete_id, source, month) do update set
            activity_count        = t.activity_count        + excluded.activity_count,
            cycling_distance_m    = t.cycling_distance_m    + excluded.cycling_distance_m,
            cycling_moving_time_s = t.cycling_moving_time_s + excluded.cycling_moving_time_s,
            updated_at            = now()
        returning 1
    ),
    del as (
        delete from public.activities a
        using stale s
        where a.activity_id = s.activity_id and a.source = p_source
        returning 1
    )
    select (select count(*) from del)::integer,
           (select count(*) from ins)::integer;
end;
$$;

-- Only the service role (the app) may call it; it must NOT be callable from the
-- public API with the anon key.
revoke all on function public.rollup_old_activities(text, integer) from public, anon, authenticated;
grant execute on function public.rollup_old_activities(text, integer) to service_role;

-- 5. dashboard_athletes = live activities (this month) + rolled-up totals -----------
-- Column names, order and types are unchanged from migration 005, so
-- CREATE OR REPLACE keeps the existing grants and Looker Studio keeps working.
create or replace view public.dashboard_athletes as
with bounds as (
    select (date_trunc('month', (now() at time zone 'Europe/Warsaw')))::date as m_start
),
live as (
    select a.athlete_id,
           count(*)::numeric as activity_count,
           coalesce(sum(case when public.is_outdoor_cycling(a.sport_type)
                             then a.distance else 0 end), 0)::numeric as dist_m,
           coalesce(sum(case when public.is_outdoor_cycling(a.sport_type)
                             then a.moving_time else 0 end), 0)::numeric as secs
    from public.activities a, bounds b
    where a.activity_date >= b.m_start
      and a.activity_date <  (b.m_start + interval '1 month')::date
    group by a.athlete_id
),
rolled as (
    select t.athlete_id,
           sum(t.activity_count)::numeric        as activity_count,
           sum(t.cycling_distance_m)::numeric    as dist_m,
           sum(t.cycling_moving_time_s)::numeric as secs
    from public.athlete_monthly_totals t, bounds b
    where t.month = b.m_start
    group by t.athlete_id
),
combined as (
    select * from live
    union all
    select * from rolled
)
select concat_ws(' ', ath.firstname, ath.lastname) as athlete_name,
       coalesce(sum(c.activity_count), 0)::bigint as activity_count,
       round(coalesce(sum(c.dist_m) / 1000.0, 0), 1) as cycling_distance_km,
       round(coalesce(sum(c.secs) / 3600.0, 0), 1)   as cycling_hours,
       ath.sex
from combined c
left join public.athletes ath on ath.athlete_id = c.athlete_id
group by c.athlete_id, ath.firstname, ath.lastname, ath.sex;

-- Re-assert view access (idempotent; protects against the grant loss that
-- followed the drop/recreate in migration 005).
grant usage on schema public to dashboard_reader;
grant select on public.dashboard_activities to dashboard_reader;
grant select on public.dashboard_athletes   to dashboard_reader;
revoke all on public.dashboard_activities from anon, authenticated;
revoke all on public.dashboard_athletes   from anon, authenticated;
