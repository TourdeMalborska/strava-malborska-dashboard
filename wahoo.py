"""
Wahoo Cloud API provider for Tour de Malborska.

Standard OAuth 2.0 authorization-code flow (CONFIDENTIAL client — uses a client
secret, no PKCE). Per-user, like Strava: each athlete authorizes once, tokens
are stored in athlete_providers (provider='wahoo'), and the hourly sync polls
their workouts.

Docs: https://cloud-api.wahooligan.com/
  authorize : https://api.wahooligan.com/oauth/authorize
  token     : https://api.wahooligan.com/oauth/token
  user      : GET /v1/user                         (identity/profile)
  workouts  : GET /v1/workouts                      (list, paginated)
  summary   : GET /v1/workouts/{id}/workout_summary (distance/duration metrics)

Scopes: user_read workouts_read.

NOTE: this is a SANDBOX app (limited throughput, test data only). Sandbox and
production share the same host; environment is a property of the credentials,
not the URL. A sandbox app cannot be converted to production — a separate
production app will be needed for real athlete data.

Data is clean JSON (no prose parsing). In workout_summary, distance is
`distance_accum` (metres) and active duration is `duration_active_accum` (secs).
"""

import os
import urllib.parse
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

import providers

WAHOO_HOST = os.getenv("WAHOO_HOST", "https://api.wahooligan.com")
WAHOO_AUTHORIZE_ENDPOINT = f"{WAHOO_HOST}/oauth/authorize"
WAHOO_TOKEN_ENDPOINT = f"{WAHOO_HOST}/oauth/token"
WAHOO_USER_ENDPOINT = f"{WAHOO_HOST}/v1/user"
WAHOO_WORKOUTS_ENDPOINT = f"{WAHOO_HOST}/v1/workouts"

WAHOO_SCOPES = "user_read workouts_read"

WAHOO_CLIENT_ID = os.getenv("WAHOO_CLIENT_ID")
WAHOO_CLIENT_SECRET = os.getenv("WAHOO_CLIENT_SECRET")
WAHOO_REDIRECT_URI = os.getenv(
    "WAHOO_REDIRECT_URI",
    "https://tourdemalborska.vercel.app/auth/wahoo/callback",
)

# Wahoo workout_type_id values treated as OUTDOOR cycling. Refine against the
# live workout-type reference; indoor/virtual rides are excluded (simulated
# distance must not count toward the ranking).
WAHOO_CYCLING_TYPE_IDS = {0, 40}


# -------------------------
# OAuth (confidential client)
# -------------------------
def build_authorize_url(state: str) -> str:
    params = {
        "client_id": WAHOO_CLIENT_ID,
        "redirect_uri": WAHOO_REDIRECT_URI,
        "response_type": "code",
        "scope": WAHOO_SCOPES,
        "state": state,
    }
    return f"{WAHOO_AUTHORIZE_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str) -> Dict[str, Any]:
    resp = requests.post(
        WAHOO_TOKEN_ENDPOINT,
        data={
            "client_id": WAHOO_CLIENT_ID,
            "client_secret": WAHOO_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": WAHOO_REDIRECT_URI,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Wahoo token exchange failed: HTTP {resp.status_code} — {resp.text[:400]}")
    return resp.json()


def refresh_token(refresh_token_value: str) -> Dict[str, Any]:
    resp = requests.post(
        WAHOO_TOKEN_ENDPOINT,
        data={
            "client_id": WAHOO_CLIENT_ID,
            "client_secret": WAHOO_CLIENT_SECRET,
            "refresh_token": refresh_token_value,
            "grant_type": "refresh_token",
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Wahoo token refresh failed: HTTP {resp.status_code} — {resp.text[:400]}")
    return resp.json()


def refresh_link_token(link: Dict[str, Any]) -> str:
    token_data = refresh_token(link["refresh_token"])
    expires_at_iso = None
    if token_data.get("expires_in"):
        expires_at_iso = (
            datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))
        ).isoformat()
    try:
        providers.update_provider_tokens(
            link_id=link["id"],
            access_token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            expires_at_iso=expires_at_iso,
        )
    except Exception as e:
        print(f"[wahoo] token persist error for link {link.get('id')}: {e}")
    return token_data["access_token"]


# -------------------------
# Identity + profile
# -------------------------
def get_user(access_token: str) -> Dict[str, Any]:
    resp = requests.get(
        WAHOO_USER_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def resolve_user_id(access_token: str) -> str:
    user = get_user(access_token)
    uid = user.get("id")
    if uid is None:
        raise RuntimeError("Wahoo /v1/user returned no id")
    return str(uid)


def fetch_profile(access_token: str) -> Dict[str, Any]:
    try:
        user = get_user(access_token)
        return {
            "firstname": user.get("first"),
            "lastname": user.get("last"),
            "email": user.get("email"),
        }
    except Exception as e:
        print(f"[wahoo] profile fetch failed, minimal athlete: {e}")
        return {"firstname": None, "lastname": None, "email": None}


# -------------------------
# Workouts
# -------------------------
def get_workouts(access_token: str, page: int = 1, per_page: int = 50) -> List[Dict[str, Any]]:
    resp = requests.get(
        WAHOO_WORKOUTS_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"page": page, "per_page": per_page},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        return data.get("workouts", []) or []
    return data if isinstance(data, list) else []


def get_workout_summary(access_token: str, workout_id) -> Optional[Dict[str, Any]]:
    resp = requests.get(
        f"{WAHOO_WORKOUTS_ENDPOINT}/{workout_id}/workout_summary",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def get_activities_range(access_token: str, start_dt: datetime,
                         end_dt: datetime) -> List[Dict[str, Any]]:
    """
    Fetch workouts starting in [start_dt, end_dt] and return normalized activity
    records.

    The workout_summary (distance etc.) is read from the INLINE `workout_summary`
    field on each workout object. We do NOT call the separate
    /v1/workouts/{id}/workout_summary endpoint: it returns 401 for workouts that
    originated in third-party apps (Wahoo policy), which would abort the sync.
    Inline summary is null for those workouts -> distance comes back None, which
    is handled gracefully (the activity is still recorded, just without km).
    """
    records: List[Dict[str, Any]] = []
    page = 1
    while True:
        workouts = get_workouts(access_token, page=page, per_page=50)
        if not workouts:
            break
        stop = False
        for w in workouts:
            starts = _parse_ts(w.get("starts"))
            if starts is None:
                continue
            if starts < start_dt:
                stop = True       # newest-first: older than window -> done
                break
            if starts > end_dt:
                continue
            summary = w.get("workout_summary") or {}
            records.append(normalize_activity(w, summary))
        if stop or len(workouts) < 50:
            break
        page += 1
    return records


def normalize_activity(workout: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    starts = workout.get("starts") or ""
    activity_date = starts[:10] if starts else None

    distance = summary.get("distance_accum")
    distance = float(distance) if distance is not None else None

    duration = summary.get("duration_active_accum") or summary.get("duration_total_accum")
    moving_time = int(float(duration)) if duration is not None else None

    return {
        "activity_id": workout["id"],
        "activity_date": activity_date,
        "distance": distance,            # metres
        "moving_time": moving_time,      # seconds
        "sport_type": str(workout.get("workout_type_id")),
        "activity_name": workout.get("name"),
        "manual": bool(workout.get("manual")),
        "raw": {"workout": workout, "summary": summary},
    }


def save_activities(activities: List[Dict[str, Any]], athlete_id: str) -> Dict[str, Any]:
    return providers.save_activities(activities, source="wahoo", athlete_id=athlete_id)
