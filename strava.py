# strava.py
import os
import time
import requests
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

from config import supabase

# -------------------------
# Helpers
# -------------------------
def _to_iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# -------------------------
# Token refresh
# -------------------------
def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.getenv("STRAVA_CLIENT_ID"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        },
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()

def refresh_athlete_token(athlete: Dict[str, Any]) -> str:
    """
    Odświeża token i zapisuje access_token, refresh_token, expires_at, updated_at.
    Zwraca access_token.
    """
    token_data = refresh_access_token(athlete["refresh_token"])
    expires_at_iso = _to_iso_utc(token_data["expires_at"])

    try:
        supabase.table("athletes").update({
            "refresh_token": token_data.get("refresh_token"),
            "access_token": token_data.get("access_token"),
            "expires_at": expires_at_iso,
            "updated_at": _now_iso(),
            "error_message": None
        }).eq("strava_athlete_id", athlete["strava_athlete_id"]).execute()
    except Exception as e:
        # Nie przerywamy, ale logujemy — caller powinien obsłużyć wyjątek jeśli potrzebne
        print(f"[strava] supabase update error in refresh_athlete_token: {e}")

    return token_data["access_token"]

# -------------------------
# Simple non-range fetch (backwards compatibility)
# -------------------------
def get_activities(access_token: str) -> List[Dict[str, Any]]:
    resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()

# -------------------------
# Range fetch with pagination and retry
# -------------------------
def get_activities_range(access_token: str, start_ts: datetime, end_ts: datetime) -> List[Dict[str, Any]]:
    url = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}
    per_page = 200
    page = 1
    results: List[Dict[str, Any]] = []

    while True:
        params = {
            "after": int(start_ts.timestamp()),
            "before": int(end_ts.timestamp()),
            "per_page": per_page,
            "page": page
        }

        resp = None
        for attempt in range(4):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    print(f"[strava] rate limited, sleeping {retry_after}s")
                    time.sleep(retry_after)
                    continue
                resp.raise_for_status()
                break
            except requests.RequestException as e:
                backoff = 2 ** attempt
                print(f"[strava] request error (attempt {attempt}) {e}, backoff {backoff}s")
                time.sleep(backoff)
        if resp is None:
            raise RuntimeError("Failed to fetch activities from Strava after retries")

        data = resp.json()
        if not data:
            break
        results.extend(data)
        if len(data) < per_page:
            break
        page += 1

    return results

# -------------------------
# Save activities (upsert by activity_id)
# -------------------------
def save_activities(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not activities:
        return {"status": "no_activities", "inserted": 0}

    records = []
    for activity in activities:
        records.append({
            "activity_id": activity["id"],
            "strava_athlete_id": activity.get("athlete", {}).get("id"),
            "activity_date": activity.get("start_date", "")[:10],
            "distance": activity.get("distance"),
            "moving_time": activity.get("moving_time"),
            "sport_type": activity.get("sport_type"),
            "activity_name": activity.get("name"),
            "manual": activity.get("manual"),
            # Provenance: which provider this activity was ingested from.
            # Enables cross-provider dedup and measuring per-source volume.
            "source": "strava",
            "raw": activity
        })

    # Supabase upsert requires unique constraint on activity_id
    result = supabase.table("activities").upsert(records).execute()
    return {"status": "ok", "data": result.data}

# -------------------------
# Yesterday helper using range fetch
# -------------------------
def get_yesterday_activities(access_token: str) -> List[Dict[str, Any]]:
    today_utc = datetime.now(timezone.utc).date()
    yesterday = today_utc - timedelta(days=1)
    start_ts = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_ts = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=timezone.utc)
    return get_activities_range(access_token, start_ts, end_ts)
