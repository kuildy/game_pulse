from flask import Flask, jsonify, render_template, request
from config import effective_mode
from db import init_db, get_games, get_source_status
from services.aggregator import refresh_all

app = Flask(__name__)
init_db()

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
