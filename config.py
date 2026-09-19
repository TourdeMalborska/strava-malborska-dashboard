# config.py
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Required Strava settings
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_VERIFY_TOKEN = os.getenv("STRAVA_VERIFY_TOKEN")

# Redirect URI can be set in .env to allow local/dev overrides
STRAVA_REDIRECT_URI = os.getenv(
    "STRAVA_REDIRECT_URI",
    "https://strava-malborska-dashboard.vercel.app/auth/strava/callback"
)

# Supabase client (server side). Use SERVICE ROLE KEY only on trusted server.
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Basic validation to fail fast if required env vars are missing
_missing = []
if not STRAVA_CLIENT_ID:
    _missing.append("STRAVA_CLIENT_ID")
if not STRAVA_CLIENT_SECRET:
    _missing.append("STRAVA_CLIENT_SECRET")
if not SUPABASE_URL:
    _missing.append("SUPABASE_URL")
if not SUPABASE_SERVICE_ROLE_KEY:
    _missing.append("SUPABASE_SERVICE_ROLE_KEY")

if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(_missing)}")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
