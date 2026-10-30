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
import json
import urllib.parse
import requests
from typing import Dict, Any

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


def resolve_user_id(token_data: Dict[str, Any]) -> str:
    """
    Derive a stable COROS account id to key the provider link.

    Prefers the id_token 'sub' claim (no extra network call). Falls back to the
    MCP queryUserInfo tool if no id_token is present.
    """
    id_token = token_data.get("id_token")
    if id_token:
        sub = _jwt_sub(id_token)
        if sub:
            return sub

    # Fallback: ask the MCP server who this token belongs to.
    try:
        info = mcp_query_user_info(token_data.get("access_token"))
        text = json.dumps(info)
        # Best-effort: use a hash of the profile if no explicit id is exposed.
        import hashlib as _hashlib
        return "coros_" + _hashlib.sha256(text.encode()).hexdigest()[:24]
    except Exception as e:
        raise RuntimeError(f"Could not resolve COROS user id: {e}")


def _jwt_sub(id_token: str):
    """Extract the 'sub' claim from an unverified JWT payload (identity only)."""
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        import base64 as _b64
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(_b64.urlsafe_b64decode(parts[1] + pad))
        return payload.get("sub")
    except Exception:
        return None


def fetch_profile(access_token: str) -> Dict[str, Any]:
    """
    Fetch a display profile for a newly-connected COROS athlete via MCP
    queryUserInfo. Returns the canonical athlete profile shape; falls back to an
    empty profile if the call fails (the athlete can still be created).
    """
    profile = {"firstname": None, "lastname": None, "email": None}
    try:
        info = mcp_query_user_info(access_token)
        # queryUserInfo returns profile fields; shape may vary, so map defensively.
        result = info.get("result", info)
        content = result.get("content") if isinstance(result, dict) else None
        if isinstance(content, dict):
            profile["firstname"] = content.get("firstName") or content.get("firstname")
            profile["lastname"] = content.get("lastName") or content.get("lastname")
            profile["sex"] = content.get("gender") or content.get("sex")
    except Exception as e:
        print(f"[coros] profile fetch failed, creating minimal athlete: {e}")
    return profile


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
