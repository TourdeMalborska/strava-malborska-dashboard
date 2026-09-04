# config.py

import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")

STRAVA_REDIRECT_URI = (
    "http://localhost:8000/auth/strava/callback"
)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)