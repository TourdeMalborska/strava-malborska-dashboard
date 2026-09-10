import os
import requests

from fastapi import FastAPI
from fastapi.responses import Response, RedirectResponse
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime

from strava import (
    refresh_athlete_token,
    get_activities,
    get_yesterday_activities,
    save_activities
)

from config import (
    STRAVA_CLIENT_ID,
    STRAVA_CLIENT_SECRET,
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
#    print("TOKEN DATA:")
#    print(token_data)

    athlete = token_data["athlete"]

    supabase.table("athletes").upsert({
        "strava_athlete_id": athlete["id"],
        "firstname": athlete["firstname"],
        "lastname": athlete["lastname"],
        "email": athlete.get("email"),
        "profile_picture": athlete.get("profile"),
        "timezone": athlete.get("timezone"),
        "country": athlete.get("country"),
        "city": athlete.get("city"),
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": datetime.utcfromtimestamp(token_data["expires_at"]).isoformat(),
        "consent_date": datetime.utcnow().isoformat(),
        "active": True,
        "status": "active",
        "error_message": None,
        "last_sync": None,
        "updated_at": datetime.utcnow().isoformat(),
        "revoked_at": None
    }).execute()

#   return RedirectResponse(
#       url="/auth-success",
#       status_code=302
#   )

@app.get("/athletes")
def get_athletes():

    result = (
        supabase
        .table("athletes")
        .select("*")
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
# @app.get("/test-refresh")
# def test_refresh():

    # athlete = (
        # supabase
        # .table("athletes")
        # .select("*")
        # .limit(1)
        # .execute()
        # .data[0]
    # )

    # token_data = refresh_access_token(
        # athlete["refresh_token"]
    # )

    # expires_at = datetime.fromtimestamp(
        # token_data["expires_at"]
    # )
    
    # supabase.table("athletes").update(
        # {
            # "refresh_token": token_data["refresh_token"],
            # "expires_at": expires_at.isoformat()
        # }
    # ).eq(
        # "strava_athlete_id",
        # athlete["strava_athlete_id"]
    # ).execute()
    
    # return {
        # "status": "ok",
        # "strava_athlete_id": athlete["strava_athlete_id"],
        # "expires_at": expires_at.isoformat()
    # }
    
@app.get("/test-refresh")
def test_refresh():

    athlete = (
        supabase
        .table("athletes")
        .select("*")
        .limit(1)
        .execute()
        .data[0]
    )

    return refresh_athlete_token(athlete)
    
@app.get("/test-activities")
def test_activities():

    athlete = (
        supabase
        .table("athletes")
        .select("*")
        .limit(1)
        .execute()
        .data[0]
    )

    access_token = refresh_athlete_token(
        athlete
    )

    activities = get_activities(
#        athlete["access_token"]
         access_token 
 )
    return activities[0]
    # return {
        # "count": len(activities)
    # }
    
@app.get("/test-save-activities")
def test_save_activities():

    athlete = (
        supabase
        .table("athletes")
        .select("*")
        .limit(1)
        .execute()
        .data[0]
    )

    access_token = refresh_athlete_token(
        athlete
    )

    activities = get_activities(
        access_token
    )

    save_activities(
        activities
    )

    return {
        "status": "saved",
        "activity_id": activities[0]["id"]
    }
    
@app.get("/test-yesterday")
def test_yesterday():

    athlete = (
        supabase
        .table("athletes")
        .select("*")
        .limit(1)
        .execute()
        .data[0]
    )
    
    access_token = refresh_athlete_token(
        athlete
    )

    activities = get_yesterday_activities(
        access_token
    )

    return {
        "count": len(activities)
    }

#---------------------------
#Temp endpoint for testing revoked tokens
#---------------------------


# @app.get("/test-athlete/{index}")
# def test_athlete(index: int):

    # athlete = (
        # supabase
        # .table("athletes")
        # .select("*")
        # .execute()
        # .data[index]
    # )

    # access_token = refresh_athlete_token(
        # athlete
    # )

    # activities = get_activities(
        # access_token
    # )

    # return {
    # "athlete_id": athlete["strava_athlete_id"],
    # "firstname": athlete["firstname"],
    # "lastname": athlete["lastname"],
    # "activities_found": len(activities),
    # "first_activity_id": (
        # activities[0]["id"]
        # if activities else None
    # )
# }

#Temp test athlete id

@app.get("/test-athlete/{index}")
def test_athlete(index: int):

    athletes = (
        supabase
        .table("athletes")
        .select("*")
        .execute()
        .data
    )

    athlete = athletes[index]

    return {
        "index": index,
        "athlete_id": athlete["strava_athlete_id"],
        "firstname": athlete["firstname"],
        "lastname": athlete["lastname"]
    }

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

    if mode == "subscribe" and token == "malborska123":
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
    # obsługa revoke itd. — twoja logika tutaj
    return {"status": "ok"}


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
                    window.location.href = "https://www.strava.com";
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