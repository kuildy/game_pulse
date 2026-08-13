# WAVESIG：YouTube 與 Wikipedia 設定

這一版只加入 YouTube 與 Wikipedia。兩者會把公開熱度訊號寫入 SQLite 並保留 35 天快照；同一款遊戲、同一來源在 24 小時內使用快取。目前不會改動 PULSE 排名。

## 1. YouTube Data API v3

YouTube 需要 Google Cloud API Key。

1. 登入 [Google Cloud Console](https://console.cloud.google.com/)。
2. 建立或選擇一個專案，例如 `WAVESIG`。
3. 進入「API 和服務」→「程式庫」。
4. 搜尋 `YouTube Data API v3`，按「啟用」。
5. 進入「API 和服務」→「憑證」。
6. 按「建立憑證」→「API 金鑰」。
7. 編輯該金鑰，在「API 限制」只允許 `YouTube Data API v3`。
8. 複製金鑰，放入 Render 的環境變數：

```env
YOUTUBE_API_KEY=你的GoogleAPIKey
```

程式會搜尋最近 48 小時內的 Gaming 類別影片，並保存相符影片數、樣本觀看數、按讚數與留言數。預設只處理熱門榜前 20 款且 24 小時快取，可避免小型 NAS 負載過高，也可節省 YouTube 配額。

注意：YouTube 請求由 Flask 伺服器送出，不是瀏覽器送出，因此不要把 API Key 設成「HTTP 參照網址限制」。若目前沒有固定的 Render 出站 IP，可先只設定「API 限制」，並確保金鑰只存在 Render Environment。

## 2. Wikipedia / Wikimedia

Wikipedia Pageviews API 不需要申請 API Key，也不需要 OAuth。

只要在 Render 設定一個可辨識、含聯絡方式的 User-Agent：

```env
WIKIMEDIA_USER_AGENT=WAVESIG/1.0 (https://你的公開網址; mailto:你的聯絡信箱)
```

程式會先在英文 Wikipedia 尋找可靠的遊戲條目，再保存最近完整日瀏覽量、前一日比較與 7 日瀏覽量。若沒有可靠條目，也會保存 `not_found` 快照，避免反覆重查。

## 3. 共用的蒐集設定

建議 DS220j / Render 先使用預設值：

```env
SOCIAL_SIGNAL_LIMIT=20
SOCIAL_SIGNAL_TTL_HOURS=24
SOCIAL_SIGNAL_WINDOW_HOURS=48
```

- `SOCIAL_SIGNAL_LIMIT`：每次最多處理熱門榜前幾款。
- `SOCIAL_SIGNAL_TTL_HOURS`：相同遊戲與來源多久後才重抓。
- `SOCIAL_SIGNAL_WINDOW_HOURS`：YouTube 搜尋最近幾小時的影片。

## 4. 加到 Render

1. 開啟 Render Dashboard。
2. 進入 WAVESIG 的 Web Service。
3. 選擇 `Environment`。
4. 逐一加入上面的環境變數；不要把真實金鑰寫入 `.env.example` 或 GitHub。
5. 儲存後重新部署。
6. 登入 `https://你的網址/admin`，按「立即重新抓取資料」。

檢查來源狀態：

```text
GET https://你的網址/api/status
```

檢查單款遊戲最新訊號與 7 日快照：

```text
GET https://你的網址/api/game/<game-key-or-slug>/social
GET https://你的網址/api/game/<game-key-or-slug>/social?history=7
```

遊戲詳細頁也會自動顯示 YouTube 與 Wikipedia 訊號卡片。

## 5. SQLite 持久化提醒

Render 免費 Web Service 的本機檔案系統不是永久儲存；重新部署、重啟或休眠後，SQLite 快照可能消失。若要長期累積資料，請選擇其中一種：

- 最終把程式與 SQLite 放到 NAS。
- Render 付費服務掛載 Persistent Disk，並把資料庫路徑移到該磁碟。
- 後續把 SQLite 改成 PostgreSQL。
