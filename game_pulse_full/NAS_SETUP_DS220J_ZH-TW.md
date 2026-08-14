# WAVESIG 安裝到 Synology DS220j

此包針對 DSM 7.2／7.3 與 DS220j（512 MB RAM）設定：Gunicorn 僅使用 1 個 worker、2 個 threads，網站只監聽 NAS 本機 `127.0.0.1:5050`，公開流量由 DSM 反向代理提供 HTTPS。

## 一、準備套件與資料夾

1. DSM 套件中心安裝 `Python 3`。
2. 控制台 → 終端機和 SNMP → 啟用 SSH 服務。
3. 在 File Station 建立 `/volume1/web/game-pulse`。
4. 將此 ZIP 解壓縮後的全部內容放進該資料夾；確認裡面直接看得到 `app.py`、`db.py`、`nas`，不要再多包一層。

## 二、安裝 Python 環境

從電腦連線 NAS：

```bash
ssh 你的DSM帳號@NAS區域網路IP
```

進入管理者模式後執行：

```bash
sudo -i
cd /volume1/web/game-pulse
chmod +x nas/*.sh
./nas/install.sh
```

安裝程式會建立 `.venv`、`data/game_pulse.db`、`logs`、`run` 與 `.env`。

## 三、填入 API 設定

編輯 `/volume1/web/game-pulse/.env`，至少填入：

```env
TWITCH_CLIENT_ID=你的TwitchClientID
TWITCH_CLIENT_SECRET=你的TwitchClientSecret
STEAM_WEB_API_KEY=你的SteamKey
GAME_PULSE_MODE=auto
ADMIN_TOKEN=你自行設定的管理密碼
FLASK_SECRET_KEY=至少32字元的隨機字串
```

不要加入 `RENDER=true`，也不要把 `.env` 上傳至 GitHub。

## 四、啟動並在區域網路測試

```bash
cd /volume1/web/game-pulse
./nas/start.sh
```

在 NAS SSH 測試：

```bash
wget -qO- http://127.0.0.1:5050/health
```

看到 `"ok":true` 即代表網站已啟動。錯誤紀錄位於：

```text
/volume1/web/game-pulse/logs/error.log
```

## 五、設定 DSM 反向代理

DSM → 控制台 → 登入入口 → 進階 → 反向代理伺服器 → 新增：

| 欄位 | 設定 |
|---|---|
| 來源通訊協定 | HTTPS |
| 來源主機名稱 | 你的網域或 Synology DDNS |
| 來源連接埠 | 443 |
| 目的地通訊協定 | HTTP |
| 目的地主機名稱 | 127.0.0.1 |
| 目的地連接埠 | 5050 |

DSM 反向代理位置可參考 Synology 官方說明：控制台 → 登入入口 → 進階。

## 六、公開網址與 HTTPS

1. DSM → 控制台 → 外部存取 → DDNS，申請或加入網域。
2. DSM → 控制台 → 安全性 → 憑證，為該網域申請 Let's Encrypt 憑證。
3. 將憑證指派給剛建立的反向代理服務。
4. 路由器只轉發外部 TCP `443` 到 NAS TCP `443`。
5. 不要把 `5050`、DSM `5000/5001` 直接開放到網際網路。

如果家用網路使用 CGNAT，路由器轉發不會生效，需要向電信業者申請公網 IP 或改用安全 Tunnel。

## 七、DSM 開機自動啟動

DSM → 控制台 → 工作排程器 → 新增 → 觸發的任務 → 使用者定義的指令碼：

- 使用者：`root`
- 事件：`開機`
- 指令：

```bash
/bin/sh /volume1/web/game-pulse/nas/start.sh
```

## 八、每 3 小時更新

工作排程器再新增一個排程任務：

- 使用者：`root`
- 排程：每 3 小時
- 指令：

```bash
/bin/sh /volume1/web/game-pulse/nas/update.sh
```

## 常用指令

```bash
./nas/start.sh
./nas/stop.sh
./nas/restart.sh
./nas/update.sh
```

SQLite 會永久保存在 `/volume1/web/game-pulse/data/game_pulse.db`。備份專案時請保留這個檔案，但不要提交到 GitHub。
