import re
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import quote

import requests

from config import WIKIMEDIA_USER_AGENT


SEARCH_URL = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia.org/all-access/user/{article}/daily/{start}/{end}"
)


def _norm(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if ch.isalnum() or ch.isspace())
    return re.sub(r"\s+", " ", value).strip().casefold()


def _article_score(game_title, article_title):
    target = _norm(game_title)
    candidate = _norm(re.sub(r"\s*\([^)]*\)\s*$", "", article_title or ""))
    if not target or not candidate:
        return 0.0
    if target == candidate:
        return 1.0
    return SequenceMatcher(None, target, candidate).ratio()


class WikipediaClient:
    def __init__(self, session=None, timeout=12, user_agent=None):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.headers = {"User-Agent": (user_agent or WIKIMEDIA_USER_AGENT).strip()}

    @property
    def enabled(self):
        return True

    def _find_article(self, title):
        response = self.session.get(
            SEARCH_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": f'"{title}" video game',
                "srlimit": 5,
                "format": "json",
                "utf8": 1,
            },
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        candidates = (response.json().get("query") or {}).get("search") or []
        ranked = sorted(
            candidates,
            key=lambda row: _article_score(title, row.get("title")),
            reverse=True,
        )
        if not ranked:
            return None
        best = ranked[0]
        score = _article_score(title, best.get("title"))
        if score < (0.90 if len(_norm(title)) < 8 else 0.76):
            return None
        return best.get("title")

    def game_signal(self, title):
        article_title = self._find_article(title)
        if not article_title:
            return {
                "status": "not_found",
                "article_title": None,
                "latest_daily_views": 0,
                "previous_daily_views": 0,
                "daily_change_percent": None,
                "seven_day_views": 0,
                "source_url": f"https://en.wikipedia.org/w/index.php?search={quote(title)}",
            }

        # Yesterday is the latest normally complete UTC day. Fetch eight days so
        # both a seven-day sum and a previous-day comparison are available.
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        start_date = yesterday - timedelta(days=7)
        article_key = quote(article_title.replace(" ", "_"), safe="")
        response = self.session.get(
            PAGEVIEWS_URL.format(
                article=article_key,
                start=start_date.strftime("%Y%m%d"),
                end=yesterday.strftime("%Y%m%d"),
            ),
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        daily = [
            {
                "date": str(item.get("timestamp") or "")[:8],
                "views": int(item.get("views") or 0),
            }
            for item in (response.json().get("items") or [])
        ]
        latest = daily[-1]["views"] if daily else 0
        previous = daily[-2]["views"] if len(daily) >= 2 else 0
        change = ((latest - previous) / previous * 100) if previous else None

        return {
            "status": "ok",
            "article_title": article_title,
            "latest_daily_views": latest,
            "previous_daily_views": previous,
            "daily_change_percent": round(change, 1) if change is not None else None,
            "seven_day_views": sum(item["views"] for item in daily[-7:]),
            "daily": daily,
            "source_url": f"https://en.wikipedia.org/wiki/{quote(article_title.replace(' ', '_'))}",
        }
