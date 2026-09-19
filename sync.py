# sync.py

import time
from datetime import datetime, timezone, timedelta
from config import supabase
from strava import refresh_athlete_token, get_activities_range, save_activities

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _update_athlete_status(athlete_id, **fields):
    payload = fields.copy()
    payload.setdefault("updated_at", _now_iso())
    try:
        supabase.table("athletes").update(payload).eq("strava_athlete_id", athlete_id).execute()
    except Exception as e:
        print(f"[sync] supabase update error for athlete {athlete_id}: {e}")

def sync_activities_for_athlete(athlete, start_ts, end_ts):
    athlete_id = athlete.get("strava_athlete_id")
    try:
        access_token = refresh_athlete_token(athlete)
        activities = get_activities_range(access_token, start_ts, end_ts)
        save_activities(activities)
        _update_athlete_status(athlete_id, last_sync=_now_iso(), error_message=None, status="active")
        count = len(activities) if activities else 0
        print(f"[sync] athlete={athlete_id} synced {count} activities")
        return {"athlete_id": athlete_id, "count": count, "error": None}
    except Exception as e:
        err = str(e)
        print(f"[sync] ERROR athlete={athlete_id}: {err}")
        _update_athlete_status(athlete_id, error_message=err, status="error")
        return {"athlete_id": athlete_id, "count": 0, "error": err}

def sync_all_athletes(start_ts, end_ts, active_only=True):
    query = supabase.table("athletes").select("*")
    if active_only:
        query = query.eq("active", True)
    athletes = query.execute().data or []
    results = []
    for athlete in athletes:
        res = sync_activities_for_athlete(athlete, start_ts, end_ts)
        results.append(res)
        time.sleep(0.2)  # mała pauza, dostosuj jeśli trzeba
    return results

# convenience runners
def run_daily_sync():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    start_ts = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_ts = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=timezone.utc)
    return sync_all_athletes(start_ts, end_ts)

def run_rolling_sync(hours: int = 4):
    end_ts = datetime.now(timezone.utc)
    start_ts = end_ts - timedelta(hours=hours)
    return sync_all_athletes(start_ts, end_ts)
