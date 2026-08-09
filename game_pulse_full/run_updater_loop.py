"""
簡易自動更新器：
保持此程式開啟，每 3 小時執行一次資料更新。
正式部署建議改用 Windows 工作排程器 / cron / 雲端排程服務。
"""
import time
from datetime import datetime
from db import init_db
from services.aggregator import refresh_all

INTERVAL_SECONDS = 3 * 60 * 60

if __name__ == "__main__":
    init_db()
    while True:
        try:
            print(f"[{datetime.now().isoformat(timespec='seconds')}] 更新開始")
            refresh_all()
            print("更新完成；3 小時後再次更新。")
        except Exception as e:
            print("更新失敗：", e)
        time.sleep(INTERVAL_SECONDS)
