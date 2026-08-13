import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATABASE_PATH = BASE_DIR / "data" / "game_pulse.db"

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "").strip()
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
STEAM_WEB_API_KEY = os.getenv("STEAM_WEB_API_KEY", "").strip()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
WIKIMEDIA_USER_AGENT = os.getenv(
    "WIKIMEDIA_USER_AGENT",
    "WAVESIG/1.0 (https://game-pulse.onrender.com)",
).strip()

MODE = os.getenv("GAME_PULSE_MODE", "auto").strip().lower()
HOT_LIMIT = int(os.getenv("HOT_LIMIT", "30"))
RECENT_LIMIT = int(os.getenv("RECENT_LIMIT", "30"))
UPCOMING_LIMIT = int(os.getenv("UPCOMING_LIMIT", "30"))
SOCIAL_SIGNAL_LIMIT = max(1, int(os.getenv("SOCIAL_SIGNAL_LIMIT", "20")))
SOCIAL_SIGNAL_TTL_HOURS = max(1.0, float(os.getenv("SOCIAL_SIGNAL_TTL_HOURS", "24")))
SOCIAL_SIGNAL_WINDOW_HOURS = max(1, int(os.getenv("SOCIAL_SIGNAL_WINDOW_HOURS", "48")))

def live_credentials_ready():
    return bool(TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET)

def effective_mode():
    if MODE == "demo":
        return "demo"
    if MODE == "live":
        return "live"
    return "live" if live_credentials_ready() else "demo"
