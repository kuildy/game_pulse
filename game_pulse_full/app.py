from flask import Flask, jsonify, render_template, request
from config import effective_mode
from db import init_db, get_games, get_source_status
from services.aggregator import refresh_all

app = Flask(__name__)
init_db()

try:
    if effective_mode() == "live":
        refresh_all()
    elif not get_games("hot", 1):
        refresh_all()
except Exception as e:
    print("GAME PULSE update failed:", e)

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
