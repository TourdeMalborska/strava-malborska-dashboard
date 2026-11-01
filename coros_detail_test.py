"""
COROS activity-detail probe (run on a machine OUTSIDE the corporate VPN/proxy —
the work PC's TLS interception blocks mcpeu.coros.com).

Purpose
  Call the COROS MCP `getActivityDetail` tool for one activity and dump its FULL
  raw response, so we can see every field COROS exposes — in particular any
  indicator of the activity's SOURCE/ORIGIN (watch/device, FIT import, third
  party) and whether it is a MANUAL entry. querySportRecords (the list tool)
  does NOT expose these; getActivityDetail might.

What it does NOT do
  No DB / Infisical writes. It only reads from COROS and prints to your terminal.

Prerequisites
  - Python 3.9+ and `pip install requests`
  - A COROS access token. Two ways to provide it:
      1) Set env COROS_ACCESS_TOKEN=<token>, or
      2) The script can refresh one from a refresh token if you set
         COROS_CLIENT_ID and COROS_REFRESH_TOKEN (from Infisical / the DB).
  - EU region host (default). Override with COROS_MCP_URL if needed.

Target activity (the manually-created COROS ride we're investigating):
  labelId = 481427340851708308   sportType = 200   (2026-10-31, 35.16 km)
Override via CLI args:  python coros_detail_test.py <labelId> <sportType>

Usage
  python coros_detail_test.py
  python coros_detail_test.py 481427340851708308 200
"""

import os
import sys
import json
import requests

COROS_MCP_URL = os.getenv("COROS_MCP_URL", "https://mcpeu.coros.com/mcp")
COROS_MCP_HOST = COROS_MCP_URL.rsplit("/mcp", 1)[0] or "https://mcpeu.coros.com"
COROS_TOKEN_ENDPOINT = f"{COROS_MCP_HOST}/oauth2/token"

DEFAULT_LABEL_ID = "481427340851708308"
DEFAULT_SPORT_TYPE = 200


def get_access_token() -> str:
    """Use COROS_ACCESS_TOKEN directly, or refresh one from a refresh token."""
    tok = os.getenv("COROS_ACCESS_TOKEN")
    if tok:
        return tok.strip()

    client_id = os.getenv("COROS_CLIENT_ID")
    refresh = os.getenv("COROS_REFRESH_TOKEN")
    if client_id and refresh:
        print("No COROS_ACCESS_TOKEN; refreshing from COROS_REFRESH_TOKEN...")
        r = requests.post(
            COROS_TOKEN_ENDPOINT,
            data={"grant_type": "refresh_token", "refresh_token": refresh,
                  "client_id": client_id},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if r.status_code != 200:
            raise SystemExit(f"Token refresh failed: HTTP {r.status_code} — {r.text[:300]}")
        return r.json()["access_token"]

    raise SystemExit(
        "No token. Set COROS_ACCESS_TOKEN, or COROS_CLIENT_ID + COROS_REFRESH_TOKEN."
    )


def mcp_call(access_token: str, method: str, params: dict, req_id: int) -> dict:
    """Single JSON-RPC call to the COROS MCP endpoint. Handles JSON + SSE."""
    resp = requests.post(
        COROS_MCP_URL,
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
        if payload is None:
            return {"_raw_sse": resp.text}
        return payload
    return resp.json()


def dump(title: str, obj) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main():
    label_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LABEL_ID
    sport_type = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SPORT_TYPE

    token = get_access_token()
    print(f"MCP: {COROS_MCP_URL}")
    print(f"Target: labelId={label_id}  sportType={sport_type}")

    # MCP handshake.
    mcp_call(token, "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "tdm-detail-test", "version": "0.1.0"},
    }, 1)

    # List the available tools, so we can see every tool COROS offers (names may
    # reveal a dedicated source/origin tool).
    try:
        tools = mcp_call(token, "tools/list", {}, 2)
        names = [t.get("name") for t in tools.get("result", {}).get("tools", [])]
        dump("AVAILABLE TOOLS", names)
    except Exception as e:
        print("tools/list failed:", e)

    # The main event: full activity detail.
    detail = mcp_call(token, "tools/call", {
        "name": "getActivityDetail",
        "arguments": {"labelId": label_id, "sportType": sport_type},
    }, 3)
    dump("getActivityDetail — FULL RAW RESPONSE", detail)

    # Also pull lap data — sometimes carries device/source metadata.
    try:
        laps = mcp_call(token, "tools/call", {
            "name": "queryActivityLapData",
            "arguments": {"labelId": label_id, "sportType": sport_type},
        }, 4)
        dump("queryActivityLapData — FULL RAW RESPONSE", laps)
    except Exception as e:
        print("queryActivityLapData failed:", e)

    print("\n" + "=" * 70)
    print("WHAT TO LOOK FOR (and send back):")
    print("  - Any field indicating SOURCE/ORIGIN: device name, watch model,")
    print("    'manual', 'import', 'thirdParty', 'dataSource', 'deviceId', FIT, etc.")
    print("  - Whether a manual entry is distinguishable from a device recording.")
    print("  Paste the getActivityDetail output back (mask anything personal).")
    print("=" * 70)


if __name__ == "__main__":
    main()
