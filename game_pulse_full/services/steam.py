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
STEAM_REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"


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


def app_reviews(appid, count=10, language="tchinese", review_type="all", max_chars=360):
    """Fetch recent public Steam user reviews for one app.

    Reviews are normalized into short excerpts. WAVESIG displays these as
    third-party Steam user reviews and links back to Steam for the full source.
    """
    appid = str(appid or "").strip()
    if not appid.isdigit():
        return {"reviews": [], "summary": {}, "language": language}

    review_type = review_type if review_type in {"all", "positive", "negative"} else "all"
    count = max(1, min(int(count), 30))
    max_chars = max(120, min(int(max_chars), 600))

    r = requests.get(
        STEAM_REVIEWS_URL.format(appid=appid),
        params={
            "json": 1,
            "filter": "recent",
            "language": language,
            "cursor": "*",
            "review_type": review_type,
            "purchase_type": "all",
            "num_per_page": count,
        },
        headers={"User-Agent": "WAVESIG/1.0 (+Steam recent reviews)"},
        timeout=15,
    )
    r.raise_for_status()
    payload = r.json() or {}
    rows = payload.get("reviews") or []
    result = []

    for row in rows:
        text = _plain_text(row.get("review"))
        if not text:
            continue
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "…"

        author = row.get("author") or {}
        ts = int(row.get("timestamp_created") or 0)
        created_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None
        playtime_minutes = author.get("playtime_at_review")
        if playtime_minutes is None:
            playtime_minutes = author.get("playtime_forever")
        try:
            playtime_hours = round(float(playtime_minutes or 0) / 60.0, 1)
        except (TypeError, ValueError):
            playtime_hours = None

        result.append({
            "recommendationid": str(row.get("recommendationid") or ""),
            "voted_up": bool(row.get("voted_up")),
            "content": text,
            "created_at": created_at,
            "timestamp_created": ts,
            "votes_up": int(row.get("votes_up") or 0),
            "votes_funny": int(row.get("votes_funny") or 0),
            "comment_count": int(row.get("comment_count") or 0),
            "playtime_hours": playtime_hours,
            "language": row.get("language") or language,
            "steam_purchase": bool(row.get("steam_purchase")),
            "received_for_free": bool(row.get("received_for_free")),
            "early_access": bool(row.get("written_during_early_access")),
            "source": "Steam User Review",
            "source_url": f"https://steamcommunity.com/app/{appid}/reviews/",
        })

    summary = payload.get("query_summary") or {}
    return {
        "reviews": result,
        "summary": {
            "total_positive": int(summary.get("total_positive") or 0),
            "total_negative": int(summary.get("total_negative") or 0),
            "total_reviews": int(summary.get("total_reviews") or 0),
            "review_score_desc": summary.get("review_score_desc") or "",
        },
        "language": language,
    }
