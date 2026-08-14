import os
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import effective_mode
from db import (
    delete_twitch_override,
    delete_watch_subscription,
    get_admin_stats,
    get_game_by_identifier,
    get_game_history,
    get_games,
    get_pulse_radar,
    get_pulse_why,
    get_release_calendar,
    get_source_status,
    get_watch_subscription,
    init_db,
    list_notifications,
    list_twitch_overrides,
    list_watch_subscriptions,
    mark_notification_read,
    mark_live_sources_refreshing,
    set_source_status,
    upsert_twitch_override,
    upsert_watch_subscription,
)
from services.aggregator import refresh_all
try:
    from services.four_gamers import latest_news as four_gamers_latest_news
    from services.four_gamers import related_news as four_gamers_related_news
except ModuleNotFoundError as exc:
    # GitHub's browser uploader can flatten a newly added service into the
    # project root. Keep that deployment working while the canonical package
    # location remains services/four_gamers.py.
    if exc.name != "services.four_gamers":
        raise
    from four_gamers import latest_news as four_gamers_latest_news
    from four_gamers import related_news as four_gamers_related_news
from services.igdb import IGDBClient
from services.steam import app_news, app_reviews

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "").strip() or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.getenv("RENDER")),
)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
_DETAIL_CACHE = {}
_DETAIL_CACHE_TTL = 1800
_NEWS_CACHE = {}
_NEWS_CACHE_TTL = 900
_REVIEWS_CACHE = {}
_REVIEWS_CACHE_TTL = 900
_DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
_REFRESH_LOCK = threading.Lock()


def _start_background_refresh():
    """Start one non-blocking refresh per web process.

    External API aggregation can exceed a web worker timeout on a cold database,
    so it must never run synchronously while Gunicorn is booting or serving the
    admin refresh request.
    """
    if not _REFRESH_LOCK.acquire(blocking=False):
        return False

    def run():
        try:
            if effective_mode() == "live":
                mark_live_sources_refreshing()
            set_source_status("Updater", "refreshing", "背景資料更新進行中")
            refresh_all()
            set_source_status("Updater", "ok", "背景資料更新完成")
        except Exception as exc:
            set_source_status("Updater", "error", f"背景更新失敗：{str(exc)[:180]}")
            print("WAVESIG background refresh failed:", exc, flush=True)
        finally:
            _REFRESH_LOCK.release()

    threading.Thread(target=run, name="wavesig-refresh", daemon=True).start()
    return True


init_db()

# Let Gunicorn become healthy immediately; live API work continues in the
# background. Demo refresh is local-only and safe to complete synchronously.
if effective_mode() == "live":
    _start_background_refresh()
elif not get_games("hot", 1):
    try:
        refresh_all()
    except Exception as exc:
        print("WAVESIG demo startup refresh failed:", exc, flush=True)


def _safe_device_id(value):
    value = (value or "").strip()
    if not _DEVICE_RE.fullmatch(value):
        abort(400, "invalid device id")
    return value


def _admin_logged_in():
    return bool(ADMIN_TOKEN and session.get("admin_ok") is True)


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not _admin_logged_in():
            return redirect(url_for("admin_page"))
        return fn(*args, **kwargs)
    return wrapped


def _detail_for_game(game):
    """Read IGDB detail metadata with the same 30-minute cache used by detail pages."""
    if not game or not game.get("igdb_id") or effective_mode() != "live":
        return {}
    cache_key = str(game["igdb_id"])
    cached = _DETAIL_CACHE.get(cache_key)
    if cached and time.time() - cached["at"] < _DETAIL_CACHE_TTL:
        return cached["data"]
    detail = IGDBClient().game_details(game["igdb_id"]) or {}
    _DETAIL_CACHE[cache_key] = {"at": time.time(), "data": detail}
    return detail




def _steam_reviews_cached(appid, review_type="all", limit=10):
    appid = str(appid or "").strip()
    if not appid.isdigit():
        return {"reviews": [], "summary": {}, "language": ""}

    review_type = review_type if review_type in {"all", "positive", "negative"} else "all"
    limit = max(1, min(int(limit), 30))
    cache_key = f"{appid}:{review_type}:{limit}"
    cached = _REVIEWS_CACHE.get(cache_key)
    if cached and time.time() - cached["at"] < _REVIEWS_CACHE_TTL:
        return cached["data"]

    # Prefer Traditional Chinese, then English, then any language so the section
    # remains useful even for games with a small Chinese review pool.
    data = {"reviews": [], "summary": {}, "language": ""}
    for language in ("tchinese", "english", "all"):
        data = app_reviews(
            appid,
            count=max(limit, 8),
            language=language,
            review_type=review_type,
            max_chars=360,
        )
        if data.get("reviews"):
            break

    data["reviews"] = (data.get("reviews") or [])[:limit]
    _REVIEWS_CACHE[cache_key] = {"at": time.time(), "data": data}
    return data




def _review_quality_score(review):
    """Rank recent Steam reviews by how useful they are to a reader."""
    content = str(review.get("content") or "").strip()
    meaningful_chars = re.findall(r"[\w\u3400-\u9fff]", content, flags=re.UNICODE)
    length_score = min(len(meaningful_chars), 220) / 22.0

    votes_up = max(0, int(review.get("votes_up") or 0))
    helpful_score = min(votes_up, 50) * 0.18

    playtime = review.get("playtime_hours")
    try:
        playtime = float(playtime or 0)
    except (TypeError, ValueError):
        playtime = 0
    playtime_score = min(playtime, 100) / 50.0

    return length_score + helpful_score + playtime_score


def _is_meaningful_review(review):
    """Reject obvious low-information / spam-like review snippets."""
    content = str(review.get("content") or "").strip()
    if not content:
        return False

    without_urls = re.sub(r"https?://\S+|www\.\S+", " ", content, flags=re.I)
    meaningful = re.findall(r"[\w\u3400-\u9fff]", without_urls, flags=re.UNICODE)
    if len(meaningful) < 18:
        return False

    normalized = "".join(meaningful).lower()
    if len(set(normalized)) < 6:
        return False

    return True


def _best_recent_review(appid, review_type):
    """Return one useful recent positive or negative review."""
    data = _steam_reviews_cached(appid, review_type=review_type, limit=30)
    candidates = [
        review for review in (data.get("reviews") or [])
        if _is_meaningful_review(review)
    ]
    if not candidates:
        return None, data

    best = max(candidates, key=_review_quality_score)
    return dict(best), data

def _publisher_fallback(game, detail):
    publisher_details = detail.get("publisher_details") or []
    publishers = detail.get("publishers") or []
    links = []
    seen = set()

    for item in publisher_details:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        url = (item.get("website") or "").strip()
        key = (name.lower(), url.lower())
        if name and key not in seen:
            links.append({"name": name, "url": url, "kind": "publisher"})
            seen.add(key)

    # If IGDB knows the publisher name but not its company website, keep the name visible.
    known_names = {x.get("name", "").lower() for x in links}
    for name in publishers:
        name = (name or "").strip()
        if name and name.lower() not in known_names:
            links.append({"name": name, "url": "", "kind": "publisher"})
            known_names.add(name.lower())

    # Last-resort official game site from WAVESIG store metadata.
    official_url = ""
    for store in game.get("stores") or []:
        if isinstance(store, dict) and store.get("kind") == "official" and store.get("url"):
            official_url = store["url"]
            break

    return {
        "publishers": links,
        "official_game_url": official_url,
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/calendar")
def release_calendar_page():
    return render_template("calendar.html", mode=effective_mode())


@app.get("/notifications")
def notifications_page():
    return render_template("notifications.html", mode=effective_mode())


@app.get("/game/<path:identifier>")
def game_detail(identifier):
    game = get_game_by_identifier(identifier)
    if not game:
        abort(404)

    detail = {}
    detail_error = None
    try:
        detail = _detail_for_game(game)
    except Exception as exc:
        detail_error = str(exc)[:180]

    view_game = dict(game)
    for key, value in detail.items():
        if value not in (None, "", [], {}):
            view_game[key] = value

    return render_template(
        "game_detail.html",
        game=view_game,
        detail_error=detail_error,
        mode=effective_mode(),
    )


@app.get("/api/games")
def api_games():
    section = request.args.get("section", "hot")
    if section not in {"hot", "new", "upcoming"}:
        section = "hot"
    try:
        limit = max(1, min(100, int(request.args.get("limit", "50"))))
    except ValueError:
        limit = 50
    return jsonify({"section": section, "mode": effective_mode(), "games": get_games(section, limit)})


@app.get("/api/radar")
def api_radar():
    try:
        limit = max(1, min(12, int(request.args.get("limit", "6"))))
    except ValueError:
        limit = 6
    try:
        window = max(3, min(24, int(request.args.get("window", "12"))))
    except ValueError:
        window = 12
    payload = get_pulse_radar(limit=limit, window_hours=window)
    payload["mode"] = effective_mode()
    return jsonify(payload)


@app.get("/api/why")
def api_why():
    try:
        limit = max(1, min(12, int(request.args.get("limit", "6"))))
    except ValueError:
        limit = 6
    try:
        window = max(3, min(72, int(request.args.get("window", "24"))))
    except ValueError:
        window = 24
    payload = get_pulse_why(limit=limit, window_hours=window)
    payload["mode"] = effective_mode()
    return jsonify(payload)


@app.get("/api/game/<path:identifier>/history")
def api_game_history(identifier):
    range_key = request.args.get("range", "24h")
    if range_key not in {"24h", "7d", "30d"}:
        range_key = "24h"
    payload = get_game_history(identifier, range_key)
    if not payload:
        abort(404)
    return jsonify(payload)


@app.get("/api/game/<path:identifier>/news")
def api_game_news(identifier):
    game = get_game_by_identifier(identifier)
    if not game:
        abort(404)

    detail = {}
    detail_error = None
    try:
        detail = _detail_for_game(game)
    except Exception as exc:
        detail_error = str(exc)[:180]

    fallback = _publisher_fallback(game, detail)
    appid = str(game.get("steam_appid") or "").strip()
    four_gamers_rows = []
    four_gamers_error = None
    try:
        four_gamers_rows = four_gamers_related_news(game.get("title") or "", limit=4)
    except Exception as exc:
        four_gamers_error = str(exc)[:180]

    steam_rows = []
    steam_error = None

    if appid.isdigit():
        cache_key = appid
        cached = _NEWS_CACHE.get(cache_key)
        try:
            if cached and time.time() - cached["at"] < _NEWS_CACHE_TTL:
                steam_rows = cached["data"]
            else:
                steam_rows = app_news(appid, count=8, maxlength=900)
                _NEWS_CACHE[cache_key] = {"at": time.time(), "data": steam_rows}
        except Exception as exc:
            steam_error = str(exc)[:180]

    rows = four_gamers_rows + steam_rows
    rows.sort(key=lambda row: row.get("published_at") or "", reverse=True)
    rows = rows[:8]

    if rows:
        source_names = []
        if four_gamers_rows:
            source_names.append("4Gamers")
        if steam_rows:
            source_names.append("Steam News")
        return jsonify({
            "game_key": game["game_key"],
            "source": " / ".join(source_names),
            "news": rows,
            "publishers": fallback["publishers"],
            "official_game_url": fallback["official_game_url"],
        })

    # Steam has no usable post (or the game is not on Steam): surface publisher/official links
    # instead of leaving the section as an engineering-style empty state.
    return jsonify({
        "game_key": game["game_key"],
        "source": "官方來源",
        "news": [],
        "publishers": fallback["publishers"],
        "official_game_url": fallback["official_game_url"],
        "steam_error": steam_error,
        "four_gamers_error": four_gamers_error,
        "detail_error": detail_error,
    })


@app.get("/api/news/4gamers")
def api_four_gamers_news():
    try:
        limit = max(1, min(12, int(request.args.get("limit", "8"))))
    except ValueError:
        limit = 8
    try:
        rows = four_gamers_latest_news(limit=limit)
    except Exception:
        rows = []
    response = jsonify({
        "source": "4Gamers RSS",
        "news": rows,
        "status": "ok" if rows else "unavailable",
    })
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@app.get("/api/game/<path:identifier>/reviews")
def api_game_reviews(identifier):
    game = get_game_by_identifier(identifier)
    if not game:
        abort(404)

    review_type = request.args.get("type", "all")
    if review_type not in {"all", "positive", "negative"}:
        review_type = "all"

    appid = str(game.get("steam_appid") or "").strip()
    if not appid.isdigit():
        return jsonify({
            "game_key": game["game_key"],
            "title": game["title"],
            "source": "Steam User Reviews",
            "available": False,
            "reviews": [],
            "summary": {},
            "message": "這款遊戲目前沒有可用的 Steam AppID。",
        })

    try:
        selected = []
        summary = {}
        languages = []

        wanted_types = ["positive", "negative"] if review_type == "all" else [review_type]
        for sentiment in wanted_types:
            review, data = _best_recent_review(appid, sentiment)
            if not summary:
                summary = data.get("summary") or {}
            language = data.get("language")
            if language:
                languages.append(language)
            if review:
                review["selected_sentiment"] = sentiment
                selected.append(review)

        selected.sort(key=lambda item: 0 if item.get("voted_up") else 1)

        return jsonify({
            "game_key": game["game_key"],
            "title": game["title"],
            "steam_appid": appid,
            "source": "Steam User Reviews",
            "available": bool(selected),
            "language": ", ".join(dict.fromkeys(languages)),
            "reviews": selected,
            "summary": summary,
            "selection": "one_meaningful_positive_and_negative",
            "message": (
                "顯示近期評論中各一則較有內容的推薦與不推薦評論。"
                if review_type == "all" else
                "顯示近期評論中一則較有內容的代表評論。"
            ),
        })
    except Exception as exc:
        return jsonify({
            "game_key": game["game_key"],
            "title": game["title"],
            "source": "Steam User Reviews",
            "available": False,
            "reviews": [],
            "summary": {},
            "error": str(exc)[:160],
        }), 502


@app.get("/api/reviews/recent")
def api_recent_reviews():
    try:
        limit = max(2, min(10, int(request.args.get("limit", "6"))))
    except ValueError:
        limit = 6

    game_limit = max(1, (limit + 1) // 2)
    candidates = []
    for game in get_games("hot", 16):
        appid = str(game.get("steam_appid") or "").strip()
        if appid.isdigit():
            candidates.append(game)
        if len(candidates) >= game_limit + 2:
            break

    if not candidates:
        return jsonify({"source": "Steam User Reviews", "reviews": []})

    rows = []
    workers = max(1, min(4, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for game in candidates:
            appid = game.get("steam_appid")
            futures[pool.submit(_best_recent_review, appid, "positive")] = (game, "positive")
            futures[pool.submit(_best_recent_review, appid, "negative")] = (game, "negative")

        grouped = {}
        for future in as_completed(futures):
            game, sentiment = futures[future]
            try:
                review, _data = future.result()
            except Exception:
                continue
            if not review:
                continue
            game_key = game.get("game_key")
            review.update({
                "game_key": game_key,
                "title": game.get("title"),
                "slug": game.get("slug"),
                "cover_url": game.get("cover_url"),
                "pulse_score": game.get("pulse_score"),
                "steam_appid": game.get("steam_appid"),
                "selected_sentiment": sentiment,
            })
            grouped.setdefault(game_key, {})[sentiment] = review

    for game in candidates:
        pair = grouped.get(game.get("game_key"), {})
        positive = pair.get("positive")
        negative = pair.get("negative")
        if positive and negative:
            rows.extend([positive, negative])
            if len(rows) >= limit:
                break

    if len(rows) < limit:
        seen_ids = {item.get("recommendationid") for item in rows}
        leftovers = []
        for game in candidates:
            pair = grouped.get(game.get("game_key"), {})
            for sentiment in ("positive", "negative"):
                review = pair.get(sentiment)
                if review and review.get("recommendationid") not in seen_ids:
                    leftovers.append(review)
        leftovers.sort(key=lambda item: int(item.get("timestamp_created") or 0), reverse=True)
        rows.extend(leftovers[: max(0, limit - len(rows))])

    return jsonify({
        "source": "Steam User Reviews",
        "reviews": rows[:limit],
        "selection": "paired_meaningful_positive_negative",
        "disclaimer": "每款遊戲優先顯示近期評論中各一則較有內容的好評與負評；內容來自 Steam 使用者。",
    })


@app.get("/api/calendar")
def api_calendar():
    month = request.args.get("month", "")
    platform = request.args.get("platform", "all")
    rows = get_release_calendar(month, platform)
    return jsonify({"month": month, "platform": platform, "games": rows})


@app.get("/api/status")
def api_status():
    return jsonify({"mode": effective_mode(), "sources": get_source_status()})


# ---- Anonymous watch + notification API ----------------------------------------
@app.get("/api/watch/<path:identifier>")
def api_watch_status(identifier):
    device_id = _safe_device_id(request.args.get("device_id"))
    game = get_game_by_identifier(identifier)
    if not game:
        abort(404)
    sub = get_watch_subscription(device_id, game["game_key"])
    return jsonify({"watching": bool(sub), "subscription": sub})


@app.post("/api/watch/<path:identifier>")
def api_watch_upsert(identifier):
    payload = request.get_json(silent=True) or {}
    device_id = _safe_device_id(payload.get("device_id"))
    game = get_game_by_identifier(identifier)
    if not game:
        abort(404)
    prefs = {
        "notify_release": payload.get("notify_release", True),
        "notify_pulse": payload.get("notify_pulse", True),
        "notify_steam": payload.get("notify_steam", True),
        "notify_news": payload.get("notify_news", True),
    }
    upsert_watch_subscription(device_id, game["game_key"], game["title"], prefs)
    return jsonify({"ok": True, "watching": True})


@app.delete("/api/watch/<path:identifier>")
def api_watch_delete(identifier):
    payload = request.get_json(silent=True) or {}
    device_id = _safe_device_id(payload.get("device_id") or request.args.get("device_id"))
    game = get_game_by_identifier(identifier)
    if not game:
        abort(404)
    delete_watch_subscription(device_id, game["game_key"])
    return jsonify({"ok": True, "watching": False})


@app.get("/api/watchlist")
def api_watchlist():
    device_id = _safe_device_id(request.args.get("device_id"))
    return jsonify({"items": list_watch_subscriptions(device_id)})


@app.get("/api/notifications")
def api_notifications():
    device_id = _safe_device_id(request.args.get("device_id"))
    unread_only = request.args.get("unread", "0") == "1"
    rows = list_notifications(device_id, limit=request.args.get("limit", 50), unread_only=unread_only)
    return jsonify({"notifications": rows, "unread": sum(1 for row in rows if not row.get("read_at"))})


@app.post("/api/notifications/read")
def api_notifications_read():
    payload = request.get_json(silent=True) or {}
    device_id = _safe_device_id(payload.get("device_id"))
    if payload.get("all"):
        mark_notification_read(device_id, all_items=True)
    elif payload.get("id") is not None:
        mark_notification_read(device_id, notification_id=payload["id"])
    else:
        abort(400)
    return jsonify({"ok": True})


# ---- Admin ----------------------------------------------------------------------
@app.route("/admin", methods=["GET"])
def admin_page():
    if not ADMIN_TOKEN:
        return render_template("admin.html", configured=False, authenticated=False)
    if not _admin_logged_in():
        return render_template("admin.html", configured=True, authenticated=False)
    return render_template(
        "admin.html",
        configured=True,
        authenticated=True,
        stats=get_admin_stats(),
        sources=get_source_status(),
        overrides=list_twitch_overrides(),
        mode=effective_mode(),
    )


@app.post("/admin/login")
def admin_login():
    if not ADMIN_TOKEN:
        abort(503)
    token = (request.form.get("token") or "").strip()
    if secrets.compare_digest(token, ADMIN_TOKEN):
        session["admin_ok"] = True
        return redirect(url_for("admin_page"))
    return render_template("admin.html", configured=True, authenticated=False, login_error="管理密碼錯誤"), 401


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_page"))


@app.post("/admin/refresh")
@admin_required
def admin_refresh():
    started = _start_background_refresh()
    session["admin_flash"] = "背景更新已開始" if started else "資料更新已在進行中"
    return redirect(url_for("admin_page"))


@app.post("/admin/overrides")
@admin_required
def admin_override_save():
    twitch_game_id = (request.form.get("twitch_game_id") or "").strip()
    igdb_id = (request.form.get("igdb_id") or "").strip()
    steam_appid = (request.form.get("steam_appid") or "").strip()
    canonical_title = (request.form.get("canonical_title") or "").strip()
    if not twitch_game_id.isdigit() or not igdb_id.isdigit() or not canonical_title:
        abort(400, "Twitch ID / IGDB ID / 名稱格式不正確")
    if steam_appid and not steam_appid.isdigit():
        abort(400, "Steam AppID 格式不正確")
    upsert_twitch_override(twitch_game_id, igdb_id, steam_appid, canonical_title)
    return redirect(url_for("admin_page"))


@app.post("/admin/overrides/<twitch_game_id>/delete")
@admin_required
def admin_override_delete(twitch_game_id):
    delete_twitch_override(twitch_game_id)
    return redirect(url_for("admin_page"))


@app.get("/health")
def health():
    return jsonify({"ok": True, "mode": effective_mode()})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
