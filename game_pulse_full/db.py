import json
import sqlite3
from datetime import datetime, timezone
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
    steam_appid TEXT,
    steam_players INTEGER,
    igdb_id INTEGER,
    rating REAL,
    updated_at TEXT NOT NULL,
    UNIQUE(game_key, section)
);

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
                    trend_label, twitch_rank, twitch_game_id, steam_appid, steam_players,
                    igdb_id, rating, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    g.get("steam_appid"), g.get("steam_players"),
                    g.get("igdb_id"), g.get("rating"), now
                )
            )

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
