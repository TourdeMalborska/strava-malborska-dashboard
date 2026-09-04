import os
import requests

from config import supabase
from datetime import datetime
from config import (
    STRAVA_CLIENT_ID,

    STRAVA_CLIENT_SECRET
)

def refresh_access_token(refresh_token: str):

    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.getenv("STRAVA_CLIENT_ID"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
    )

    response.raise_for_status()

    return response.json()
    
def refresh_athlete_token(athlete):

    token_data = refresh_access_token(
        athlete["refresh_token"]
    )

    expires_at = datetime.fromtimestamp(
        token_data["expires_at"]
    )

    supabase.table("athletes").update(
        {
            "refresh_token": token_data["refresh_token"],
            "expires_at": expires_at.isoformat()
        }
    ).eq(
        "strava_athlete_id",
        athlete["strava_athlete_id"]
    ).execute()

    return token_data["access_token"]

def get_activities(access_token):

    response = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={
            "Authorization": f"Bearer {access_token}"
        }
    )

    response.raise_for_status()

    return response.json()