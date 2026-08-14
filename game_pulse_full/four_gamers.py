import html
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests


FEED_URL = "https://www.4gamers.com.tw/rss/latest-news"
CACHE_TTL_SECONDS = 30 * 60
FAILURE_RETRY_SECONDS = 5 * 60
MAX_FEED_ITEMS = 40
_CACHE = {"at": 0.0, "failed_at": 0.0, "rows": []}
_CACHE_LOCK = threading.Lock()


def _plain_text(value, max_chars=240):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > max_chars:
        value = value[:max_chars].rstrip() + "…"
    return value


def _published_at(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_article_url(value):
    value = (value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "4gamers.com.tw",
        "www.4gamers.com.tw",
    }:
        return ""
    return value


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    rows = []
    seen = set()
    for item in root.findall(".//item")[:MAX_FEED_ITEMS]:
        title = _plain_text(item.findtext("title"), max_chars=180)
        url = _safe_article_url(item.findtext("link"))
        if not title or not url or url in seen:
            continue
        seen.add(url)
        rows.append({
            "gid": url.rsplit("/", 1)[-1],
            "title": title,
            "url": url,
            "author": "4Gamers",
            "feedlabel": "4Gamers",
            "contents": _plain_text(item.findtext("description"), max_chars=240),
            "published_at": _published_at(item.findtext("pubDate")),
        })
    return rows


def _download_feed(session=None, timeout=8):
    client = session or requests
    response = client.get(
        FEED_URL,
        headers={
            "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8",
            "User-Agent": "WAVESIG/1.0 (+public RSS reader)",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return parse_feed(response.text)


def latest_news(limit=8):
    limit = max(1, min(int(limit), 20))
    now = time.monotonic()
    if _CACHE["rows"] and now - _CACHE["at"] < CACHE_TTL_SECONDS:
        return [dict(row) for row in _CACHE["rows"][:limit]]
    if _CACHE["failed_at"] and not _CACHE["rows"] and now - _CACHE["failed_at"] < FAILURE_RETRY_SECONDS:
        return []

    with _CACHE_LOCK:
        now = time.monotonic()
        if _CACHE["rows"] and now - _CACHE["at"] < CACHE_TTL_SECONDS:
            return [dict(row) for row in _CACHE["rows"][:limit]]
        if _CACHE["failed_at"] and not _CACHE["rows"] and now - _CACHE["failed_at"] < FAILURE_RETRY_SECONDS:
            return []
        try:
            rows = _download_feed()
        except Exception:
            _CACHE["failed_at"] = now
            # A stale cache is safer than breaking the public news endpoint.
            if _CACHE["rows"]:
                return [dict(row) for row in _CACHE["rows"][:limit]]
            return []
        _CACHE["rows"] = rows
        _CACHE["at"] = now
        _CACHE["failed_at"] = 0.0
        return [dict(row) for row in rows[:limit]]


def _search_key(value):
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(ch for ch in value if ch.isalnum())


def filter_related_news(game_title, rows, limit=4):
    needle = _search_key(game_title)
    if len(needle) < 4:
        return []
    matched = []
    for row in rows or []:
        haystack = _search_key(f"{row.get('title', '')} {row.get('contents', '')}")
        if needle in haystack:
            matched.append(dict(row))
            if len(matched) >= max(1, min(int(limit), 8)):
                break
    return matched


def related_news(game_title, limit=4):
    return filter_related_news(game_title, latest_news(limit=20), limit=limit)
