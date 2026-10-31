"""
Garmin provider for Tour de Malborska.

TWO Garmin integration paths exist (see docs/multi-provider.md):

  * Personal API (THIS module): a single-person API keyed by a Personal API
    key created on one Garmin Connect account. It can ONLY read THAT account's
    data. Used here as a single-athlete pilot to validate the data shape and
    the source='garmin' path. No per-user OAuth, no approval.
  * Connect Developer Program / Activity API (future): per-user OAuth with
    end-user consent, for onboarding many club athletes. Requires applying for
    and being granted Developer Program access. That is the correct long-term
    multi-athlete path; it is NOT implemented here.

Verified against the live Personal API:
  token : POST {HOST}/personalapitoken-service/personal-api/personal-api-key/token
          header Authorization: ApiKey <key>  ->  body is the bearer JWT as
          PLAIN TEXT (not JSON).
  data  : GET {HOST}/activitylist-service/activities/search/activities
          header Authorization: Bearer <token>  ->  JSON list of activities.
  HOST  : https://personal.connectapi.garmin.com  (same host for token + data;
          apis.garmin.com does NOT serve the personal endpoints).

Activity JSON (real fields used):
  activityId (int), distance (metres, float), duration/movingDuration (seconds),
  startTimeGMT ('YYYY-MM-DD HH:MM:SS'), activityType.typeKey (e.g. 'running'),
  isManualActivity (bool), activityName.
"""

import os
import time
import requests
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

import providers

GARMIN_HOST = os.getenv("GARMIN_HOST", "https://personal.connectapi.garmin.com")
GARMIN_TOKEN_ENDPOINT = (
    f"{GARMIN_HOST}/personalapitoken-service/personal-api/personal-api-key/token"
)
GARMIN_ACTIVITIES_ENDPOINT = (
    f"{GARMIN_HOST}/activitylist-service/activities/search/activities"
)

# The Personal API key is stored in Infisical (prod/app) as GARMIN_API_KEY.
GARMIN_API_KEY_ENV = "GARMIN_API_KEY"

# Stable synthetic account id for the Personal API. The Personal API is
# single-account (one key = one Garmin account), and the activity list does not
# carry an owner id, so we key the provider link by this constant. If multiple
# Personal API keys were ever used they would each need a distinct id; for the
# single-athlete pilot one constant is correct.
GARMIN_PERSONAL_USER_ID = "garmin_personal_self"


# -------------------------
# Auth: API key -> bearer token
# -------------------------
def obtain_token(api_key: str = None) -> str:
    """
    Exchange the Personal API key for a bearer token. The token endpoint
    returns the JWT as PLAIN TEXT (not JSON). Returns the token string.
    """
    key = api_key or os.getenv(GARMIN_API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{GARMIN_API_KEY_ENV} is not configured")

    resp = requests.post(
        GARMIN_TOKEN_ENDPOINT,
        headers={"Authorization": f"ApiKey {key}"},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.text.strip()
    if not token or token.count(".") < 2:
        raise RuntimeError("Garmin token endpoint did not return a JWT")
    return token


# -------------------------
# Activity fetch
# -------------------------
def search_activities(access_token: str, start: int = 0, limit: int = 20,
                      start_date: str = None, end_date: str = None
                      ) -> List[Dict[str, Any]]:
    """
    Fetch activities (newest first). Dates are 'YYYY-MM-DD' strings (optional).
    Returns the raw JSON list.
    """
    params = {"start": start, "limit": limit}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    resp = None
    for attempt in range(4):
        try:
            resp = requests.get(
                GARMIN_ACTIVITIES_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=30,
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                print(f"[garmin] rate limited, sleeping {retry_after}s")
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            backoff = 2 ** attempt
            print(f"[garmin] request error (attempt {attempt}) {e}, backoff {backoff}s")
            time.sleep(backoff)
    if resp is None:
        raise RuntimeError("Failed to fetch activities from Garmin after retries")

    data = resp.json()
    return data if isinstance(data, list) else []


def get_activities_range(access_token: str, start_dt: datetime,
                         end_dt: datetime) -> List[Dict[str, Any]]:
    """Fetch activities within a datetime range (uses YYYY-MM-DD date filters)."""
    return search_activities(
        access_token,
        start=0,
        limit=50,
        start_date=start_dt.strftime("%Y-%m-%d"),
        end_date=end_dt.strftime("%Y-%m-%d"),
    )


# -------------------------
# Normalize + save
# -------------------------
def normalize_activity(a: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw Garmin activity into the canonical activities table shape."""
    sport = None
    at = a.get("activityType")
    if isinstance(at, dict):
        sport = at.get("typeKey")

    # Date from startTimeGMT 'YYYY-MM-DD HH:MM:SS'.
    start_gmt = a.get("startTimeGMT") or ""
    activity_date = start_gmt[:10] if start_gmt else None

    duration = a.get("movingDuration") or a.get("duration")

    return {
        "activity_id": a["activityId"],
        "activity_date": activity_date,
        "distance": a.get("distance"),          # metres, like Strava
        "moving_time": int(duration) if duration is not None else None,
        "sport_type": sport,
        "activity_name": a.get("activityName"),
        "manual": bool(a.get("isManualActivity")),
        "raw": a,
    }


def save_activities(activities: List[Dict[str, Any]], athlete_id: str) -> Dict[str, Any]:
    """Normalize raw Garmin activities and persist with source='garmin'."""
    records = [normalize_activity(a) for a in activities]
    return providers.save_activities(records, source="garmin", athlete_id=athlete_id)


# -------------------------
# Personal API link bootstrap (pilot)
# -------------------------
def ensure_personal_link() -> Dict[str, Any]:
    """
    Ensure an athlete_providers row exists for the single Personal-API Garmin
    account, creating a canonical athlete on first run. Returns the link row.

    The Personal API uses a long-lived key (not per-call tokens), so we store
    the derived bearer token's identity marker on a provider link keyed by the
    constant GARMIN_PERSONAL_USER_ID. The API key itself stays in Infisical, not
    the DB.
    """
    existing = providers.find_provider_link("garmin", GARMIN_PERSONAL_USER_ID)
    if existing:
        return existing

    # First run: create a canonical athlete for the Personal API owner.
    athlete_id = providers.create_athlete({
        "firstname": "Garmin",
        "lastname": "(Personal API)",
    })
    return providers.link_provider(
        athlete_id=athlete_id,
        provider="garmin",
        provider_user_id=GARMIN_PERSONAL_USER_ID,
        access_token=None,      # token is derived on demand from the API key
        refresh_token=None,
        expires_at_iso=None,
        scope="personal-api",
    )
