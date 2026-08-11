import json
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
"""

def connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)

        # 舊版 SQLite 已存在時，CREATE TABLE IF NOT EXISTS 不會補新欄位。
        # 這裡做輕量 migration，Render/NAS 不需要手動刪資料庫。
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
        if "twitch_viewers" not in columns:
            conn.execute("ALTER TABLE games ADD COLUMN twitch_viewers INTEGER")
        if "twitch_channels" not in columns:
            conn.execute("ALTER TABLE games ADD COLUMN twitch_channels INTEGER")

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
                    g.get("igdb_id"), g.get("rating"), now
                )
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
            # 24H 趨勢只需要短期歷史；保留 8 天方便之後擴成 7D 趨勢。
            history_cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            conn.execute("DELETE FROM game_history WHERE recorded_at < ?", (history_cutoff,))

def _attach_24h_trend(conn, item):
    """把 24H PULSE 變化與 sparkline 點附加到 API 回傳資料。

    只有真的存在 24 小時以前的快照才會宣稱 24H delta；
    剛啟用 history 時會回傳 trend_ready=False，避免把 2 小時變化誤標成 24H。
    """
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
        LIMIT 48
        """,
        (item.get("game_key"), cutoff),
    ).fetchall()

    trend_rows = list(points)
    # 把 24 小時基準點也放進 sparkline，讓折線從真正的 24H 參考值開始。
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
            (section, limit)
        ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            for field in ("platforms_json", "genres_json", "stores_json", "sources_json"):
                item[field.replace("_json", "")] = json.loads(item.pop(field) or "[]")
            if section == "hot":
                item = _attach_24h_trend(conn, item)
            result.append(item)
    return result

def get_game_by_identifier(identifier):
    """可用 game_key 或 IGDB slug 取得遊戲；同款跨 section 時優先熱門榜。"""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM games
            WHERE game_key = ? OR slug = ?
            ORDER BY
              CASE WHEN game_key = ? THEN 0 ELSE 1 END,
              CASE section
                WHEN 'hot' THEN 0
                WHEN 'new' THEN 1
                WHEN 'upcoming' THEN 2
                ELSE 3
              END,
              updated_at DESC
            LIMIT 1
            """,
            (identifier, identifier, identifier),
        ).fetchone()

    if not row:
        return None

    item = dict(row)
    for field in ("platforms_json", "genres_json", "stores_json", "sources_json"):
        item[field.replace("_json", "")] = json.loads(item.pop(field) or "[]")
    if item.get("section") == "hot":
        with connect() as conn:
            item = _attach_24h_trend(conn, item)
    return item


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
            (source, status, message, now)
        )

def get_source_status():
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT source,status,message,updated_at FROM source_status ORDER BY source"
        ).fetchall()]
