"""
Hammerhead (SRAM) Karoo provider for Tour de Malborska.

Standard OAuth 2.0 authorization-code flow, confidential client (client secret).
Per-user, like Strava/Wahoo: each athlete authorizes once, tokens are stored in
athlete_providers (provider='hammerhead'), and the hourly sync polls their rides.

Source of truth: OpenAPI spec at https://api.hammerhead.io/v1/docs/openapi.yml
  authorize : https://api.hammerhead.io/v1/auth/oauth/authorize
  token     : https://api.hammerhead.io/v1/auth/oauth/token   (returns user_id)
  list      : GET https://api.hammerhead.io/v1/api/activities
              ?page=&perPage=(max 100)&startDate=YYYY-MM-DD
              -> {data: [ActivitySummary], totalPages, currentPage, ...}
  detail    : GET https://api.hammerhead.io/v1/api/activities/{activityId}
              adds activityType, description, polyline
  scope     : activity:read

There is NO profile endpoint: we get a stable user id from the token response
but no name. New Hammerhead athletes get a placeholder name.

UNVERIFIED (spec examples are ambiguous - confirm against a real ride):
  * distance unit  -> assumed METRES  (route examples are clearly metres)
  * duration unit  -> assumed MILLISECONDS (example 76765 with 123.45 m only
    gives a plausible speed if duration is ms)
  * activity date  -> taken from createdAt; this may be the UPLOAD time, not the
    ride start (the API exposes no start time)
"""

import os
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import requests

import providers

HAMMERHEAD_AUTH_BASE = "https://api.hammerhead.io/v1/auth"
HAMMERHEAD_API_BASE = "https://api.hammerhead.io/v1/api"
HAMMERHEAD_AUTHORIZE_ENDPOINT = f"{HAMMERHEAD_AUTH_BASE}/oauth/authorize"
HAMMERHEAD_TOKEN_ENDPOINT = f"{HAMMERHEAD_AUTH_BASE}/oauth/token"
HAMMERHEAD_ACTIVITIES_ENDPOINT = f"{HAMMERHEAD_API_BASE}/activities"

HAMMERHEAD_SCOPES = "activity:read"

HAMMERHEAD_CLIENT_ID = os.getenv("HAMMERHEAD_CLIENT_ID")
HAMMERHEAD_CLIENT_SECRET = os.getenv("HAMMERHEAD_CLIENT_SECRET")
HAMMERHEAD_REDIRECT_URI = os.getenv(
    "HAMMERHEAD_REDIRECT_URI",
    "https://tourdemalborska.vercel.app/auth/hammerhead/callback",
)

# Unit conversion to our canonical units (metres, seconds). UNVERIFIED - see
# module docstring. Change these two constants if a real ride shows otherwise.
DISTANCE_TO_METRES = 1.0          # API distance assumed to be metres
DURATION_TO_SECONDS = 1 / 1000.0  # API duration assumed to be milliseconds

# Hammerhead activityType -> our sport_type. The first three are counted as
# outdoor cycling by public.is_outdoor_cycling(); e-bikes and velomobiles are
# stored under their own names and NOT counted (product decision - change the
# mapping or the SQL list to count them).
SPORT_TYPE_MAP = {
    "RIDE": "Ride",
    "GRAVEL": "GravelRide",
    "MOUNTAIN_BIKE": "MountainBikeRide",
    "EBIKE": "EBikeRide",
    "EMOUNTAIN_BIKE": "EMountainBikeRide",
    "VELOMOBILE": "Velomobile",
}

PER_PAGE = 100
MAX_PAGES = 20  # safety stop for a single sync window


# -------------------------
# IDs
# -------------------------
def to_activity_id(hammerhead_id: str) -> int:
    """
    activities.activity_id is BIGINT, but Hammerhead ids are strings like
    "1000.activity.abcd". Map them to a stable positive 63-bit integer
    (SHA-256, deterministic), so upserts stay idempotent. The original string
    id is kept in raw['hammerhead_id'].
    """
    digest = hashlib.sha256(f"hammerhead:{hammerhead_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> 1


# -------------------------
# OAuth (confidential client)
# -------------------------
def build_authorize_url(state: str) -> str:
    params = {
        "client_id": HAMMERHEAD_CLIENT_ID,
        "redirect_uri": HAMMERHEAD_REDIRECT_URI,
        "response_type": "code",
        "scope": HAMMERHEAD_SCOPES,
        "state": state,
    }
    return f"{HAMMERHEAD_AUTHORIZE_ENDPOINT}?{urllib.parse.urlencode(params)}"


def _token_request(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "client_id": HAMMERHEAD_CLIENT_ID,
        "client_secret": HAMMERHEAD_CLIENT_SECRET,
        **data,
    }
    resp = requests.post(
        HAMMERHEAD_TOKEN_ENDPOINT,
        data=payload,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Hammerhead token request failed: HTTP {resp.status_code} - {resp.text[:400]}"
        )
    return resp.json()


def exchange_code(code: str) -> Dict[str, Any]:
    """Authorization code -> {access_token, refresh_token, expires_in, user_id}."""
    return _token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": HAMMERHEAD_REDIRECT_URI,
    })


def refresh_token(refresh_token_value: str) -> Dict[str, Any]:
    return _token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_value,
    })


def expires_at_from(token_data: Dict[str, Any]) -> Optional[str]:
    if token_data.get("expires_in"):
        return (
            datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))
        ).isoformat()
    return None


def refresh_link_token(link: Dict[str, Any]) -> str:
    """Refresh the access token for an athlete_providers row and persist it."""
    token_data = refresh_token(link["refresh_token"])
    try:
        providers.update_provider_tokens(
            link_id=link["id"],
            access_token=token_data.get("access_token"),
            # Keep the old refresh token if the server does not rotate it.
            refresh_token=token_data.get("refresh_token") or link["refresh_token"],
            expires_at_iso=expires_at_from(token_data),
        )
    except Exception as e:
        print(f"[hammerhead] token persist error for link {link.get('id')}: {e}")
    return token_data["access_token"]


def resolve_user_id(token_data: Dict[str, Any]) -> str:
    uid = token_data.get("user_id")
    if uid is None or str(uid).strip() == "":
        raise RuntimeError("Hammerhead token response has no user_id")
    return str(uid)


def placeholder_profile() -> Dict[str, Any]:
    """Hammerhead exposes no profile/name endpoint."""
    return {"firstname": "Hammerhead", "lastname": "(Karoo)"}


# -------------------------
# Activities
# -------------------------
def _get(access_token: str, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_activity_page(access_token: str, page: int, start_date: str) -> Dict[str, Any]:
    return _get(access_token, HAMMERHEAD_ACTIVITIES_ENDPOINT, {
        "page": page, "perPage": PER_PAGE, "startDate": start_date,
    })


def get_activity_detail(access_token: str, hammerhead_id: str) -> Dict[str, Any]:
    quoted = urllib.parse.quote(str(hammerhead_id), safe="")
    return _get(access_token, f"{HAMMERHEAD_ACTIVITIES_ENDPOINT}/{quoted}")


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
    Fetch activities created in [start_dt, end_dt] and return normalized
    records. The list endpoint gives no sport type, so each matching activity
    is fetched once more for activityType (polyline in that response is
    discarded, never stored).
    """
    records: List[Dict[str, Any]] = []
    start_date = start_dt.strftime("%Y-%m-%d")
    page = 1
    while page <= MAX_PAGES:
        body = get_activity_page(access_token, page, start_date) or {}
        items = body.get("data") or []
        for summary in items:
            created = _parse_ts(summary.get("createdAt"))
            if created is None or created < start_dt or created > end_dt:
                continue
            try:
                detail = get_activity_detail(access_token, summary["id"]) or {}
            except Exception as e:
                print(f"[hammerhead] detail fetch failed for {summary.get('id')}: {e}")
                detail = {}
            records.append(normalize_activity({**summary, **detail}))
        total_pages = int(body.get("totalPages") or 1)
        if page >= total_pages or not items:
            break
        page += 1
    return records


def normalize_activity(a: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Hammerhead activity (summary + detail) to the activities shape."""
    hh_id = str(a["id"])
    created = a.get("createdAt") or ""

    distance = a.get("distance")
    distance_m = float(distance) * DISTANCE_TO_METRES if distance is not None else None

    duration = a.get("duration")
    moving_time = int(round(float(duration) * DURATION_TO_SECONDS)) if duration is not None else None

    activity_type = a.get("activityType")
    return {
        "activity_id": to_activity_id(hh_id),
        "activity_date": created[:10] if created else None,
        "distance": distance_m,
        "moving_time": moving_time,
        "sport_type": SPORT_TYPE_MAP.get(activity_type, activity_type),
        "activity_name": a.get("name"),
        "manual": None,  # the API exposes no manual flag
        # Minimal raw: original id + type only. NO polyline, NO description.
        "raw": {"provider": "hammerhead", "hammerhead_id": hh_id,
                "activityType": activity_type},
    }


def save_activities(records: List[Dict[str, Any]], athlete_id: str) -> Dict[str, Any]:
    return providers.save_activities(records, source="hammerhead", athlete_id=athlete_id)
