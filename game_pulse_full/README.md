# GAME PULSE
跨平台「近日熱門 / 新上市 / 即將推出」遊戲播報網站。

Synology DS220j 安裝方式請看 `NAS_SETUP_DS220J_ZH-TW.md`。

## 你已經拿到的功能

- Flask 後端
- SQLite 資料庫
- 響應式深色遊戲情報站 UI
- 熱門 / 新上市 / 即將推出
- PC / PlayStation / Xbox / Nintendo 篩選
- 遊戲搜尋
- IGDB 封面、類型、平台、發售日
- IGDB PopScore 熱門 primitives
- Twitch Top Games
- Steam current players（IGDB 能取得 Steam App ID 時）
- Steam / Epic / GOG / PlayStation / Xbox / Nintendo / 官方網站入口
- 沒有 API Key 也能跑的 Demo Mode
- 手動更新與每 3 小時更新工具

---

# 1. 最快啟動方式（Windows）

直接雙擊：

    start.bat

第一次會：
1. 建立 `.venv`
2. 安裝 requirements
3. 啟動 Flask

然後開瀏覽器：

    http://127.0.0.1:5000

如果沒有設定 API Key，網站會顯示 `DEMO MODE`。

---

# 2. 啟用真正的自動資料

IGDB API 使用 Twitch Developer Application 的 Client ID / Secret。

建立 Twitch Developer App 後：

1. 把 `.env.example` 複製成 `.env`
2. 填入：

    TWITCH_CLIENT_ID=你的ClientID
    TWITCH_CLIENT_SECRET=你的ClientSecret
    GAME_PULSE_MODE=auto

3. 執行：

    update_now.bat

重新整理網站後，右上角應該會變成：

    LIVE DATA

# 3. 自動每 3 小時更新

開啟：

    auto_update_3h.bat

只要這個視窗保持執行，就會每 3 小時刷新一次。

如果你希望「關掉更新視窗也照樣每 3 小時執行」，可以在 PowerShell 執行：

    powershell -ExecutionPolicy Bypass -File .\setup_auto_update_task.ps1

它會建立 Windows 工作排程：

    GAME PULSE Auto Update

正式上線時，建議不要靠常駐 BAT，而是：
- Windows Task Scheduler
- Linux cron
- GitHub Actions + API
- AWS EventBridge / Lambda
- Render Cron Job
- Railway / Fly.io 排程

建議頻率：
- Twitch 熱門：每 1–3 小時
- IGDB PopScore：每天 1 次也足夠
- 新上市 / Upcoming：每天 1 次

目前範例為了簡化，統一由 refresh_all 一次更新。

---

# 4. 熱門分數

Live Mode 目前：

    45% IGDB Interest
    35% Twitch Live Viewers
    20% Steam CCU

IGDB 內部再混合可取得的 primitives，例如：
- Visits
- Want to Play
- Playing
- Total Reviews

每個 primitive 先 max-normalize，再做加權。

若某一來源缺資料，不會直接算 0，而是依目前可用來源重新正規化。

---

# 5. 為什麼不是每個平台都直接抓商店排行榜？

因為不同商店的公開 API 能力不一致。

這個架構把兩件事分開：

A. 「熱門判定」
- IGDB
- Twitch
- Steam 補充

B. 「去哪裡玩 / 買」
- IGDB 有直接外部網址 → 使用遊戲頁
- 沒有直接網址 → 顯示官方商店入口

這樣 PlayStation / Xbox / Nintendo 遊戲即使沒有 Steam，也能出現在榜單。

---

# 6. 專案結構

    game_pulse_full/
    ├─ app.py
    ├─ config.py
    ├─ db.py
    ├─ requirements.txt
    ├─ .env.example
    ├─ start.bat
    ├─ update_now.bat
    ├─ auto_update_3h.bat
    ├─ run_updater_loop.py
    ├─ services/
    │  ├─ aggregator.py
    │  ├─ igdb.py
    │  ├─ twitch.py
    │  └─ steam.py
    ├─ scripts/
    │  └─ update_games.py
    ├─ templates/
    │  └─ index.html
    ├─ static/
    │  ├─ css/style.css
    │  └─ js/app.js
    └─ data/
       └─ game_pulse.db  # 啟動後自動建立，不放進 GitHub

---

# 7. 下一階段適合增加

- 使用者登入
- 收藏 / 我的願望清單
- 每款遊戲獨立詳細頁
- 歷史熱門分數走勢
- Steam / Epic 價格與特價
- 中文名稱與中文摘要
- AI 遊戲推薦
- Discord / LINE 發售提醒
- 後台管理
- AWS 部署
- Redis cache
- PostgreSQL
- REST API key / rate limiting
