"""
Provider-neutral data-access layer for Tour de Malborska.

Identity model (see migrations/002_canonical_athlete_providers.sql and
docs/multi-provider.md):

  athletes            canonical person, keyed by athlete_id (uuid, app-owned).
  athlete_providers   one row per (athlete x provider): provider_user_id,
                      tokens, scope, status, last_sync.
  oauth_states        short-lived PKCE/state store for OAuth round-trips.

Providers (Strava, COROS, ...) are peers. A provider account links to exactly
one athlete via (provider, provider_user_id). Per model B, each provider
authorization creates its OWN athlete row — duplicate people across providers
are accepted for now and reconciled later.
"""

import secrets
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from config import supabase

PROVIDERS = ("strava", "coros", "garmin", "wahoo")


# -------------------------
# Time helpers
# -------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def epoch_to_iso(ts: int) -> str:
    """Unix epoch seconds -> ISO-8601 UTC."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# -------------------------
# Athlete (canonical person)
# -------------------------
def create_athlete(profile: Dict[str, Any]) -> str:
    """
    Insert a new canonical athlete from a provider profile and return its
    athlete_id (uuid). Only display/profile fields live on the athlete row;
    tokens live on athlete_providers.
    """
    row = {
        "firstname": profile.get("firstname"),
        "lastname": profile.get("lastname"),
        "email": profile.get("email"),
        "sex": profile.get("sex"),
        "city": profile.get("city"),
        "country": profile.get("country"),
        "timezone": profile.get("timezone"),
        "profile_picture": profile.get("profile_picture"),
        "active": True,
        "status": "active",
        "consent_date": _now_iso(),
        "updated_at": _now_iso(),
    }
    result = supabase.table("athletes").insert(row).execute()
    return result.data[0]["athlete_id"]


# -------------------------
# Provider links + tokens
# -------------------------
def find_provider_link(provider: str, provider_user_id: str) -> Optional[Dict[str, Any]]:
    """Return the athlete_providers row for this external account, or None."""
    res = (
        supabase.table("athlete_providers")
        .select("*")
        .eq("provider", provider)
        .eq("provider_user_id", str(provider_user_id))
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def link_provider(
    athlete_id: str,
    provider: str,
    provider_user_id: str,
    access_token: str,
    refresh_token: Optional[str],
    expires_at_iso: Optional[str],
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create or update the athlete_providers row for (provider, provider_user_id).
    Used on OAuth connect and reconnect. Upserts on the unique
    (provider, provider_user_id) constraint.
    """
    row = {
        "athlete_id": athlete_id,
        "provider": provider,
        "provider_user_id": str(provider_user_id),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at_iso,
        "scope": scope,
        "status": "active",
        "error_message": None,
        "connected_at": _now_iso(),
        "revoked_at": None,
        "updated_at": _now_iso(),
    }
    res = (
        supabase.table("athlete_providers")
        .upsert(row, on_conflict="provider,provider_user_id")
        .execute()
    )
    return res.data[0]


def update_provider_tokens(
    link_id: str,
    access_token: str,
    refresh_token: Optional[str],
    expires_at_iso: Optional[str],
) -> None:
    """Persist refreshed tokens onto an existing provider link."""
    supabase.table("athlete_providers").update({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at_iso,
        "error_message": None,
        "updated_at": _now_iso(),
    }).eq("id", link_id).execute()


def update_provider_status(link_id: str, **fields) -> None:
    """Update status / last_sync / error_message on a provider link."""
    payload = dict(fields)
    payload.setdefault("updated_at", _now_iso())
    try:
        supabase.table("athlete_providers").update(payload).eq("id", link_id).execute()
    except Exception as e:
        print(f"[providers] status update error for link {link_id}: {e}")


def revoke_provider(provider: str, provider_user_id: str) -> int:
    """
    Mark a provider link revoked and clear its tokens. Returns rows affected.
    Used by revoke webhooks / deauthorization.
    """
    res = (
        supabase.table("athlete_providers")
        .update({
            "status": "revoked",
            "access_token": None,
            "refresh_token": None,
            "revoked_at": _now_iso(),
            "error_message": None,
            "updated_at": _now_iso(),
        })
        .eq("provider", provider)
        .eq("provider_user_id", str(provider_user_id))
        .execute()
    )
    return len(res.data or [])


def list_active_links(provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Return active athlete_providers rows to sync. Optionally filter by provider.
    This replaces the old 'select athletes where active=true' — syncability is a
    property of the provider link, not the person.
    """
    query = supabase.table("athlete_providers").select("*").eq("status", "active")
    if provider:
        query = query.eq("provider", provider)
    return query.execute().data or []


# -------------------------
# OAuth state / PKCE
# -------------------------
def generate_pkce() -> Dict[str, str]:
    """Generate a PKCE code_verifier and S256 code_challenge."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return {"code_verifier": verifier, "code_challenge": challenge}


def save_oauth_state(
    provider: str,
    code_verifier: str,
    athlete_id: Optional[str] = None,
    redirect_after: Optional[str] = None,
) -> str:
    """Create a CSRF state tied to a PKCE verifier; return the state token."""
    state = secrets.token_urlsafe(32)
    supabase.table("oauth_states").insert({
        "state": state,
        "provider": provider,
        "code_verifier": code_verifier,
        "athlete_id": athlete_id,
        "redirect_after": redirect_after,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
    }).execute()
    return state


def consume_oauth_state(state: str, provider: str) -> Optional[Dict[str, Any]]:
    """
    Fetch and delete a one-time OAuth state. Returns the row if valid and
    unexpired, else None. Single-use: the row is deleted on read.
    """
    res = (
        supabase.table("oauth_states")
        .select("*")
        .eq("state", state)
        .eq("provider", provider)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return None
    row = rows[0]

    # Delete regardless of validity (single-use, no replay).
    supabase.table("oauth_states").delete().eq("state", state).execute()

    expires_at = row.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                return None
        except ValueError:
            pass
    return row


# -------------------------
# Activities (canonical link)
# -------------------------
def save_activities(
    activities: List[Dict[str, Any]],
    source: str,
    athlete_id: str,
) -> Dict[str, Any]:
    """
    Upsert normalized activity records, stamped with the provider `source` and
    the canonical `athlete_id`. Each activity dict must already be normalized to
    the activities table shape (activity_id, activity_date, distance,
    moving_time, sport_type, activity_name, manual, raw). Provider-specific code
    (strava.py, coros.py) does the normalization and passes records here.
    """
    if not activities:
        return {"status": "no_activities", "inserted": 0}

    records = []
    for a in activities:
        rec = dict(a)
        rec["source"] = source
        rec["athlete_id"] = athlete_id
        records.append(rec)

    result = supabase.table("activities").upsert(records).execute()
    return {"status": "ok", "count": len(records), "data": result.data}
