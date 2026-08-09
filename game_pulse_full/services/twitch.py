import time
import requests
from config import TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX = "https://api.twitch.tv/helix"

class TwitchClient:
    def __init__(self):
        self.client_id = TWITCH_CLIENT_ID
        self.client_secret = TWITCH_CLIENT_SECRET
        self._token = None
        self._token_expiry = 0

    @property
    def enabled(self):
        return bool(self.client_id and self.client_secret)

    def token(self):
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        r = requests.post(
            TOKEN_URL,
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + int(data.get("expires_in", 3600))
        return self._token

    def get(self, path, params=None):
        r = requests.get(
            f"{HELIX}/{path}",
            params=params or {},
            headers={
                "Client-Id": self.client_id,
                "Authorization": f"Bearer {self.token()}",
            },
            timeout=25,
        )
        r.raise_for_status()
        return r.json()

    def top_games(self, limit=30):
        data = self.get("games/top", {"first": min(int(limit), 100)}).get("data", [])
        result = []
        for idx, g in enumerate(data, start=1):
            box = (g.get("box_art_url") or "").replace("{width}", "600").replace("{height}", "800")
            result.append({
                "twitch_game_id": g.get("id"),
                "title": g.get("name") or "未命名遊戲",
                "cover_url": box,
                "twitch_rank": idx,
                "twitch_score": max(0.0, 1 - ((idx - 1) / max(len(data), 1))),
            })
        return result
