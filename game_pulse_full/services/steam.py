import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests


STEAM_CURRENT_PLAYERS_URL = (
    "https://api.steampowered.com/ISteamUserStats/"
    "GetNumberOfCurrentPlayers/v1/"
)
STEAM_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"


def current_players(appid):
    if not appid:
        return None
    try:
        r = requests.get(
            STEAM_CURRENT_PLAYERS_URL,
            params={"appid": int(appid)},
            timeout=12,
        )
        r.raise_for_status()
        payload = r.json().get("response", {})
        if payload.get("result") == 1:
            return int(payload.get("player_count", 0))
    except Exception:
        return None
    return None


def current_players_many(appids, max_workers=8):
    unique_ids = list(dict.fromkeys(
        str(appid).strip()
        for appid in appids
        if str(appid or "").strip().isdigit()
    ))
    if not unique_ids:
        return {}

    result = {}
    workers = max(1, min(int(max_workers), 10, len(unique_ids)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(current_players, appid): appid for appid in unique_ids}
        for future in as_completed(futures):
            appid = futures[future]
            try:
                result[appid] = future.result()
            except Exception:
                result[appid] = None
    return result


def _plain_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def app_news(appid, count=8, maxlength=900):
    """Fetch public Steam news for one app.

    Uses the public ISteamNews/GetNewsForApp v2 endpoint. No publisher key is
    required for public/released app news.
    """
    if not str(appid or "").strip().isdigit():
        return []
    r = requests.get(
        STEAM_NEWS_URL,
        params={
            "appid": int(appid),
            "count": max(1, min(int(count), 20)),
            "maxlength": max(120, min(int(maxlength), 3000)),
            "format": "json",
        },
        timeout=15,
    )
    r.raise_for_status()
    rows = (r.json().get("appnews") or {}).get("newsitems") or []
    result = []
    for row in rows:
        ts = int(row.get("date") or 0)
        published_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None
        result.append({
            "gid": str(row.get("gid") or ""),
            "title": row.get("title") or "Steam News",
            "url": row.get("url") or "",
            "author": row.get("author") or "",
            "feedlabel": row.get("feedlabel") or "Steam",
            "contents": _plain_text(row.get("contents")),
            "published_at": published_at,
        })
    return result
