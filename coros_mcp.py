"""Read-only COROS MCP connectivity probe. No user credentials or tokens used."""
import os
import requests

COROS_MCP_URL = os.getenv("COROS_MCP_URL", "https://mcpeu.coros.com/mcp")

def check_coros_connection():
    try:
        response = requests.post(
            COROS_MCP_URL,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "tour-de-malborska-poc",
                        "version": "0.1.0",
                    },
                },
            },
            timeout=15,
            allow_redirects=False,
        )
    except requests.RequestException:
        return {"status": "network_error", "reachable": False}

    return {
        "http_status": response.status_code,
        "authentication_required": response.status_code == 401,
        "redirect": response.status_code in (301, 302, 307, 308),
        "reachable": response.status_code < 500,
    }
