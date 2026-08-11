import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone

from config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_key TEXT NOT NULL,
    section TEXT NOT NULL,
    title TEXT NOT NULL,
    slug TEXT,
    summary TEXT,
    cover_url TEXT,
    release_date TEXT,
    platforms_json TEXT NOT NULL DEFAULT '[]',
    genres_json TEXT NOT NULL DEFAULT '[]',
    stores_json TEXT NOT NULL DEFAULT '[]',
    sources_json TEXT NOT NULL DEFAULT '[]',
    pulse_score REAL NOT NULL DEFAULT 0,
    trend_label TEXT,
    twitch_rank INTEGER,
    twitch_game_id TEXT,
    twitch_viewers INTEGER,
    twitch_channels INTEGER,
    steam_appid TEXT,
    steam_players INTEGER,
    igdb_id INTEGER,
    rating REAL,
    updated_at TEXT NOT NULL,
    UNIQUE(game_key, section)
);

CREATE TABLE IF NOT EXISTS game_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_key TEXT NOT NULL,
    title TEXT NOT NULL,
    pulse_score REAL NOT NULL,
    twitch_viewers INTEGER,
    steam_players INTEGER,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_game_history_key_time
ON game_history(game_key, recorded_at);

CREATE TABLE IF NOT EXISTS source_status (
    source TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    message TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watch_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    game_key TEXT NOT NULL,
    title TEXT NOT NULL,
    notify_release INTEGER NOT NULL DEFAULT 1,
    notify_pulse INTEGER NOT NULL DEFAULT 1,
    notify_steam INTEGER NOT NULL DEFAULT 1,
    notify_news INTEGER NOT NULL DEFAULT 1,
    last_news_gid TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(device_id, game_key)
);

CREATE INDEX IF NOT EXISTS idx_watch_device
ON watch_subscriptions(device_id);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    game_key TEXT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    link TEXT,
    dedupe_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT,
    UNIQUE(device_id, dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_notifications_device_time
ON notifications(device_id, created_at DESC);

CREATE TABLE IF NOT EXISTS twitch_overrides (
    twitch_game_id TEXT PRIMARY KEY,
    igdb_id TEXT NOT NULL,
    steam_appid TEXT,
    canonical_title TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)

        # Lightweight migration for users who already have the older DB.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
        if "twitch_viewers" not in columns:
            conn.execute("ALTER TABLE games ADD COLUMN twitch_viewers INTEGER")
        if "twitch_channels" not in columns:
            conn.execute("ALTER TABLE games ADD COLUMN twitch_channels INTEGER")

        # Keep the known CS -> CS2 correction as a database-backed default.
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO twitch_overrides(twitch_game_id, igdb_id, steam_appid, canonical_title, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(twitch_game_id) DO NOTHING
            """,
            ("32399", "242408", "730", "Counter-Strike 2", now),
        )


def _decode_game_row(row):
    if not row:
        return None
    item = dict(row)
    for field in ("platforms_json", "genres_json", "stores_json", "sources_json"):
        item[field.replace("_json", "")] = json.loads(item.pop(field) or "[]")
    return item


def replace_section(section, games):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        conn.execute("DELETE FROM games WHERE section = ?", (section,))
        for g in games:
            conn.execute(
                """
                INSERT INTO games (
                    game_key, section, title, slug, summary, cover_url, release_date,
                    platforms_json, genres_json, stores_json, sources_json, pulse_score,
                    trend_label, twitch_rank, twitch_game_id, twitch_viewers, twitch_channels,
                    steam_appid, steam_players, igdb_id, rating, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    g["game_key"], section, g["title"], g.get("slug"), g.get("summary"),
                    g.get("cover_url"), g.get("release_date"),
                    json.dumps(g.get("platforms", []), ensure_ascii=False),
                    json.dumps(g.get("genres", []), ensure_ascii=False),
                    json.dumps(g.get("stores", []), ensure_ascii=False),
                    json.dumps(g.get("sources", []), ensure_ascii=False),
                    float(g.get("pulse_score", 0)), g.get("trend_label"),
                    g.get("twitch_rank"), g.get("twitch_game_id"),
                    g.get("twitch_viewers"), g.get("twitch_channels"),
                    g.get("steam_appid"), g.get("steam_players"),
                    g.get("igdb_id"), g.get("rating"), now,
                ),
            )

            if section == "hot":
                conn.execute(
                    """
                    INSERT INTO game_history(
                        game_key, title, pulse_score, twitch_viewers, steam_players, recorded_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        g["game_key"],
                        g["title"],
                        float(g.get("pulse_score", 0)),
                        g.get("twitch_viewers"),
                        g.get("steam_players"),
                        now,
                    ),
                )

        if section == "hot":
            # 30D chart needs a little safety margin.
            cutoff = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
            conn.execute("DELETE FROM game_history WHERE recorded_at < ?", (cutoff,))


def _attach_24h_trend(conn, item):
    if item.get("section") != "hot":
        return item

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).isoformat()
    baseline = conn.execute(
        """
        SELECT pulse_score, twitch_viewers, steam_players, recorded_at
        FROM game_history
        WHERE game_key = ? AND recorded_at <= ?
        ORDER BY recorded_at DESC
        LIMIT 1
        """,
        (item.get("game_key"), cutoff),
    ).fetchone()

    points = conn.execute(
        """
        SELECT pulse_score, twitch_viewers, steam_players, recorded_at
        FROM game_history
        WHERE game_key = ? AND recorded_at >= ?
        ORDER BY recorded_at ASC
        LIMIT 64
        """,
        (item.get("game_key"), cutoff),
    ).fetchall()

    trend_rows = list(points)
    if baseline and (not trend_rows or trend_rows[0]["recorded_at"] != baseline["recorded_at"]):
        trend_rows.insert(0, baseline)

    item["trend_points"] = [
        {
            "time": row["recorded_at"],
            "pulse_score": round(float(row["pulse_score"] or 0), 1),
            "twitch_viewers": row["twitch_viewers"],
            "steam_players": row["steam_players"],
        }
        for row in trend_rows
    ]

    if not baseline:
        item["trend_ready"] = False
        item["trend_24h_delta"] = None
        item["trend_24h_percent"] = None
        item["trend_24h_direction"] = None
        return item

    current = float(item.get("pulse_score") or 0)
    previous = float(baseline["pulse_score"] or 0)
    delta = current - previous
    pct = (delta / previous * 100) if previous else None
    item["trend_ready"] = True
    item["trend_24h_delta"] = round(delta, 1)
    item["trend_24h_percent"] = round(pct, 1) if pct is not None else None
    item["trend_24h_direction"] = "up" if delta > 0.4 else "down" if delta < -0.4 else "flat"
    return item


def get_games(section, limit=50):
    order = "pulse_score DESC, id ASC" if section == "hot" else "release_date ASC, id ASC"
    if section == "new":
        order = "release_date DESC, id ASC"
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM games WHERE section = ? ORDER BY {order} LIMIT ?",
            (section, limit),
        ).fetchall()
        result = []
        for row in rows:
            item = _decode_game_row(row)
            if section == "hot":
                item = _attach_24h_trend(conn, item)
            result.append(item)
    return result


def get_game_by_identifier(identifier):
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM games
            WHERE game_key = ? OR slug = ?
            ORDER BY
              CASE WHEN game_key = ? THEN 0 ELSE 1 END,
              CASE section WHEN 'hot' THEN 0 WHEN 'new' THEN 1 WHEN 'upcoming' THEN 2 ELSE 3 END,
              updated_at DESC
            LIMIT 1
            """,
            (identifier, identifier, identifier),
        ).fetchone()
        if not row:
            return None
        item = _decode_game_row(row)
        if item.get("section") == "hot":
            item = _attach_24h_trend(conn, item)
        return item


def get_game_history(identifier, range_key="24h"):
    game = get_game_by_identifier(identifier)
    if not game:
        return None

    ranges = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    delta = ranges.get(range_key, ranges["24h"])
    since = (datetime.now(timezone.utc) - delta).isoformat()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT pulse_score, twitch_viewers, steam_players, recorded_at
            FROM game_history
            WHERE game_key = ? AND recorded_at >= ?
            ORDER BY recorded_at ASC
            LIMIT 320
            """,
            (game["game_key"], since),
        ).fetchall()

    points = [
        {
            "time": row["recorded_at"],
            "pulse_score": round(float(row["pulse_score"] or 0), 1),
            "twitch_viewers": row["twitch_viewers"],
            "steam_players": row["steam_players"],
        }
        for row in rows
    ]
    return {"game": {"game_key": game["game_key"], "title": game["title"]}, "range": range_key, "points": points}



def _radar_growth_component(previous, current, weight):
    """Log-scaled positive growth so small categories do not dominate the radar."""
    if previous is None or current is None:
        return 0.0
    previous = max(0.0, float(previous))
    current = max(0.0, float(current))
    if current <= previous:
        return 0.0
    # +1000 keeps very small categories from exploding to a 100-point signal.
    ratio = (current + 1000.0) / (previous + 1000.0)
    return max(0.0, min(float(weight), math.log2(ratio) * (float(weight) / 2.0)))


def _radar_percent(previous, current):
    if previous is None or current is None:
        return None
    previous = float(previous)
    current = float(current)
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100.0, 1)


def get_pulse_radar(limit=6, window_hours=12):
    """Rank early-rising games using recent PULSE, Twitch and Steam history.

    This is a heuristic early-signal score, not a probability forecast. It intentionally
    favors accelerating games that still have headroom rather than games already sitting
    at the very top of the chart.
    """
    limit = max(1, min(int(limit), 12))
    window_hours = max(3, min(int(window_hours), 24))
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()

    current_games = get_games("hot", 100)
    ranked = []
    pending = 0

    with connect() as conn:
        for game in current_games:
            rows = conn.execute(
                """
                SELECT pulse_score,twitch_viewers,steam_players,recorded_at
                FROM game_history
                WHERE game_key=? AND recorded_at >= ?
                ORDER BY recorded_at ASC
                LIMIT 96
                """,
                (game["game_key"], since),
            ).fetchall()

            if len(rows) < 2:
                pending += 1
                continue

            first = rows[0]
            last = rows[-1]
            try:
                first_dt = datetime.fromisoformat(first["recorded_at"].replace("Z", "+00:00"))
                last_dt = datetime.fromisoformat(last["recorded_at"].replace("Z", "+00:00"))
                span_hours = max(0.0, (last_dt - first_dt).total_seconds() / 3600.0)
            except Exception:
                span_hours = 0.0

            # Avoid calling two snapshots seconds apart a trend.
            if span_hours < 1.0:
                pending += 1
                continue

            pulse_before = float(first["pulse_score"] or 0)
            pulse_now = float(game.get("pulse_score") or last["pulse_score"] or 0)
            pulse_delta = round(pulse_now - pulse_before, 1)

            twitch_before = first["twitch_viewers"]
            twitch_now = game.get("twitch_viewers")
            steam_before = first["steam_players"]
            steam_now = game.get("steam_players")

            pulse_component = max(0.0, min(35.0, pulse_delta * 2.6))
            twitch_component = _radar_growth_component(twitch_before, twitch_now, 30.0)
            steam_component = _radar_growth_component(steam_before, steam_now, 25.0)

            # A game at PULSE 55 with fast acceleration is more interesting to RADAR than
            # a game already parked at PULSE 98. This is the "early discovery" headroom.
            headroom_component = max(0.0, min(10.0, (86.0 - pulse_now) / 3.2))
            multi_signal_bonus = 5.0 if twitch_component >= 6 and steam_component >= 5 else 0.0

            radar_score = pulse_component + twitch_component + steam_component + headroom_component + multi_signal_bonus
            if pulse_now >= 92:
                radar_score *= 0.55
            elif pulse_now >= 84:
                radar_score *= 0.78
            radar_score = round(max(0.0, min(100.0, radar_score)), 1)

            if radar_score < 12:
                continue

            twitch_pct = _radar_percent(twitch_before, twitch_now)
            steam_pct = _radar_percent(steam_before, steam_now)

            if radar_score >= 75:
                level = "BREAKOUT"
                level_zh = "突破預警"
            elif radar_score >= 55:
                level = "HEATING_UP"
                level_zh = "快速升溫"
            elif radar_score >= 35:
                level = "RISING"
                level_zh = "持續上升"
            else:
                level = "WATCH"
                level_zh = "值得觀察"

            signal_scores = [
                (twitch_component, "Twitch 觀看正在加速"),
                (steam_component, "Steam 玩家正在增加"),
                (pulse_component, "PULSE 熱度快速上升"),
            ]
            signal_scores.sort(reverse=True, key=lambda x: x[0])
            reason = signal_scores[0][1] if signal_scores and signal_scores[0][0] > 0 else "多來源訊號開始升溫"
            if twitch_component >= 6 and steam_component >= 5:
                reason = "Twitch 與 Steam 同步升溫"

            ranked.append({
                "game_key": game["game_key"],
                "title": game["title"],
                "slug": game.get("slug") or "",
                "cover_url": game.get("cover_url") or "",
                "pulse_score": round(pulse_now, 1),
                "radar_score": radar_score,
                "level": level,
                "level_zh": level_zh,
                "reason": reason,
                "window_hours": round(span_hours, 1),
                "pulse_delta": pulse_delta,
                "twitch_viewers": twitch_now,
                "twitch_growth_percent": twitch_pct,
                "steam_players": steam_now,
                "steam_growth_percent": steam_pct,
                "samples": len(rows),
            })

    ranked.sort(key=lambda x: (x["radar_score"], x["pulse_delta"]), reverse=True)
    return {
        "window_hours": window_hours,
        "items": ranked[:limit],
        "pending_games": pending,
        "method": "early_momentum_v1",
        "disclaimer": "RADAR 是依近期多來源成長訊號計算的早期預警分數，不代表未來熱門機率。",
    }


def get_release_calendar(month, platform="all"):
    try:
        year, mon = [int(x) for x in month.split("-", 1)]
        start = datetime(year, mon, 1, tzinfo=timezone.utc)
    except Exception:
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    if start.month == 12:
        end = datetime(start.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(start.year, start.month + 1, 1, tzinfo=timezone.utc)

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM games
            WHERE section IN ('new','upcoming')
              AND release_date >= ? AND release_date < ?
            ORDER BY release_date ASC, title ASC
            """,
            (start.date().isoformat(), end.date().isoformat()),
        ).fetchall()

    platform = (platform or "all").strip().lower()
    result = []
    seen = set()
    for row in rows:
        item = _decode_game_row(row)
        if item["game_key"] in seen:
            continue
        seen.add(item["game_key"])
        text = " ".join(item.get("platforms") or []).lower()
        if platform != "all":
            aliases = {
                "pc": ("pc", "windows", "linux", "mac"),
                "playstation": ("playstation", "ps5", "ps4"),
                "xbox": ("xbox",),
                "nintendo": ("nintendo", "switch"),
            }
            needles = aliases.get(platform, (platform,))
            if not any(n in text for n in needles):
                continue
        result.append(item)
    return result


def set_source_status(source, status, message=""):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO source_status(source,status,message,updated_at)
            VALUES(?,?,?,?)
            ON CONFLICT(source) DO UPDATE SET
              status=excluded.status,
              message=excluded.message,
              updated_at=excluded.updated_at
            """,
            (source, status, message, now),
        )


def get_source_status():
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT source,status,message,updated_at FROM source_status ORDER BY source"
        ).fetchall()]


# ---- Watch / notification center -------------------------------------------------

def upsert_watch_subscription(device_id, game_key, title, prefs):
    now = datetime.now(timezone.utc).isoformat()
    values = (
        1 if prefs.get("notify_release", True) else 0,
        1 if prefs.get("notify_pulse", True) else 0,
        1 if prefs.get("notify_steam", True) else 0,
        1 if prefs.get("notify_news", True) else 0,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO watch_subscriptions(
              device_id,game_key,title,notify_release,notify_pulse,notify_steam,notify_news,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(device_id,game_key) DO UPDATE SET
              title=excluded.title,
              notify_release=excluded.notify_release,
              notify_pulse=excluded.notify_pulse,
              notify_steam=excluded.notify_steam,
              notify_news=excluded.notify_news,
              updated_at=excluded.updated_at
            """,
            (device_id, game_key, title, *values, now, now),
        )


def delete_watch_subscription(device_id, game_key):
    with connect() as conn:
        conn.execute("DELETE FROM watch_subscriptions WHERE device_id=? AND game_key=?", (device_id, game_key))


def get_watch_subscription(device_id, game_key):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM watch_subscriptions WHERE device_id=? AND game_key=?",
            (device_id, game_key),
        ).fetchone()
    return dict(row) if row else None


def list_watch_subscriptions(device_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM watch_subscriptions WHERE device_id=? ORDER BY updated_at DESC",
            (device_id,),
        ).fetchall()
    result = []
    for row in rows:
        sub = dict(row)
        game = get_game_by_identifier(sub["game_key"])
        sub["game"] = game
        result.append(sub)
    return result


def list_all_watch_subscriptions():
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM watch_subscriptions ORDER BY id ASC").fetchall()]


def update_watch_last_news(device_id, game_key, gid):
    with connect() as conn:
        conn.execute(
            "UPDATE watch_subscriptions SET last_news_gid=?, updated_at=? WHERE device_id=? AND game_key=?",
            (str(gid or ""), datetime.now(timezone.utc).isoformat(), device_id, game_key),
        )


def create_notification(device_id, game_key, kind, title, message, link, dedupe_key):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO notifications(
              device_id,game_key,kind,title,message,link,dedupe_key,created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (device_id, game_key, kind, title, message, link, dedupe_key, now),
        )
        return cur.rowcount > 0


def list_notifications(device_id, limit=50, unread_only=False):
    clause = "AND read_at IS NULL" if unread_only else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM notifications
            WHERE device_id=? {clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (device_id, max(1, min(int(limit), 100))),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_notification_read(device_id, notification_id=None, all_items=False):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        if all_items:
            conn.execute("UPDATE notifications SET read_at=? WHERE device_id=? AND read_at IS NULL", (now, device_id))
        elif notification_id is not None:
            conn.execute(
                "UPDATE notifications SET read_at=? WHERE device_id=? AND id=?",
                (now, device_id, int(notification_id)),
            )


def get_current_game_for_watch(game_key):
    return get_game_by_identifier(game_key)


def get_history_baseline(game_key, hours=24):
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT pulse_score,twitch_viewers,steam_players,recorded_at
            FROM game_history
            WHERE game_key=? AND recorded_at <= ?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (game_key, cutoff),
        ).fetchone()
    return dict(row) if row else None


# ---- Admin ----------------------------------------------------------------------

def list_twitch_overrides():
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT twitch_game_id,igdb_id,steam_appid,canonical_title,updated_at FROM twitch_overrides ORDER BY canonical_title"
        ).fetchall()]


def get_twitch_override(twitch_game_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM twitch_overrides WHERE twitch_game_id=?",
            (str(twitch_game_id or ""),),
        ).fetchone()
    return dict(row) if row else None


def upsert_twitch_override(twitch_game_id, igdb_id, steam_appid, canonical_title):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO twitch_overrides(twitch_game_id,igdb_id,steam_appid,canonical_title,updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(twitch_game_id) DO UPDATE SET
              igdb_id=excluded.igdb_id,
              steam_appid=excluded.steam_appid,
              canonical_title=excluded.canonical_title,
              updated_at=excluded.updated_at
            """,
            (str(twitch_game_id), str(igdb_id), str(steam_appid or ""), canonical_title.strip(), now),
        )


def delete_twitch_override(twitch_game_id):
    with connect() as conn:
        conn.execute("DELETE FROM twitch_overrides WHERE twitch_game_id=?", (str(twitch_game_id),))


def get_admin_stats():
    with connect() as conn:
        section_rows = conn.execute(
            "SELECT section,COUNT(*) AS count,MAX(updated_at) AS updated_at FROM games GROUP BY section"
        ).fetchall()
        history = conn.execute(
            "SELECT COUNT(*) AS count,MIN(recorded_at) AS oldest,MAX(recorded_at) AS newest FROM game_history"
        ).fetchone()
        watch_count = conn.execute("SELECT COUNT(*) AS count FROM watch_subscriptions").fetchone()["count"]
        notification_count = conn.execute("SELECT COUNT(*) AS count FROM notifications").fetchone()["count"]
        unread_count = conn.execute("SELECT COUNT(*) AS count FROM notifications WHERE read_at IS NULL").fetchone()["count"]
        source_problem_count = conn.execute(
            "SELECT COUNT(*) AS count FROM source_status WHERE status IN ('error','partial')"
        ).fetchone()["count"]

    return {
        "sections": {r["section"]: {"count": r["count"], "updated_at": r["updated_at"]} for r in section_rows},
        "history": dict(history) if history else {},
        "watch_count": watch_count,
        "notification_count": notification_count,
        "unread_count": unread_count,
        "source_problem_count": source_problem_count,
    }
