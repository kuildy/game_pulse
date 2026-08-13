from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from config import (
    SOCIAL_SIGNAL_TTL_HOURS,
    SOCIAL_SIGNAL_WINDOW_HOURS,
    YOUTUBE_API_KEY,
)
from db import save_social_signal, set_source_status, social_signal_is_stale
from services.wikipedia import WikipediaClient
from services.youtube import YouTubeClient


SOURCE_CLIENTS = (
    ("YouTube", YouTubeClient),
    ("Wikipedia", WikipediaClient),
)


def _safe_error(exc):
    message = str(exc)
    for secret in (YOUTUBE_API_KEY,):
        if secret:
            message = message.replace(secret, "[redacted]")
    message = re.sub(
        r"([?&](?:key|client_secret|client_id)=)[^&\s]+",
        r"\1[redacted]",
        message,
        flags=re.I,
    )
    return message[:160]


def _collect_source(source, client_class, games, ttl_hours, window_hours):
    client = client_class()
    if not client.enabled:
        return {
            "source": source,
            "status": "optional",
            "message": "尚未設定 YouTube API 金鑰，已安全略過",
        }

    stale_games = [
        game
        for game in games
        if social_signal_is_stale(game["game_key"], source, ttl_hours)
    ]
    cached = len(games) - len(stale_games)
    collected = 0
    matched = 0
    errors = []

    # Keep requests sequential inside each source. The two sources themselves
    # run in parallel, which is fast enough without stressing a small NAS.
    for game in stale_games:
        try:
            if source == "YouTube":
                metrics = client.game_signal(game["title"], window_hours=window_hours)
                matched += int(metrics.get("matched_videos") or 0)
            else:
                metrics = client.game_signal(game["title"])
                matched += 1 if metrics.get("article_title") else 0

            save_social_signal(
                game["game_key"],
                game["title"],
                source,
                metrics,
                metrics.get("source_url") or "",
            )
            collected += 1
        except Exception as exc:
            errors.append(f"{game.get('title')}: {_safe_error(exc)}")

    attempted = len(stale_games)
    if errors and collected == 0 and attempted:
        status = "error"
    elif errors:
        status = "partial"
    else:
        status = "ok"

    message = f"新增 {collected} 款、快取 {cached} 款；找到 {matched} 筆相符訊號"
    if errors:
        message += f"；{len(errors)} 款失敗：{errors[0]}"
    return {"source": source, "status": status, "message": message}


def refresh_social_signals(games, ttl_hours=None, window_hours=None):
    games = [
        game for game in (games or [])
        if game.get("game_key") and game.get("title")
    ]
    if not games:
        for source, _ in SOURCE_CLIENTS:
            set_source_status(source, "optional", "本次沒有熱門遊戲可蒐集")
        return []

    ttl_hours = SOCIAL_SIGNAL_TTL_HOURS if ttl_hours is None else ttl_hours
    window_hours = SOCIAL_SIGNAL_WINDOW_HOURS if window_hours is None else window_hours
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(
                _collect_source,
                source,
                client_class,
                games,
                ttl_hours,
                window_hours,
            ): source
            for source, client_class in SOURCE_CLIENTS
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "source": source,
                    "status": "error",
                    "message": _safe_error(exc),
                }
            set_source_status(result["source"], result["status"], result["message"][:240])
            results.append(result)
    return sorted(results, key=lambda item: item["source"])
