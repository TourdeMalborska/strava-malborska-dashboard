# strava.py
#
# Strava provider: HTTP calls to the Strava API plus normalization into the
# canonical activities shape. Database writes (tokens, activities) go through
# providers.py so the identity model stays provider-neutral.
import os
import time
import requests
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

import providers

# -------------------------
# Token refresh (Strava API)
# -------------------------
def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.getenv("STRAVA_CLIENT_ID"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_link_token(link: Dict[str, Any]) -> str:
    """
    Refresh the Strava access token for an athlete_providers row and persist the
    rotated tokens back onto that link. Returns a valid access_token.

    `link` is an athlete_providers row (provider='strava').
    """
    token_data = refresh_access_token(link["refresh_token"])
    expires_at_iso = providers.epoch_to_iso(token_data["expires_at"])

    try:
        providers.update_provider_tokens(
            link_id=link["id"],
            access_token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            expires_at_iso=expires_at_iso,
        )
    except Exception as e:
        # Don't abort the caller on a persist failure; surface in logs.
        print(f"[strava] token persist error for link {link.get('id')}: {e}")

    return token_data["access_token"]


# -------------------------
# Activity fetch
# -------------------------
def get_activities(access_token: str) -> List[Dict[str, Any]]:
    resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_activities_range(
    access_token: str, start_ts: datetime, end_ts: datetime
) -> List[Dict[str, Any]]:
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
            "page": page,
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


def get_yesterday_activities(access_token: str) -> List[Dict[str, Any]]:
    today_utc = datetime.now(timezone.utc).date()
    yesterday = today_utc - timedelta(days=1)
    start_ts = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_ts = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=timezone.utc)
    return get_activities_range(access_token, start_ts, end_ts)


# -------------------------
# Normalize + save
# -------------------------
def normalize_activity(activity: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw Strava activity into the canonical activities table shape."""
    return {
        "activity_id": activity["id"],
        "activity_date": activity.get("start_date", "")[:10],
        "distance": activity.get("distance"),
        "moving_time": activity.get("moving_time"),
        "sport_type": activity.get("sport_type"),
        "activity_name": activity.get("name"),
        "manual": activity.get("manual"),
        "raw": activity,
    }


def save_activities(activities: List[Dict[str, Any]], athlete_id: str) -> Dict[str, Any]:
    """
    Normalize raw Strava activities and persist them against the canonical
    athlete_id with source='strava'.
    """
    records = [normalize_activity(a) for a in activities]
    return providers.save_activities(records, source="strava", athlete_id=athlete_id)
