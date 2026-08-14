# DS220j Container Manager 安裝

## 1. 填寫環境設定

在 File Station 開啟 `/volume1/web/game-pulse/container.env`，填入與 Render 相同的 API 金鑰，並設定 `ADMIN_TOKEN` 與至少 32 字元的 `FLASK_SECRET_KEY`。

## 2. 建立專案

1. 開啟 Container Manager。
2. 選擇「專案」→「新增」。
3. 專案名稱填入 `wavesig`。
4. 路徑選擇 `/volume1/web/game-pulse`。
5. 上傳該資料夾內的 `docker-compose.yml` 建立專案。
6. 等待映像建置完成。

第一次建置會下載 ARM64 Python 基礎映像並安裝套件，DS220j 可能需要數分鐘。

## 3. 確認狀態

在 Container Manager 的「容器」頁面確認 `wavesig` 顯示「執行中」，稍後健康狀態應顯示 `healthy`。

服務只發布在 NAS 本機的 `127.0.0.1:5050`，不會直接把容器連接埠開放到網際網路。下一步使用 DSM 反向代理連入。
