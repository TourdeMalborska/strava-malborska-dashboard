"""
COROS MCP integration for Tour de Malborska.

COROS exposes training data through an MCP server secured with OAuth 2.0
(authorization code + PKCE) and RFC 7591 Dynamic Client Registration. This
module builds that integration in stages:

  Stage A (this file, now): register_client() — one-time Dynamic Client
    Registration to obtain client_id / client_secret. No approval needed.
  Stage B: per-athlete OAuth connect flow (/auth/coros + callback) with PKCE.
  Stage C: MCP session + querySportRecords read, feeding the daily sync with
    source="coros".

Region: EU account data lives behind the EU MCP host. See docs/multi-provider.md
for the MCP-vs-Partner-API decision log.

Discovery (https://mcpeu.coros.com/.well-known/oauth-authorization-server):
  authorization_endpoint : https://mcpeu.coros.com/oauth2/authorize
  token_endpoint         : https://mcpeu.coros.com/oauth2/token
  registration_endpoint  : https://mcpeu.coros.com/connect/register
  code_challenge_methods : ["S256"]   (PKCE required)
  scopes_supported       : ["openid", "mcp.tools", "offline_access"]
"""

import os
import re
import json
import urllib.parse
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

# -------------------------
# Endpoints / configuration
# -------------------------
# COROS_MCP_URL is stored in Infisical (prod/app) as the full MCP tool endpoint,
# e.g. https://mcpeu.coros.com/mcp. We derive the auth host from it so there is
# a single source of truth. Falls back to the EU host.
COROS_MCP_URL = os.getenv("COROS_MCP_URL", "https://mcpeu.coros.com/mcp")
COROS_MCP_HOST = COROS_MCP_URL.rsplit("/mcp", 1)[0] or "https://mcpeu.coros.com"

COROS_AUTHORIZATION_ENDPOINT = f"{COROS_MCP_HOST}/oauth2/authorize"
COROS_TOKEN_ENDPOINT = f"{COROS_MCP_HOST}/oauth2/token"
COROS_REGISTRATION_ENDPOINT = f"{COROS_MCP_HOST}/connect/register"

# Public OAuth client (Dynamic Client Registration returned no client_secret and
# token_endpoint_auth_method="none"). Security comes from PKCE, not a secret.
COROS_CLIENT_ID = os.getenv("COROS_CLIENT_ID")

# Scopes: offline_access -> refresh token; mcp.tools -> call tools such as
# querySportRecords. COROS also returns openid; we request what we need.
COROS_SCOPES = "mcp.tools offline_access"

# Redirect URI must EXACTLY match what was registered with COROS. Stored in
# Infisical (prod/app) as COROS_REDIRECT_URI; defaults to the prod callback.
COROS_REDIRECT_URI = os.getenv(
    "COROS_REDIRECT_URI",
    "https://tourdemalborska.vercel.app/auth/coros/callback",
)


# -------------------------
# Stage A: Dynamic Client Registration (run once)
# -------------------------
def register_client(
    redirect_uri: str = None,
    client_name: str = "Tour de Malborska",
) -> Dict[str, Any]:
    """
    Perform RFC 7591 Dynamic Client Registration against the COROS MCP
    authorization server to obtain client credentials.

    This is a ONE-TIME setup step. Run it once, then store the returned
    client_id and client_secret in Infisical (prod/app) as COROS_CLIENT_ID and
    COROS_CLIENT_SECRET. The app's OAuth flow (Stage B) uses those stored
    credentials; it does NOT register on every run.

    Returns the raw registration response. Does not persist anything.
    """
    redirect = redirect_uri or COROS_REDIRECT_URI

    # Standard RFC 7591 registration payload for an authorization-code client
    # that will use PKCE and request a refresh token.
    payload = {
        "client_name": client_name,
        "redirect_uris": [redirect],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_basic",
        "scope": COROS_SCOPES,
    }

    resp = requests.post(
        COROS_REGISTRATION_ENDPOINT,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json=payload,
        timeout=30,
    )

    # Surface the server's message on failure to make setup debuggable.
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"COROS client registration failed: HTTP {resp.status_code} — "
            f"{resp.text[:500]}"
        )

    return resp.json()


# -------------------------
# Stage B: OAuth authorization-code flow (public client + PKCE)
# -------------------------
def build_authorize_url(state: str, code_challenge: str) -> str:
    """
    Build the COROS authorization URL for the authorization-code + PKCE flow.
    `state` and `code_challenge` are generated per request (see providers.py).
    """
    params = {
        "response_type": "code",
        "client_id": COROS_CLIENT_ID,
        "redirect_uri": COROS_REDIRECT_URI,
        "scope": COROS_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{COROS_AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str, code_verifier: str) -> Dict[str, Any]:
    """
    Exchange an authorization code for tokens. Public client: no client_secret;
    the PKCE code_verifier proves the request originated from us.
    Returns the token response (access_token, refresh_token, expires_in, ...).
    """
    resp = requests.post(
        COROS_TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": COROS_REDIRECT_URI,
            "client_id": COROS_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"COROS token exchange failed: HTTP {resp.status_code} — {resp.text[:400]}"
        )
    return resp.json()


def refresh_token(refresh_token_value: str) -> Dict[str, Any]:
    """Refresh a COROS access token. Returns the new token response."""
    resp = requests.post(
        COROS_TOKEN_ENDPOINT,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token_value,
            "client_id": COROS_CLIENT_ID,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"COROS token refresh failed: HTTP {resp.status_code} — {resp.text[:400]}"
        )
    return resp.json()


# -------------------------
# Stage C (partial): minimal MCP client
# -------------------------
def _mcp_call(access_token: str, method: str, params: Dict[str, Any] = None,
              req_id: int = 1) -> Dict[str, Any]:
    """
    Make a single JSON-RPC call to the COROS MCP endpoint with the user's
    access token. Handles both JSON and SSE (text/event-stream) responses.
    """
    resp = requests.post(
        COROS_MCP_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        },
        json={
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        },
        timeout=30,
    )
    resp.raise_for_status()

    ctype = resp.headers.get("Content-Type", "")
    if "text/event-stream" in ctype:
        # Parse the last JSON data line from the SSE stream.
        payload = None
        for line in resp.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    payload = json.loads(line[len("data:"):].strip())
                except json.JSONDecodeError:
                    continue
        if payload is None:
            raise RuntimeError("COROS MCP returned no parseable SSE data")
        return payload
    return resp.json()


def mcp_query_user_info(access_token: str) -> Dict[str, Any]:
    """Call the queryUserInfo tool and return its raw result."""
    # Establish the session, then call the tool.
    _mcp_call(access_token, "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "tour-de-malborska", "version": "0.1.0"},
    }, req_id=1)
    return _mcp_call(access_token, "tools/call", {
        "name": "queryUserInfo",
        "arguments": {},
    }, req_id=2)


def _jwt_claims(token: str) -> Dict[str, Any]:
    """Decode the (unverified) payload of a JWT. Used only to read identity
    claims from COROS's access token; signature is not validated because the
    token came directly from the token endpoint over TLS."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        import base64 as _b64
        pad = "=" * (-len(parts[1]) % 4)
        return json.loads(_b64.urlsafe_b64decode(parts[1] + pad))
    except Exception:
        return {}


def resolve_user_id(token_data: Dict[str, Any]) -> str:
    """
    Derive the stable COROS account id used to key the provider link.

    Confirmed against real COROS tokens: there is NO id_token, but the
    access_token is a JWT carrying a 'sub' claim (the stable account id).
    """
    access_token = token_data.get("access_token")
    claims = _jwt_claims(access_token) if access_token else {}
    sub = claims.get("sub")
    if not sub:
        raise RuntimeError("COROS access token has no 'sub' claim to identify the user")
    return str(sub)


def _mcp_text(result: Dict[str, Any]) -> str:
    """
    Extract the human-readable text payload from an MCP tools/call result.
    COROS returns result.content = [{"type":"text","text": "...prose..."}].
    """
    try:
        content = result.get("result", {}).get("content", [])
        parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        text = "\n".join(parts)
        # COROS wraps the body in a JSON string literal; unwrap if so.
        if text.startswith('"') and text.endswith('"'):
            try:
                text = json.loads(text)
            except json.JSONDecodeError:
                pass
        return text
    except Exception:
        return ""


def fetch_profile(access_token: str) -> Dict[str, Any]:
    """
    Fetch a display profile for a newly-connected COROS athlete via MCP
    queryUserInfo and parse its prose output.

    Real shape (text):
        User Profile Information
        ========================
        Height: 175.0 cm
        Weight: 60.0 kg
        Birthday: 1996-10-26 (Age: 30)
        Gender: Male
        Nickname: Łukasz
    """
    profile = {"firstname": None, "lastname": None, "email": None, "sex": None}
    try:
        info = mcp_query_user_info(access_token)
        text = _mcp_text(info)

        nick = re.search(r"Nickname:\s*(.+)", text)
        if nick:
            profile["firstname"] = nick.group(1).strip()

        gender = re.search(r"Gender:\s*(\w+)", text)
        if gender:
            g = gender.group(1).strip().lower()
            # Map to the single-char convention used elsewhere (Strava: M/F).
            profile["sex"] = {"male": "M", "female": "F"}.get(g, gender.group(1).strip())
    except Exception as e:
        print(f"[coros] profile fetch failed, creating minimal athlete: {e}")
    return profile


# -------------------------
# Stage C: activity read + parse
# -------------------------
def mcp_query_sport_records(access_token: str, start_date: str, end_date: str,
                            limit: int = 50) -> Dict[str, Any]:
    """
    Call querySportRecords for a date range. Dates are yyyyMMdd in the COROS
    account timezone. Establishes an MCP session first.
    """
    _mcp_call(access_token, "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "tour-de-malborska", "version": "0.1.0"},
    }, req_id=1)
    return _mcp_call(access_token, "tools/call", {
        "name": "querySportRecords",
        "arguments": {
            "startDate": start_date,
            "endDate": end_date,
            "limit": limit,
        },
    }, req_id=2)


# Map COROS sport names to a normalized sport_type string for the ranking.
_COROS_SPORT_NORMALIZE = {
    "cycling": "Ride",
    "running": "Run",
    "trail running": "TrailRun",
    "swimming": "Swim",
    "walking": "Walk",
    "hiking": "Hike",
}


def parse_sport_records(text: str) -> List[Dict[str, Any]]:
    """
    Parse the prose output of querySportRecords into activity records.

    COROS returns LLM-oriented text, e.g.:

        Sport Records — 2026-10-24 to 2026-10-30 (1 records)
        ========================

        1. Cycling — 2026-10-26
           Location: Kluisbergen Droga rowerowa
           Start Coordinates: 50.761002, 3.499000
           Time Window: startTimestamp=1793037600 | endTimestamp=1793040318
           Duration: 45:18 | Distance: 26.54 km
           Average Speed: 35.2 km/h | Avg HR: 122 bpm | Calories: 505 kcal
           LabelId: 481318651069235201 | SportType: 200

    NOTE: this parser depends on COROS's text format. It is inherently more
    fragile than a REST/JSON API and is a key reason to move to the COROS
    Partner API if usage grows (see docs/multi-provider.md). Lines that don't
    parse are skipped rather than failing the whole sync.
    """
    records: List[Dict[str, Any]] = []
    if not text:
        return records

    # Split into per-activity blocks starting at "N. <Sport> — YYYY-MM-DD".
    blocks = re.split(r"\n(?=\d+\.\s)", text)
    for block in blocks:
        header = re.match(r"\s*\d+\.\s*(.+?)\s*[—-]\s*(\d{4}-\d{2}-\d{2})", block)
        if not header:
            continue
        sport_raw = header.group(1).strip()
        activity_date = header.group(2).strip()

        label = re.search(r"LabelId:\s*(\d+)", block)
        if not label:
            # Without a stable activity id we cannot dedup/upsert; skip.
            continue
        activity_id = int(label.group(1))

        dist_km = re.search(r"Distance:\s*([\d.]+)\s*km", block)
        distance_m = int(round(float(dist_km.group(1)) * 1000)) if dist_km else None

        dur = re.search(r"Duration:\s*([\d:]+)", block)
        moving_time = _duration_to_seconds(dur.group(1)) if dur else None

        sport_type = _COROS_SPORT_NORMALIZE.get(sport_raw.lower(), sport_raw)

        records.append({
            "activity_id": activity_id,
            "activity_date": activity_date,
            "distance": distance_m,       # metres, matching Strava's unit
            "moving_time": moving_time,   # seconds
            "sport_type": sport_type,
            "activity_name": f"{sport_raw} {activity_date}",
            "manual": False,
            "raw": {"provider": "coros", "text_block": block.strip()},
        })
    return records


def _duration_to_seconds(hms: str):
    """Convert 'H:MM:SS' or 'MM:SS' to seconds."""
    try:
        parts = [int(p) for p in hms.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 1:
            return parts[0]
    except Exception:
        return None
    return None


def get_activities_range(access_token: str, start_dt: datetime,
                         end_dt: datetime) -> List[Dict[str, Any]]:
    """
    Fetch and parse COROS activities for a datetime range. Converts to the
    yyyyMMdd dates COROS expects (COROS interprets them in the account tz; for a
    daily sync of 'yesterday' this is close enough for ranking purposes).
    """
    start_date = start_dt.strftime("%Y%m%d")
    end_date = end_dt.strftime("%Y%m%d")
    result = mcp_query_sport_records(access_token, start_date, end_date)
    return parse_sport_records(_mcp_text(result))


def refresh_link_token(link: Dict[str, Any]) -> str:
    """
    Refresh a COROS access token for an athlete_providers row and persist the
    rotated tokens. Returns a valid access_token. Mirrors
    strava.refresh_link_token but uses the COROS token endpoint.

    COROS: access tokens last ~30 days, refresh tokens ~180 days and rotate on
    each refresh (the new refresh_token must be stored).
    """
    import providers

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
        print(f"[coros] token persist error for link {link.get('id')}: {e}")

    return token_data["access_token"]


if __name__ == "__main__":
    # Run-once helper:
    #   python coros.py
    #
    # Prints the registered client credentials so you can copy them into
    # Infisical prod/app (COROS_CLIENT_ID / COROS_CLIENT_SECRET). Nothing is
    # written to the database or to Infisical automatically.
    print(f"Registering COROS MCP client at: {COROS_REGISTRATION_ENDPOINT}")
    print(f"Redirect URI: {COROS_REDIRECT_URI}")
    print(f"Scopes: {COROS_SCOPES}")
    print("-" * 60)

    result = register_client()

    # Show the important fields explicitly, then the full response for safety.
    client_id = result.get("client_id")
    client_secret = result.get("client_secret")

    print("Registration succeeded.")
    print(f"  COROS_CLIENT_ID     = {client_id}")
    print(f"  COROS_CLIENT_SECRET = {client_secret}")

    # Some servers return an expiry or a registration access token; surface them
    # so nothing important is lost.
    for extra in (
        "client_id_issued_at",
        "client_secret_expires_at",
        "registration_access_token",
        "registration_client_uri",
    ):
        if extra in result:
            print(f"  {extra} = {result[extra]}")

    print("-" * 60)
    print("Full response:")
    print(json.dumps(result, indent=2))
    print("-" * 60)
    print("NEXT: store COROS_CLIENT_ID and COROS_CLIENT_SECRET in Infisical "
          "prod/app, then we build the OAuth connect flow (Stage B).")
