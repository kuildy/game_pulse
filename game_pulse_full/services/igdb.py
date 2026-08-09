import math
import time
from datetime import datetime, timezone
import requests
from config import TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET

IGDB_BASE = "https://api.igdb.com/v4"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"

GAME_FIELDS = (
    "id,name,slug,summary,first_release_date,"
    "cover.image_id,genres.name,platforms.name,"
    "total_rating,total_rating_count,"
    "websites.url,"
    "external_games.external_game_source.name,external_games.url,external_games.uid"
)

class IGDBClient:
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
        payload = r.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + int(payload.get("expires_in", 3600))
        return self._token

    def post(self, endpoint, query):
        r = requests.post(
            f"{IGDB_BASE}/{endpoint}",
            headers={
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {self.token()}",
                "Accept": "application/json",
            },
            data=query.encode("utf-8"),
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def popularity_type_map(self):
        rows = self.post(
            "popularity_types",
            "fields name,updated_at; limit 100;"
        )
        return {r.get("name", ""): r["id"] for r in rows}

    def hot_games(self, limit=30):
        """
        依 IGDB PopScore primitives 組合一個跨平台熱門分數。
        primitive 數值尺度不同，因此每種 primitive 先各自 max-normalize。
        """
        type_map = self.popularity_type_map()
        preferred = {
            "Visits": 0.16,
            "Want to Play": 0.08,
            "Playing": 0.12,
            "24hr Peak Players": 0.18,
            "Global Top Sellers": 0.14,
            "Twitch Hours Watched": 0.22,
            "Total Reviews": 0.10,
        }

        collected = {}
        available_weight = {}

        for name, weight in preferred.items():
            type_id = type_map.get(name)
            if not type_id:
                continue
            rows = self.post(
                "popularity_primitives",
                f"fields game_id,value,popularity_type; "
                f"where popularity_type = {int(type_id)}; "
                f"sort value desc; limit 100;"
            )
            if not rows:
                continue
            max_value = max(float(r.get("value", 0) or 0) for r in rows) or 1.0
            for row in rows:
                gid = int(row["game_id"])
                normalized = max(0.0, float(row.get("value", 0) or 0) / max_value)
                collected[gid] = collected.get(gid, 0.0) + normalized * weight
                available_weight[gid] = available_weight.get(gid, 0.0) + weight

        if not collected:
            return []

        normalized_scores = {
            gid: (score / max(available_weight.get(gid, 1e-9), 1e-9))
            for gid, score in collected.items()
        }
        top_ids = [
            gid for gid, _ in sorted(
                normalized_scores.items(), key=lambda kv: kv[1], reverse=True
            )[:max(limit * 2, 50)]
        ]

        games = self.games_by_ids(top_ids)
        by_id = {g["id"]: g for g in games}
        result = []
        for gid in top_ids:
            g = by_id.get(gid)
            if not g:
                continue
            item = self.transform_game(g)
            item["igdb_pop_score"] = normalized_scores.get(gid, 0.0)
            result.append(item)
            if len(result) >= limit:
                break
        return result

    def games_by_ids(self, ids):
        if not ids:
            return []
        joined = ",".join(str(int(x)) for x in ids[:100])
        return self.post(
            "games",
            f"fields {GAME_FIELDS}; where id = ({joined}); limit 100;"
        )

    def games_by_release_window(self, start_ts, end_ts, limit=30, newest_first=True):
        direction = "desc" if newest_first else "asc"
        return [
            self.transform_game(g)
            for g in self.post(
                "games",
                f"fields {GAME_FIELDS}; "
                f"where first_release_date >= {int(start_ts)} & "
                f"first_release_date <= {int(end_ts)}; "
                f"sort first_release_date {direction}; limit {int(limit)};"
            )
        ]

    @staticmethod
    def transform_game(g):
        cover = g.get("cover") or {}
        image_id = cover.get("image_id")
        cover_url = (
            f"https://images.igdb.com/igdb/image/upload/t_cover_big_2x/{image_id}.jpg"
            if image_id else ""
        )

        release_date = None
        if g.get("first_release_date"):
            release_date = datetime.fromtimestamp(
                int(g["first_release_date"]), tz=timezone.utc
            ).date().isoformat()

        websites = g.get("websites") or []
        externals = g.get("external_games") or []

        direct = {}

        # Website URL 直接依官方網域辨識，避免依賴 IGDB 已 deprecated 的 website.category。
        social_or_reference = (
            "wikipedia.org", "fandom.com", "facebook.com", "x.com", "twitter.com",
            "instagram.com", "youtube.com", "youtu.be", "reddit.com", "discord."
        )
        for w in websites:
            url = w.get("url") or ""
            low = url.lower()
            if not url:
                continue
            if "steampowered.com" in low:
                direct.setdefault("steam", url)
            elif "epicgames.com" in low:
                direct.setdefault("epic", url)
            elif "gog.com" in low:
                direct.setdefault("gog", url)
            elif "playstation.com" in low:
                direct.setdefault("playstation", url)
            elif "xbox.com" in low or "microsoft.com" in low:
                direct.setdefault("xbox", url)
            elif "nintendo." in low:
                direct.setdefault("nintendo", url)
            elif not any(domain in low for domain in social_or_reference):
                direct.setdefault("official", url)

        steam_appid = None
        for e in externals:
            source = e.get("external_game_source") or {}
            source_name = source.get("name", "") if isinstance(source, dict) else ""
            source_name = source_name.lower()
            url = e.get("url")
            uid = e.get("uid")

            if "steam" in source_name:
                steam_appid = uid or steam_appid
                if url:
                    direct.setdefault("steam", url)
            elif "gog" in source_name:
                if url:
                    direct.setdefault("gog", url)
            elif "epic" in source_name:
                if url:
                    direct.setdefault("epic", url)
            elif "playstation" in source_name:
                if url:
                    direct.setdefault("playstation", url)
            elif "xbox" in source_name or "microsoft" in source_name:
                if url:
                    direct.setdefault("xbox", url)

        return {
            "igdb_id": g.get("id"),
            "title": g.get("name") or "未命名遊戲",
            "slug": g.get("slug") or "",
            "summary": (g.get("summary") or "").strip(),
            "cover_url": cover_url,
            "release_date": release_date,
            "platforms": [x.get("name") for x in (g.get("platforms") or []) if x.get("name")],
            "genres": [x.get("name") for x in (g.get("genres") or []) if x.get("name")],
            "rating": round(float(g["total_rating"]), 1) if g.get("total_rating") else None,
            "rating_count": g.get("total_rating_count") or 0,
            "direct_links": direct,
            "steam_appid": str(steam_appid) if steam_appid else None,
        }
