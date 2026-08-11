import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

from config import (
    HOT_LIMIT,
    RECENT_LIMIT,
    UPCOMING_LIMIT,
    STEAM_WEB_API_KEY,
    effective_mode
)
from db import replace_section, set_source_status
from services.igdb import IGDBClient
from services.twitch import TwitchClient
from services.steam import current_players

def norm_title(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if ch.isalnum() or ch.isspace())
    return re.sub(r"\s+", " ", value).strip().lower()


NON_GAME_TWITCH_CATEGORIES = {
    "irl",
    "slots",
    "sports",
    "just chatting",
    "music",
    "talk shows & podcasts",
    "pools, hot tubs, and beaches",
    "art",
    "food & drink",
    "travel & outdoors",
    "special events",
}


def is_non_game_twitch_category(title):
    return norm_title(title) in {
        norm_title(x) for x in NON_GAME_TWITCH_CATEGORIES
    }

def best_igdb_match(title, candidates):
    """從 IGDB 搜尋候選中挑出可信度足夠的名稱配對。"""
    target = norm_title(title)
    if not target or not candidates:
        return None, 0.0

    best = None
    best_score = 0.0

    for candidate in candidates:
        candidate_title = norm_title(candidate.get("title"))
        if not candidate_title:
            continue

        if candidate_title == target:
            return candidate, 1.0

        score = SequenceMatcher(None, target, candidate_title).ratio()

        # 對「主標題 + 副標題/新版名稱」稍微放寬，但不直接視為完全相同。
        shorter, longer = sorted((target, candidate_title), key=len)
        if shorter in longer and len(shorter) >= 5:
            coverage = len(shorter) / max(len(longer), 1)
            score = max(score, 0.72 + 0.20 * coverage)

        if score > best_score:
            best = candidate
            best_score = score

    # 短標題較容易誤配，因此門檻提高。
    threshold = 0.84 if len(target) < 8 else 0.76
    if best_score >= threshold:
        return best, best_score
    return None, best_score

def fallback_stores(title, platforms):
    q = quote_plus(title)
    platforms_text = " ".join(platforms).lower()
    stores = [
        {"name": "Steam", "kind": "steam", "url": f"https://store.steampowered.com/search/?term={q}", "direct": False},
        {"name": "Epic Games", "kind": "epic", "url": "https://store.epicgames.com/?lang=zh-Hant", "direct": False},
        {"name": "GOG", "kind": "gog", "url": "https://www.gog.com/en/games", "direct": False},
    ]
    if any(x in platforms_text for x in ["playstation", "ps5", "ps4"]):
        stores.append({"name": "PlayStation", "kind": "playstation", "url": "https://store.playstation.com/zh-hant-tw/", "direct": False})
    if "xbox" in platforms_text:
        stores.append({"name": "Xbox", "kind": "xbox", "url": "https://www.xbox.com/zh-TW/games/store", "direct": False})
    if "switch" in platforms_text or "nintendo" in platforms_text:
        stores.append({"name": "Nintendo", "kind": "nintendo", "url": "https://ec.nintendo.com/TW/zh/", "direct": False})
    return stores

def build_stores(game):
    direct = game.get("direct_links", {})
    pretty = {
        "official": "官方網站",
        "steam": "Steam",
        "epic": "Epic Games",
        "gog": "GOG",
        "xbox": "Xbox",
        "playstation": "PlayStation",
        "nintendo": "Nintendo",
    }
    stores = []
    for kind, url in direct.items():
        if kind in pretty and url:
            stores.append({"name": pretty[kind], "kind": kind, "url": url, "direct": True})

    existing = {x["kind"] for x in stores}
    for item in fallback_stores(game["title"], game.get("platforms", [])):
        if item["kind"] not in existing:
            stores.append(item)
    return stores[:7]

def finish_record(game, section, score=0, sources=None):
    platforms = game.get("platforms") or []
    title = game["title"]
    igdb_id = game.get("igdb_id")
    twitch_id = game.get("twitch_game_id")
    game_key = f"igdb:{igdb_id}" if igdb_id else f"twitch:{twitch_id}" if twitch_id else f"title:{norm_title(title)}"
    return {
        "game_key": game_key,
        "title": title,
        "slug": game.get("slug", ""),
        "summary": game.get("summary") or (
            "目前僅取得 Twitch 熱門資料；IGDB 尚未找到可靠的對應遊戲資料。"
            if section == "hot" else "近期遊戲資料。"
        ),
        "cover_url": game.get("cover_url") or "",
        "release_date": game.get("release_date"),
        "platforms": platforms,
        "genres": game.get("genres") or [],
        "stores": build_stores(game),
        "sources": sources or [],
        "pulse_score": round(max(0, min(100, score)), 1),
        "trend_label": game.get("trend_label"),
        "twitch_rank": game.get("twitch_rank"),
        "twitch_game_id": twitch_id,
        "steam_appid": game.get("steam_appid"),
        "steam_players": game.get("steam_players"),
        "igdb_id": igdb_id,
        "rating": game.get("rating"),
    }

def refresh_live():
    igdb = IGDBClient()
    twitch = TwitchClient()

    if STEAM_WEB_API_KEY:
        set_source_status(
            "Steam",
            "ok",
            "Steam API 金鑰已設定，Steam 資料補充功能啟用"
        )
    else:
        set_source_status(
            "Steam",
            "optional",
            "尚未設定 Steam API 金鑰；IGDB 與 Twitch Live Data 不受影響"
        )

    # 1) 跨平台熱門：IGDB PopScore + Twitch 即時 Top Games
    igdb_hot = []
    twitch_hot = []
    try:
        igdb_hot = igdb.hot_games(max(HOT_LIMIT, 30))
        set_source_status("IGDB", "ok", f"取得 {len(igdb_hot)} 筆熱門資料")
    except Exception as e:
        set_source_status("IGDB", "error", str(e)[:240])

    try:
        raw_twitch_hot = twitch.top_games(max(HOT_LIMIT + 20, 50))

        filtered_categories = [
            g["title"]
            for g in raw_twitch_hot
            if is_non_game_twitch_category(g.get("title", ""))
        ]

        twitch_hot = [
            g
            for g in raw_twitch_hot
            if not is_non_game_twitch_category(g.get("title", ""))
        ][:HOT_LIMIT]

        set_source_status(
            "Twitch",
            "ok",
            f"取得 {len(twitch_hot)} 筆遊戲熱門資料"
        )

        if filtered_categories:
            set_source_status(
                "Twitch Filter",
                "ok",
                "已排除非遊戲分類：" + "、".join(filtered_categories)
            )
    except Exception as e:
        set_source_status("Twitch", "error", str(e)[:240])

    # 先做精確標準化名稱合併；配不到的 Twitch 項目再主動搜尋 IGDB。
    merged = {}
    for g in igdb_hot:
        key = norm_title(g["title"])
        merged[key] = dict(g)
        merged[key]["_igdb_score"] = float(g.get("igdb_pop_score", 0))
        merged[key]["_twitch_score"] = None

    search_attempts = 0
    search_matches = 0
    search_misses = 0
    unmatched_titles = []

    for tg in twitch_hot:
        key = norm_title(tg["title"])

        if key in merged:
            merged[key].update({
                "twitch_game_id": tg.get("twitch_game_id"),
                "twitch_rank": tg.get("twitch_rank"),
            })
            if not merged[key].get("cover_url"):
                merged[key]["cover_url"] = tg.get("cover_url")
            merged[key]["_twitch_score"] = tg.get("twitch_score", 0)
            continue

        # Twitch 有、IGDB Hot 沒有：主動用名稱搜尋 IGDB。
        search_attempts += 1
        matched = None
        try:
            candidates = igdb.search_games(tg.get("title"), limit=5)
            matched, _similarity = best_igdb_match(tg.get("title"), candidates)
        except Exception:
            matched = None

        if matched:
            # 若搜尋到的 IGDB 遊戲其實已存在於 hot 集合（只是名稱不同），
            # 就直接合併到既有項目，避免首頁出現重複遊戲。
            existing_key = next(
                (
                    existing_key
                    for existing_key, existing_game in merged.items()
                    if existing_game.get("igdb_id") == matched.get("igdb_id")
                ),
                None,
            )

            match_key = existing_key or norm_title(matched.get("title")) or key
            base = merged.get(match_key, dict(matched))
            base.update({
                "twitch_game_id": tg.get("twitch_game_id"),
                "twitch_rank": tg.get("twitch_rank"),
                "_twitch_score": tg.get("twitch_score", 0),
                "_igdb_enriched": True,
            })
            if "_igdb_score" not in base:
                # 這款不是 IGDB Hot primitive 排名中的項目，
                # 因此只用 Twitch 分數排名，但使用 IGDB 中繼資料補齊卡片。
                base["_igdb_score"] = None
            if not base.get("cover_url"):
                base["cover_url"] = tg.get("cover_url")

            merged[match_key] = base
            search_matches += 1
        else:
            merged[key] = {
                **tg,
                "platforms": [],
                "genres": [],
                "direct_links": {},
                "_igdb_score": None,
                "_twitch_score": tg.get("twitch_score", 0),
                "_igdb_enriched": False,
            }
            search_misses += 1
            unmatched_titles.append(tg.get("title") or "未知遊戲")

    if search_attempts:
        set_source_status(
            "IGDB Match",
            "ok" if search_misses == 0 else "partial",
            f"Twitch 額外查詢 {search_attempts} 筆：IGDB 補齊 {search_matches} 筆，仍缺 {search_misses} 筆"
        )

        if unmatched_titles:
            # 額外保留未配對名稱，方便直接從 /api/status 診斷。
            missing_text = "、".join(unmatched_titles[:10])
            if len(unmatched_titles) > 10:
                missing_text += f"（另有 {len(unmatched_titles) - 10} 款）"
            set_source_status(
                "IGDB Missing",
                "partial",
                f"未配對：{missing_text}"
            )
        else:
            set_source_status(
                "IGDB Missing",
                "ok",
                "全部 Twitch 熱門遊戲皆已取得可靠的 IGDB 對應資料"
            )

    hot_records = []
    for g in merged.values():
        components = []
        sources = []
        if g.get("_igdb_score") is not None:
            components.append((float(g["_igdb_score"]), 0.65))
            sources.append("IGDB PopScore")
        if g.get("_twitch_score") is not None:
            components.append((float(g["_twitch_score"]), 0.35))
            sources.append("Twitch Top Games")
        if g.get("_igdb_enriched") and "IGDB PopScore" not in sources:
            sources.append("IGDB Metadata")
        denom = sum(w for _, w in components) or 1
        score = 100 * sum(v * w for v, w in components) / denom

        if g.get("steam_appid"):
            players = current_players(g["steam_appid"])
            if players is not None:
                g["steam_players"] = players
                sources.append("Steam CCU")

        hot_records.append(finish_record(g, "hot", score, sources))

    hot_records.sort(key=lambda x: x["pulse_score"], reverse=True)
    replace_section("hot", hot_records[:HOT_LIMIT])

    # 2) 近日上市：過去 30 天
    now = datetime.now(timezone.utc)
    try:
        recent = igdb.games_by_release_window(
            int((now - timedelta(days=30)).timestamp()),
            int(now.timestamp()),
            RECENT_LIMIT,
            newest_first=True,
        )
        recent_records = []
        for idx, g in enumerate(recent):
            freshness = max(35, 90 - idx * 1.5)
            recent_records.append(finish_record(g, "new", freshness, ["IGDB Release Dates"]))
        replace_section("new", recent_records)
        set_source_status("IGDB Releases", "ok", f"取得 {len(recent_records)} 筆近日上市")
    except Exception as e:
        set_source_status("IGDB Releases", "error", str(e)[:240])

    # 3) 即將推出：未來 90 天
    try:
        upcoming = igdb.games_by_release_window(
            int(now.timestamp()),
            int((now + timedelta(days=90)).timestamp()),
            UPCOMING_LIMIT,
            newest_first=False,
        )
        upcoming_records = []
        for idx, g in enumerate(upcoming):
            score = max(25, 80 - idx)
            upcoming_records.append(finish_record(g, "upcoming", score, ["IGDB Release Dates"]))
        replace_section("upcoming", upcoming_records)
        set_source_status("IGDB Upcoming", "ok", f"取得 {len(upcoming_records)} 筆即將推出")
    except Exception as e:
        set_source_status("IGDB Upcoming", "error", str(e)[:240])

def refresh_demo():
    # Demo 資料刻意標示為示範，避免被誤認為即時榜單。
    demo_hot = [
        {"title":"Minecraft","platforms":["PC","PlayStation 5","Xbox Series X|S","Nintendo Switch"],"genres":["Adventure","Sandbox"],"pulse_score":96,"summary":"示範資料：跨平台熱門卡片會在 Live 模式改為 API 自動更新。"},
        {"title":"Fortnite","platforms":["PC","PlayStation 5","Xbox Series X|S","Nintendo Switch"],"genres":["Shooter","Battle Royale"],"pulse_score":93,"summary":"示範資料：Live 模式會混合 IGDB PopScore 與 Twitch Top Games。"},
        {"title":"ELDEN RING","platforms":["PC","PlayStation 5","Xbox Series X|S"],"genres":["RPG","Action"],"pulse_score":89,"summary":"示範資料：有直接商店網址時會優先顯示遊戲頁，否則顯示平台入口。"},
        {"title":"Monster Hunter Wilds","platforms":["PC","PlayStation 5","Xbox Series X|S"],"genres":["Action","RPG"],"pulse_score":86,"summary":"示範資料：Steam 只作為其中一個資料來源，不會限制其他平台遊戲進榜。"},
        {"title":"Marvel Rivals","platforms":["PC","PlayStation 5","Xbox Series X|S"],"genres":["Shooter","Multiplayer"],"pulse_score":83,"summary":"示範資料：之後可再加入收藏、登入、個人推薦與價格追蹤。"},
        {"title":"Stardew Valley","platforms":["PC","PlayStation 4","Xbox One","Nintendo Switch"],"genres":["Simulation","RPG"],"pulse_score":78,"summary":"示範資料：卡片支援多平台與不同商店入口。"},
    ]
    hot = []
    for i,g in enumerate(demo_hot,1):
        base = dict(g)
        base.update({"direct_links": {}, "twitch_rank": i})
        hot.append(finish_record(base, "hot", g["pulse_score"], ["Demo", "IGDB PopScore", "Twitch Top Games"]))
    replace_section("hot", hot)

    today = datetime.now(timezone.utc).date()
    demo_new = [
        {"title":"Demo New Release A","platforms":["PC","PlayStation 5"],"genres":["Action"],"release_date":str(today),"summary":"示範新上市資料；啟用 API 後會顯示過去 30 天的實際作品。"},
        {"title":"Demo New Release B","platforms":["PC","Xbox Series X|S"],"genres":["RPG"],"release_date":str(today - timedelta(days=4)),"summary":"發售日期由 IGDB 自動同步。"},
        {"title":"Demo New Release C","platforms":["Nintendo Switch"],"genres":["Adventure"],"release_date":str(today - timedelta(days=9)),"summary":"支援 Nintendo 平台，不限定 Steam。"},
    ]
    replace_section("new", [finish_record({**g,"direct_links":{}}, "new", 70-i*5, ["Demo"]) for i,g in enumerate(demo_new)])

    demo_up = [
        {"title":"Demo Upcoming A","platforms":["PC","PlayStation 5"],"genres":["RPG"],"release_date":str(today + timedelta(days=10)),"summary":"示範即將推出資料；Live 模式抓未來 90 天。"},
        {"title":"Demo Upcoming B","platforms":["Xbox Series X|S"],"genres":["Shooter"],"release_date":str(today + timedelta(days=25)),"summary":"可從平台按鈕前往商店或官方頁面。"},
        {"title":"Demo Upcoming C","platforms":["Nintendo Switch"],"genres":["Adventure"],"release_date":str(today + timedelta(days=45)),"summary":"後續可以加上上市倒數與通知。"},
    ]
    replace_section("upcoming", [finish_record({**g,"direct_links":{}}, "upcoming", 65-i*5, ["Demo"]) for i,g in enumerate(demo_up)])

    for source in ("IGDB", "Twitch", "Steam"):
        set_source_status(source, "demo", "尚未設定 API 金鑰，目前使用示範資料")

def refresh_all():
    if effective_mode() == "live":
        refresh_live()
    else:
        refresh_demo()