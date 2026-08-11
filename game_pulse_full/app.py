import time

from flask import Flask, abort, jsonify, render_template, request

from config import effective_mode
from db import get_game_by_identifier, get_games, get_source_status, init_db
from services.aggregator import refresh_all
from services.igdb import IGDBClient

app = Flask(__name__)
init_db()

_DETAIL_CACHE = {}
_DETAIL_CACHE_TTL = 1800

# 第一次啟動若資料庫為空，自動建立 Demo / Live 資料
if not get_games("hot", 1):
    try:
        refresh_all()
    except Exception:
        # 即使網路/API 暫時失敗，網站仍可啟動；使用者可稍後執行更新程式
        pass


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/game/<path:identifier>")
def game_detail(identifier):
    game = get_game_by_identifier(identifier)
    if not game:
        abort(404)

    detail = {}
    detail_error = None

    # 詳細頁先使用 SQLite 既有資料；有 IGDB ID 時再補充更完整的 metadata。
    if game.get("igdb_id") and effective_mode() == "live":
        try:
            cache_key = str(game["igdb_id"])
            cached = _DETAIL_CACHE.get(cache_key)
            if cached and time.time() - cached["at"] < _DETAIL_CACHE_TTL:
                detail = cached["data"]
            else:
                detail = IGDBClient().game_details(game["igdb_id"]) or {}
                _DETAIL_CACHE[cache_key] = {"at": time.time(), "data": detail}
        except Exception as exc:
            # 外部 API 暫時失敗時仍顯示資料庫中的遊戲資訊，不讓整頁失敗。
            detail_error = str(exc)[:180]

    # 詳細資料優先；IGDB 沒回傳的欄位則沿用資料庫內容。
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
    return jsonify({
        "section": section,
        "mode": effective_mode(),
        "games": get_games(section, limit),
    })


@app.get("/api/status")
def api_status():
    return jsonify({
        "mode": effective_mode(),
        "sources": get_source_status(),
    })


@app.get("/health")
def health():
    return jsonify({"ok": True, "mode": effective_mode()})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
