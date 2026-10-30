"""
COROS connect test helper (Phase 3) — RUN ON A MACHINE OUTSIDE THE CORPORATE
VPN/PROXY (the work PC's TLS interception blocks mcpeu.coros.com).

Purpose
  Complete one real COROS OAuth authorization-code + PKCE round-trip and print
  the RAW token response and the RAW queryUserInfo MCP result, so we can see
  exactly what COROS returns and finalize the identity/profile mapping in
  coros.py (resolve_user_id / fetch_profile) against real data.

What it does NOT do
  It does not write to the database or to Infisical. It only talks to COROS and
  prints results to your terminal. Tokens are shown so you can inspect the
  response shape — run it somewhere private and don't paste full tokens back
  verbatim (mask them; see "WHAT TO SEND BACK" at the end of the run).

Prerequisites
  - Python 3.9+ and `pip install requests`
  - COROS_CLIENT_ID available (from Infisical prod/app, or paste when prompted)
  - A COROS account you can log into (EU region)

How the redirect works
  COROS registered the PRODUCTION redirect
  (https://tourdemalborska.vercel.app/auth/coros/callback). We reuse it: you
  authorize in the browser, COROS redirects to that production URL with
  ?code=...&state=... in the address bar. You COPY the `code` value from the
  browser's address bar and paste it here. (The production page itself will try
  to process it too; that's fine — the code is single-use, so whoever exchanges
  it first wins. If the production callback consumes it, just re-run and be
  quick, or temporarily note the code before the page finishes.)

Usage
  python coros_connect_test.py
"""

import os
import sys
import json
import base64
import hashlib
import secrets
import urllib.parse
import requests

COROS_MCP_HOST = "https://mcpeu.coros.com"
AUTH_ENDPOINT = f"{COROS_MCP_HOST}/oauth2/authorize"
TOKEN_ENDPOINT = f"{COROS_MCP_HOST}/oauth2/token"
MCP_ENDPOINT = f"{COROS_MCP_HOST}/mcp"
SCOPES = "mcp.tools offline_access"
REDIRECT_URI = os.getenv(
    "COROS_REDIRECT_URI",
    "https://tourdemalborska.vercel.app/auth/coros/callback",
)


def _mask(value, keep=6):
    if not value:
        return value
    s = str(value)
    return s[:keep] + "…(" + str(len(s)) + " chars)" if len(s) > keep else s


def gen_pkce():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def mcp_call(access_token, method, params, req_id):
    resp = requests.post(
        MCP_ENDPOINT,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        },
        json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
        timeout=30,
    )
    resp.raise_for_status()
    ctype = resp.headers.get("Content-Type", "")
    if "text/event-stream" in ctype:
        payload = None
        for line in resp.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    payload = json.loads(line[len("data:"):].strip())
                except json.JSONDecodeError:
                    continue
        return payload if payload is not None else {"_raw_sse": resp.text}
    return resp.json()


def main():
    client_id = os.getenv("COROS_CLIENT_ID")
    if not client_id:
        client_id = input("Paste COROS_CLIENT_ID: ").strip()
    if not client_id:
        print("No COROS_CLIENT_ID provided. Aborting.")
        sys.exit(1)

    verifier, challenge = gen_pkce()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    print("=" * 70)
    print("STEP 1 — Open this URL in your browser and authorize with COROS:")
    print()
    print(authorize_url)
    print()
    print("STEP 2 — After authorizing, the browser goes to the production")
    print("callback URL. Copy the value of the `code` query parameter from the")
    print("browser's address bar (everything after 'code=' up to the next '&').")
    print("=" * 70)

    code = input("Paste the `code` value here: ").strip()
    if not code:
        print("No code provided. Aborting.")
        sys.exit(1)

    print("\nExchanging code for tokens (public client + PKCE)...")
    token_resp = requests.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )

    print(f"Token endpoint HTTP {token_resp.status_code}")
    if token_resp.status_code != 200:
        print("Token exchange FAILED. Raw response:")
        print(token_resp.text[:1000])
        sys.exit(1)

    token_data = token_resp.json()

    # Show token response with secrets masked but structure intact.
    masked = dict(token_data)
    for k in ("access_token", "refresh_token", "id_token"):
        if k in masked:
            masked[k] = _mask(masked[k])
    print("\n--- TOKEN RESPONSE (secrets masked, keys/shape intact) ---")
    print(json.dumps(masked, indent=2))
    print("Token response KEYS:", sorted(token_data.keys()))

    # If there is an id_token, decode its payload (unverified) to see claims.
    if token_data.get("id_token"):
        try:
            parts = token_data["id_token"].split(".")
            pad = "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
            print("\n--- id_token CLAIMS (unverified) ---")
            print("claim keys:", sorted(claims.keys()))
            if "sub" in claims:
                print("sub present (candidate provider_user_id):", _mask(claims["sub"]))
        except Exception as e:
            print("Could not decode id_token:", e)

    access_token = token_data.get("access_token")

    # Now call the MCP queryUserInfo tool to see the identity/profile shape.
    print("\nCalling MCP initialize + queryUserInfo...")
    try:
        mcp_call(access_token, "initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "tdm-connect-test", "version": "0.1.0"},
        }, 1)
        info = mcp_call(access_token, "tools/call",
                        {"name": "queryUserInfo", "arguments": {}}, 2)
        print("\n--- queryUserInfo RESULT (raw shape) ---")
        print(json.dumps(info, indent=2)[:4000])
    except Exception as e:
        print("queryUserInfo call failed:", e)

    # Also try one querySportRecords to confirm the activity read shape.
    print("\nCalling MCP querySportRecords (last 7 days)...")
    try:
        recs = mcp_call(access_token, "tools/call",
                        {"name": "querySportRecords", "arguments": {"limit": 5}}, 3)
        print("\n--- querySportRecords RESULT (raw shape) ---")
        print(json.dumps(recs, indent=2)[:4000])
    except Exception as e:
        print("querySportRecords call failed:", e)

    print("\n" + "=" * 70)
    print("WHAT TO SEND BACK (so coros.py can be finalized):")
    print("  1. The 'Token response KEYS' line and whether id_token / sub exist.")
    print("  2. The id_token claim keys (NOT the token itself).")
    print("  3. The queryUserInfo RESULT shape (field names; mask personal data).")
    print("  4. The querySportRecords RESULT shape (field names).")
    print("  Do NOT paste full access_token / refresh_token values.")
    print("=" * 70)


if __name__ == "__main__":
    main()
