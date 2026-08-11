from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from db import (
    create_notification,
    get_current_game_for_watch,
    get_history_baseline,
    list_all_watch_subscriptions,
    update_watch_last_news,
)
from services.steam import app_news


def _game_link(game):
    identifier = game.get("slug") or game.get("game_key") or ""
    return f"/game/{identifier}" if identifier else "/"


def evaluate_notifications(max_news_games=20):
    """Evaluate anonymous watch rules after a data refresh.

    Conservative anti-spam rules:
    - release: 7 days before launch and launch day
    - PULSE: +10 points vs a real 24h baseline
    - Steam: +50% AND +5,000 players vs a real 24h baseline
    - news: one notification when a newer Steam news GID is detected
    """
    subscriptions = list_all_watch_subscriptions()
    today = datetime.now(timezone.utc).date()
    created = 0
    news_targets = []

    for sub in subscriptions:
        game = get_current_game_for_watch(sub["game_key"])
        if not game:
            continue

        link = _game_link(game)
        title = game.get("title") or sub.get("title") or "追蹤遊戲"

        if sub.get("notify_release") and game.get("release_date"):
            try:
                release_date = datetime.fromisoformat(game["release_date"]).date()
                days = (release_date - today).days
                if days == 7:
                    created += int(create_notification(
                        sub["device_id"], game["game_key"], "release", f"{title} 一週後上市",
                        f"距離上市還有 7 天：{game['release_date']}", link,
                        f"release7:{game['game_key']}:{game['release_date']}",
                    ))
                elif days == 0:
                    created += int(create_notification(
                        sub["device_id"], game["game_key"], "release", f"{title} 今天上市",
                        "你追蹤的遊戲今天正式上市。", link,
                        f"release0:{game['game_key']}:{game['release_date']}",
                    ))
            except Exception:
                pass

        baseline = get_history_baseline(game["game_key"], hours=24)
        if baseline:
            if sub.get("notify_pulse"):
                current = float(game.get("pulse_score") or 0)
                previous = float(baseline.get("pulse_score") or 0)
                delta = current - previous
                if delta >= 10:
                    created += int(create_notification(
                        sub["device_id"], game["game_key"], "pulse", f"{title} 熱度明顯上升",
                        f"24H PULSE 上升 {delta:.1f} 分，目前 {current:.1f}。", link,
                        f"pulse:{game['game_key']}:{today.isoformat()}",
                    ))

            if sub.get("notify_steam"):
                current_steam = game.get("steam_players")
                old_steam = baseline.get("steam_players")
                if current_steam is not None and old_steam is not None and int(old_steam) >= 100:
                    diff = int(current_steam) - int(old_steam)
                    ratio = int(current_steam) / max(int(old_steam), 1)
                    if diff >= 5000 and ratio >= 1.5:
                        created += int(create_notification(
                            sub["device_id"], game["game_key"], "steam", f"{title} Steam 玩家暴增",
                            f"Steam 在線玩家 24H 增加 {diff:,}，目前 {int(current_steam):,}。", link,
                            f"steam:{game['game_key']}:{today.isoformat()}",
                        ))

        if (
            sub.get("notify_news")
            and str(game.get("steam_appid") or "").isdigit()
            and len(news_targets) < max_news_games
        ):
            news_targets.append((sub, game, link, title))

    # News requests are independent; run them in parallel so a slow Steam response
    # does not stretch a Render/NAS refresh into minutes.
    if news_targets:
        workers = max(1, min(6, len(news_targets)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(app_news, game["steam_appid"], 1, 300): (sub, game, link, title)
                for sub, game, link, title in news_targets
            }
            for future in as_completed(futures):
                sub, game, link, title = futures[future]
                try:
                    rows = future.result()
                    if not rows:
                        continue
                    newest = rows[0]
                    gid = newest.get("gid") or ""
                    old_gid = sub.get("last_news_gid") or ""
                    if not old_gid:
                        update_watch_last_news(sub["device_id"], game["game_key"], gid)
                    elif gid and gid != old_gid:
                        created += int(create_notification(
                            sub["device_id"], game["game_key"], "news", f"{title} 有新消息",
                            newest.get("title") or "Steam 發布了新的遊戲消息。",
                            newest.get("url") or link,
                            f"news:{game['game_key']}:{gid}",
                        ))
                        update_watch_last_news(sub["device_id"], game["game_key"], gid)
                except Exception:
                    pass

    return {"subscriptions": len(subscriptions), "created": created, "news_checked": len(news_targets)}
