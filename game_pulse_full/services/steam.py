from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


STEAM_CURRENT_PLAYERS_URL = (
    "https://api.steampowered.com/ISteamUserStats/"
    "GetNumberOfCurrentPlayers/v1/"
)


def current_players(appid):
    if not appid:
        return None
    try:
        r = requests.get(
            STEAM_CURRENT_PLAYERS_URL,
            params={"appid": int(appid)},
            timeout=12,
        )
        r.raise_for_status()
        payload = r.json().get("response", {})
        if payload.get("result") == 1:
            return int(payload.get("player_count", 0))
    except Exception:
        return None
    return None


def current_players_many(appids, max_workers=8):
    """平行取得多款 Steam App 的即時玩家數，降低整次更新耗時。"""
    unique_ids = list(dict.fromkeys(
        str(appid).strip()
        for appid in appids
        if str(appid or "").strip().isdigit()
    ))
    if not unique_ids:
        return {}

    result = {}
    workers = max(1, min(int(max_workers), 10, len(unique_ids)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(current_players, appid): appid for appid in unique_ids}
        for future in as_completed(futures):
            appid = futures[future]
            try:
                result[appid] = future.result()
            except Exception:
                result[appid] = None
    return result
