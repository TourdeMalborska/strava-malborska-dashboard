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
def create_athlete(profile: Dict[str, Any], source: str) -> str:
    """
    Insert a new canonical athlete from a provider profile and return its
    athlete_id (uuid). Only display/profile fields live on the athlete row;
    tokens live on athlete_providers.

    `source` records the ORIGIN provider — which provider this athlete first
    entered the system through (strava/coros/garmin/wahoo). Distinct from the
    per-link athlete_providers.provider and the per-activity activities.source.
    """
    row = {
        "firstname": profile.get("firstname"),
        "lastname": profile.get("lastname"),
        "email": profile.get("email"),
        "sex": profile.get("sex"),
        "timezone": profile.get("timezone"),
        "source": source,
        "active": True,
        "status": "active",
        "consent_date": _now_iso(),
        "updated_at": _now_iso(),
    }
    result = supabase.table("athletes").insert(row).execute()
    return result.data[0]["athlete_id"]


def record_consent(athlete_id: str) -> None:
    """
    Stamp the moment the athlete accepted the current consent text on the
    connect page. Called from every OAuth callback, including reconnects, so
    athletes who joined before the consent step existed are re-recorded when
    they reconnect.
    """
    supabase.table("athletes").update({
        "consent_date": _now_iso(),
        "updated_at": _now_iso(),
    }).eq("athlete_id", athlete_id).execute()


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


def _count(query) -> int:
    return query.execute().count or 0


def purge_provider_data(provider: str, provider_user_id, dry_run: bool = False) -> Dict[str, Any]:
    """
    Permanently delete everything we hold for ONE provider account
    (Strava API Policy 2.5 / 7.4: deletion on revocation or on request).

    Removes, for the athlete linked to (provider, provider_user_id):
      - their activities from that provider
      - their monthly totals from that provider
      - the provider link itself (tokens included)
      - for Strava: stored webhook events about that Strava user
      - the athlete row too, IF no other provider link remains for them
        (the activities FK has no cascade, so activities are deleted first)

    dry_run=True only counts what WOULD be deleted. Returns a summary dict.
    Safe to call twice: the second call finds nothing and deletes nothing.
    """
    uid = str(provider_user_id)
    link = find_provider_link(provider, uid)
    out: Dict[str, Any] = {
        "provider": provider, "provider_user_id": uid, "dry_run": dry_run,
        "link_found": bool(link), "activities": 0, "monthly_totals": 0,
        "webhook_events": 0, "athlete_deleted": False,
    }

    if provider == "strava":
        events = supabase.table("webhook_events").select("*", count="exact").filter(
            "payload->>owner_id", "eq", uid).limit(0)
        out["webhook_events"] = _count(events)
        if not dry_run and out["webhook_events"]:
            supabase.table("webhook_events").delete().filter(
                "payload->>owner_id", "eq", uid).execute()

    if not link:
        return out

    athlete_id = link["athlete_id"]
    out["activities"] = _count(
        supabase.table("activities").select("*", count="exact")
        .eq("athlete_id", athlete_id).eq("source", provider).limit(0))
    out["monthly_totals"] = _count(
        supabase.table("athlete_monthly_totals").select("*", count="exact")
        .eq("athlete_id", athlete_id).eq("source", provider).limit(0))

    other_links = [
        l for l in (supabase.table("athlete_providers").select("id")
                    .eq("athlete_id", athlete_id).execute().data or [])
        if l["id"] != link["id"]
    ]
    out["athlete_deleted"] = not other_links

    if dry_run:
        return out

    supabase.table("activities").delete().eq("athlete_id", athlete_id).eq("source", provider).execute()
    supabase.table("athlete_monthly_totals").delete().eq("athlete_id", athlete_id).eq("source", provider).execute()
    supabase.table("athlete_providers").delete().eq("id", link["id"]).execute()
    if not other_links:
        # No provider left for this person: remove any remaining rows that point
        # at the athlete (FK without cascade), then the athlete itself.
        supabase.table("activities").delete().eq("athlete_id", athlete_id).execute()
        supabase.table("athletes").delete().eq("athlete_id", athlete_id).execute()
    return out


def rollup_old_activities(source: str, keep_days: int = 7) -> Dict[str, int]:
    """
    Retention: fold activities older than `keep_days` (calendar days incl. today)
    for `source` into athlete_monthly_totals and delete them, atomically, via the
    SQL function created in migration 009. Service-role only. Idempotent.
    """
    res = supabase.rpc(
        "rollup_old_activities", {"p_source": source, "p_keep_days": keep_days}
    ).execute()
    row = (res.data or [{}])[0] if isinstance(res.data, list) else (res.data or {})
    return {
        "activities_deleted": int(row.get("activities_deleted", 0) or 0),
        "totals_rows_touched": int(row.get("totals_rows_touched", 0) or 0),
    }


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
