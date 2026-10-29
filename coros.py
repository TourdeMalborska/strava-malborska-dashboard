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
import requests
from typing import Dict, Any

# -------------------------
# Endpoints / configuration
# -------------------------
# Base host for the EU region. Override via COROS_MCP_HOST if the account
# region ever differs (mcpus / mcpcn). The MCP tool endpoint is <host>/mcp.
COROS_MCP_HOST = os.getenv("COROS_MCP_HOST", "https://mcpeu.coros.com")

COROS_AUTHORIZATION_ENDPOINT = f"{COROS_MCP_HOST}/oauth2/authorize"
COROS_TOKEN_ENDPOINT = f"{COROS_MCP_HOST}/oauth2/token"
COROS_REGISTRATION_ENDPOINT = f"{COROS_MCP_HOST}/connect/register"
COROS_MCP_ENDPOINT = f"{COROS_MCP_HOST}/mcp"

# Scopes: offline_access is required to receive a refresh token; mcp.tools is
# required to call tools such as querySportRecords. We deliberately omit openid
# (no identity claims needed) to keep data access minimal.
COROS_SCOPES = "mcp.tools offline_access"

# Redirect URI must EXACTLY match what is registered with COROS. Defaults to the
# live production callback; override locally via COROS_REDIRECT_URI.
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
