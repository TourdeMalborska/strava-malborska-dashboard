import os
import requests
import hmac

from fastapi import FastAPI
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import Response, RedirectResponse
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timezone
from sync import run_daily_sync, run_rolling_sync

app = FastAPI()

import providers
from strava import (
    refresh_link_token,
    get_activities,
    get_yesterday_activities,
    save_activities,
    normalize_activity,
)

from config import (
    STRAVA_CLIENT_ID,
    STRAVA_CLIENT_SECRET,
    STRAVA_VERIFY_TOKEN,
    STRAVA_REDIRECT_URI,
    supabase
)

class StatusResponse(BaseModel):

	status: str

@app.get("/", response_model=StatusResponse)
def root():
    return {
        "status": "running"
    }
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
	return Response(status_code=204)

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }
@app.get("/auth/strava")
def auth_strava():

    url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={STRAVA_CLIENT_ID}"
        "&response_type=code"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        "&approval_prompt=force"
        "&scope=read,activity:read"
    )

    return RedirectResponse(url=url)


import coros as coros_provider


@app.get("/auth/coros")
def auth_coros():
    """
    Start the COROS OAuth connect flow (model B: COROS is an independent
    provider). Generates PKCE + state, stores them in oauth_states, and
    redirects the user to COROS to authorize.
    """
    pkce = providers.generate_pkce()
    state = providers.save_oauth_state(
        provider="coros",
        code_verifier=pkce["code_verifier"],
    )
    url = coros_provider.build_authorize_url(
        state=state,
        code_challenge=pkce["code_challenge"],
    )
    return RedirectResponse(url=url)


@app.get("/auth/coros/callback")
def coros_callback(code: str = None, state: str = None, error: str = None):
    """
    COROS OAuth callback. Validates state, exchanges the code (PKCE), resolves
    the COROS account identity, and stores an athlete_providers link for a new
    canonical athlete (or reuses the existing one on reconnect).
    """
    if error or not code or not state:
        return RedirectResponse(url="/auth-cancelled", status_code=302)

    state_row = providers.consume_oauth_state(state, provider="coros")
    if not state_row:
        # Invalid/expired/replayed state.
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    token_data = coros_provider.exchange_code(
        code=code,
        code_verifier=state_row["code_verifier"],
    )

    # Resolve the COROS account identity for the provider link key.
    coros_user_id = coros_provider.resolve_user_id(token_data)

    expires_at_iso = None
    if token_data.get("expires_in"):
        from datetime import timedelta
        expires_at_iso = (
            datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))
        ).isoformat()

    existing = providers.find_provider_link("coros", coros_user_id)
    if existing:
        athlete_id = existing["athlete_id"]
    else:
        # Model B: a COROS authorization creates its own canonical athlete.
        profile = coros_provider.fetch_profile(token_data.get("access_token"))
        athlete_id = providers.create_athlete(profile)

    providers.link_provider(
        athlete_id=athlete_id,
        provider="coros",
        provider_user_id=coros_user_id,
        access_token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        expires_at_iso=expires_at_iso,
        scope=token_data.get("scope", coros_provider.COROS_SCOPES),
    )

    return RedirectResponse(url="/auth-success", status_code=302)


from datetime import datetime


@app.get("/auth/strava/callback")
def strava_callback(
    code: str = None,
    error: str = None
):

    if not code:
        return RedirectResponse(
           url="/auth-cancelled",
           status_code=302
        )

    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.getenv("STRAVA_CLIENT_ID"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code"
        }
    )

    token_data = response.json()
    athlete = token_data["athlete"]
    strava_user_id = str(athlete["id"])

    # Canonical model: an athlete_providers row links this Strava account to a
    # canonical athlete. Reconnect reuses the existing athlete; a first-time
    # connect creates a new canonical athlete (model B).
    existing = providers.find_provider_link("strava", strava_user_id)
    if existing:
        athlete_id = existing["athlete_id"]
    else:
        athlete_id = providers.create_athlete({
            "firstname": athlete.get("firstname"),
            "lastname": athlete.get("lastname"),
            "email": athlete.get("email"),
            "profile_picture": athlete.get("profile"),
            "timezone": athlete.get("timezone"),
            "country": athlete.get("country"),
            "sex": athlete.get("sex"),
            "city": athlete.get("city"),
        })

    providers.link_provider(
        athlete_id=athlete_id,
        provider="strava",
        provider_user_id=strava_user_id,
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at_iso=providers.epoch_to_iso(token_data["expires_at"]),
        scope="read,activity:read",
    )

    return RedirectResponse(
        url="/auth-success",
        status_code=302
    )

@app.get("/athletes")
def get_athletes():
    # Select explicit profile columns only — never expose tokens (tokens now
    # live on athlete_providers, but stay explicit to avoid future leaks).
    result = (
        supabase
        .table("athletes")
        .select(
            "athlete_id,firstname,lastname,email,sex,city,country,"
            "timezone,profile_picture,active,status,created_at,updated_at"
        )
        .execute()
    )
    return result.data

@app.get("/activities")
def activities():

#Lokalne testowanie
    #access_token = "xxx"

    access_token = os.getenv("STRAVA_ACCESS_TOKEN")

    headers = {
        #"Authorization": f"Bearer xxx"
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers=headers
    )

    return response.json()

#    return {
#        "status": "oauth_success",
#        "authorization_code": code
#    }
def _first_strava_link():
    """Helper for test endpoints: first active Strava provider link, or None."""
    links = providers.list_active_links(provider="strava")
    return links[0] if links else None


@app.get("/test-refresh")
def test_refresh():
    link = _first_strava_link()
    if not link:
        raise HTTPException(status_code=404, detail="No active Strava link")
    access_token = refresh_link_token(link)
    return {"status": "ok", "athlete_id": link["athlete_id"],
            "provider_user_id": link["provider_user_id"]}


@app.get("/test-activities")
def test_activities():
    link = _first_strava_link()
    if not link:
        raise HTTPException(status_code=404, detail="No active Strava link")
    access_token = refresh_link_token(link)
    activities = get_activities(access_token)
    return activities[0] if activities else {"count": 0}


@app.get("/test-save-activities")
def test_save_activities():
    link = _first_strava_link()
    if not link:
        raise HTTPException(status_code=404, detail="No active Strava link")
    access_token = refresh_link_token(link)
    activities = get_activities(access_token)
    result = save_activities(activities, athlete_id=link["athlete_id"])
    return {
        "status": "saved",
        "count": result.get("count", 0),
        "activity_id": activities[0]["id"] if activities else None,
    }


@app.get("/test-yesterday")
def test_yesterday():
    link = _first_strava_link()
    if not link:
        raise HTTPException(status_code=404, detail="No active Strava link")
    access_token = refresh_link_token(link)
    activities = get_yesterday_activities(access_token)
    return {"count": len(activities)}

@app.get("/test-athlete/{index}")
def test_athlete(index: int):
    athletes = (
        supabase
        .table("athletes")
        .select("athlete_id,firstname,lastname")
        .execute()
        .data
    )
    if index < 0 or index >= len(athletes):
        raise HTTPException(status_code=404, detail="Athlete index out of range")

    athlete = athletes[index]
    return {
        "index": index,
        "athlete_id": athlete["athlete_id"],
        "firstname": athlete["firstname"],
        "lastname": athlete["lastname"],
    }


def trigger_github_backup():
    token = os.getenv("GITHUB_BACKUP_TOKEN")

    if not token:
        raise RuntimeError("GITHUB_BACKUP_TOKEN is not configured")

    url = (
        "https://api.github.com/repos/"
        "TourdeMalborska/strava-malborska-dashboard/"
        "actions/workflows/backup-supabase.yml/dispatches"
    )

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"ref": "main"},
        timeout=15,
    )

    if response.status_code != 204:
        raise RuntimeError(
            f"GitHub backup dispatch failed: HTTP {response.status_code}"
        )


@app.get("/sync/daily")
def sync_daily(request: Request):
    cron_secret = os.getenv("CRON_SECRET")

    if not cron_secret:
        raise HTTPException(
            status_code=503,
            detail="Cron authentication is not configured",
        )

    authorization = request.headers.get("authorization", "")
    expected = f"Bearer {cron_secret}"

    if not hmac.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    results = run_daily_sync()

    if not results:
        raise HTTPException(
            status_code=503,
            detail="No active athletes to synchronize",
        )

    errors = [
        result for result in results
        if result.get("error") is not None
    ]

    if errors:
        print(
            f"[sync] Daily sync failed for {len(errors)} "
            f"of {len(results)} athletes"
        )
        raise HTTPException(
            status_code=503,
            detail={
                "status": "sync_failed",
                "athletes_total": len(results),
                "athletes_failed": len(errors),
            },
        )

    try:
        trigger_github_backup()
    except Exception as exc:
        print(f"[backup] Dispatch error: {type(exc).__name__}")
        raise HTTPException(
            status_code=502,
            detail="Synchronization succeeded, but backup dispatch failed",
        )

    return {
        "mode": "daily",
        "status": "sync_success",
        "athletes_synced": len(results),
        "backup": "requested",
        "results": results,
    }

@app.get("/sync/rolling")
def sync_rolling():
    results = run_rolling_sync()
    return {"mode": "rolling", "results": results}

#--------------------------
#HTML Call for welcome page
#Redirect call to Strava service
#--------------------------

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

# GET — Strava challenge verification
@app.get("/api/strava/webhook")
async def strava_webhook_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == STRAVA_VERIFY_TOKEN:
        return JSONResponse(content={"hub.challenge": challenge}, status_code=200)

    return JSONResponse(content={"status": "ignored"}, status_code=200)

# POST — Strava events
@app.post("/api/strava/webhook")
async def strava_webhook_event(request: Request):
    try:
        payload = await request.json()
    except Exception as e:
        print("Invalid JSON in webhook POST:", e)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    print("WEBHOOK EVENT RECEIVED:", payload)

    object_type = payload.get("object_type")
    aspect_type = payload.get("aspect_type")
    object_id = payload.get("object_id")
    owner_id = payload.get("owner_id")
    updates = payload.get("updates") or {}

    # Najpierw zapisujemy surowy event do audytu/debugowania
    try:
        supabase.table("webhook_events").insert({
            "payload": payload
        }).execute()
    except Exception as e:
        # Nie powodujemy retry webhooka tylko dlatego,
        # że zapis pomocniczego logu się nie udał
        print("WEBHOOK EVENT LOG ERROR:", e)

    # Strava revoke/deauthorization event:
    # object_type = athlete
    # aspect_type = update
    # updates.authorized = "false"
    is_revoke_event = (
        object_type == "athlete"
        and aspect_type == "update"
        and str(updates.get("authorized")).lower() == "false"
    )

    if is_revoke_event:
        athlete_id = object_id or owner_id

        try:
            updated_rows = providers.revoke_provider("strava", athlete_id)

            print(
                f"ATHLETE REVOKED: strava_user_id={athlete_id}, "
                f"updated_rows={updated_rows}"
            )

        except Exception as e:
            print(
                f"REVOKE PROCESSING ERROR: "
                f"athlete_id={athlete_id}, error={e}"
            )

            # Na obecnym etapie MVP zwracamy 200,
            # aby Strava nie zapętlała ponowień.
            # Event pozostaje zapisany w webhook_events.
            return {
                "status": "accepted",
                "event": "athlete_revoke",
                "athlete_id": athlete_id,
                "processed": False
            }

        return {
            "status": "ok",
            "event": "athlete_revoke",
            "athlete_id": athlete_id,
            "processed": True
        }

    # Na razie pozostałe eventy tylko logujemy.
    # Nightly sync pozostaje głównym mechanizmem pobierania aktywności.
    return {
        "status": "ok",
        "event": f"{object_type}.{aspect_type}",
        "processed": False
    }

@app.get("/auth-success", response_class=HTMLResponse)
def auth_success():

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tour de Malborska</title>

        <script>
            let countdown = 5;

            setInterval(() => {
                countdown--;

                document.getElementById("counter").innerText = countdown;

                if (countdown <= 0) {
                    window.location.href = "https://www.strava.com/dashboard";
                }
            }, 1000);
        </script>

    </head>
    <body style="
        font-family: Arial;
        text-align: center;
        padding-top: 100px;
    ">

        <h1>✅ Konto zostało połączone</h1>

        <p>
            Autoryzacja aplikacji Tour de Malborska zakończyła się sukcesem.
        </p>

        <p>
            Za <span id="counter">5</span> sekund wrócisz do Stravy.
        </p>

    </body>
    </html>
    """
    
@app.get("/auth-cancelled", response_class=HTMLResponse)
def auth_cancelled():

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tour de Malborska</title>
    </head>
    <body style="
        font-family: Arial;
        text-align: center;
        padding-top: 100px;
    ">

        <h1>❌ Autoryzacja anulowana</h1>

        <p>
            Nie udzielono zgody na połączenie ze Strava.
        </p>

        <p>
            Możesz zamknąć okno lub spróbować ponownie.
        </p>

    </body>
    </html>
    """

# COROS MCP PoC: protected, read-only connectivity test
from coros_mcp import check_coros_connection

@app.get("/test/coros/connection")
def test_coros_connection(request: Request):
    secret = os.getenv("COROS_TEST_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Test authentication not configured")
    provided = request.headers.get("X-Test-Secret", "")
    if not hmac.compare_digest(provided, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return check_coros_connection()
