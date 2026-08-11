import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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
                "igdb_id": (g.get("igdb_id") or "").strip() or None,
                "title": g.get("name") or "未命名遊戲",
                "cover_url": box,
                "twitch_rank": idx,
                # 僅作 API 失敗時的排名備援訊號；正式 PULSE 優先使用即時觀看人數。
                "twitch_score": max(0.0, 1 - ((idx - 1) / max(len(data), 1))),
            })
        return result

    def game_live_stats(self, game_id, stream_limit=100):
        """取得單一 Twitch 遊戲分類的即時觀看訊號。

        Helix Get Streams 會依 viewer_count 由高到低排序；這裡固定取前 100 個
        直播頻道並加總，因此 twitch_viewers 是「前 100 個直播頻道合計」，
        不是宣稱整個分類所有直播的精確總觀看數。
        """
        game_id = str(game_id or "").strip()
        if not game_id:
            return {"viewers": None, "channels": None, "error": "missing game_id"}

        try:
            data = self.get(
                "streams",
                {
                    "game_id": game_id,
                    "type": "live",
                    "first": max(1, min(int(stream_limit), 100)),
                },
            ).get("data", [])
            return {
                "viewers": sum(int(row.get("viewer_count", 0) or 0) for row in data),
                "channels": len(data),
                "error": None,
            }
        except Exception as exc:
            return {"viewers": None, "channels": None, "error": str(exc)[:160]}

    def live_stats_for_games(self, game_ids, max_workers=6, stream_limit=100):
        """平行抓取多款遊戲的即時 Twitch 觀看訊號。"""
        unique_ids = list(dict.fromkeys(
            str(game_id).strip()
            for game_id in game_ids
            if str(game_id or "").strip()
        ))
        if not unique_ids:
            return {}

        # top_games() 已先取得 token；這裡預先呼叫一次，避免多執行緒同時刷新 token。
        self.token()
        result = {}
        workers = max(1, min(int(max_workers), 8, len(unique_ids)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self.game_live_stats, game_id, stream_limit): game_id
                for game_id in unique_ids
            }
            for future in as_completed(futures):
                game_id = futures[future]
                try:
                    result[game_id] = future.result()
                except Exception as exc:
                    result[game_id] = {
                        "viewers": None,
                        "channels": None,
                        "error": str(exc)[:160],
                    }
        return result
