import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import requests

from config import YOUTUBE_API_KEY


SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _norm(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if ch.isalnum() or ch.isspace())
    return re.sub(r"\s+", " ", value).strip().casefold()


class YouTubeClient:
    def __init__(self, api_key=None, session=None, timeout=12):
        self.api_key = (api_key if api_key is not None else YOUTUBE_API_KEY).strip()
        self.session = session or requests.Session()
        self.timeout = timeout

    @property
    def enabled(self):
        return bool(self.api_key)

    def game_signal(self, title, window_hours=48, max_results=5):
        if not self.enabled:
            raise RuntimeError("YouTube API key is not configured")

        published_after = (
            datetime.now(timezone.utc) - timedelta(hours=max(1, int(window_hours)))
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        search = self.session.get(
            SEARCH_URL,
            params={
                "key": self.api_key,
                "part": "snippet",
                "type": "video",
                "videoCategoryId": "20",
                "q": f'"{title}" game',
                "order": "viewCount",
                "publishedAfter": published_after,
                "maxResults": max(1, min(int(max_results), 10)),
                "safeSearch": "moderate",
            },
            timeout=self.timeout,
        )
        search.raise_for_status()
        search_data = search.json()

        target = _norm(title)
        matches = []
        for item in search_data.get("items") or []:
            snippet = item.get("snippet") or {}
            video_id = (item.get("id") or {}).get("videoId")
            if not video_id:
                continue
            searchable = _norm(f"{snippet.get('title', '')} {snippet.get('description', '')}")
            if target and target not in searchable:
                continue
            matches.append({
                "video_id": video_id,
                "title": snippet.get("title") or "",
                "channel": snippet.get("channelTitle") or "",
                "published_at": snippet.get("publishedAt"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })

        stats_by_id = {}
        if matches:
            stats = self.session.get(
                VIDEOS_URL,
                params={
                    "key": self.api_key,
                    "part": "statistics",
                    "id": ",".join(item["video_id"] for item in matches),
                },
                timeout=self.timeout,
            )
            stats.raise_for_status()
            stats_by_id = {
                item.get("id"): item.get("statistics") or {}
                for item in (stats.json().get("items") or [])
            }

        totals = {"views": 0, "likes": 0, "comments": 0}
        for item in matches:
            stats = stats_by_id.get(item["video_id"], {})
            item["views"] = int(stats.get("viewCount") or 0)
            item["likes"] = int(stats.get("likeCount") or 0)
            item["comments"] = int(stats.get("commentCount") or 0)
            totals["views"] += item["views"]
            totals["likes"] += item["likes"]
            totals["comments"] += item["comments"]

        return {
            "status": "ok",
            "window_hours": int(window_hours),
            "matched_videos": len(matches),
            "estimated_search_results": int((search_data.get("pageInfo") or {}).get("totalResults") or 0),
            "sample_views": totals["views"],
            "sample_likes": totals["likes"],
            "sample_comments": totals["comments"],
            "videos": matches,
            "source_url": f"https://www.youtube.com/results?search_query={quote_plus(title + ' game')}",
        }
