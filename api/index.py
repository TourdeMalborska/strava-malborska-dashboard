import os
import requests

from fastapi import FastAPI
from fastapi.responses import Response, RedirectResponse
from pydantic import BaseModel

app = FastAPI()

#for local test put real Client_ID from Strava
#STRAVA_CLIENT_ID = "xxx"

# STRAVA_REDIRECT_URI = (
    # "http://localhost:8000/auth/strava/callback"
# )

#For Vercel Production
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")

STRAVA_REDIRECT_URI = (
   "https://strava-malborska-dashboard.vercel.app/auth/strava/callback"
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

@app.get("/auth/strava/callback")
def strava_callback(code: str):

    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.getenv("STRAVA_CLIENT_ID"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
            # "client_id": "xxx",
            # "client_secret": "xxx",
            "code": code,
            "grant_type": "authorization_code"
        }
    )

    return response.json()

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