import requests

def current_players(appid):
    if not appid:
        return None
    try:
        r = requests.get(
            "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
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
