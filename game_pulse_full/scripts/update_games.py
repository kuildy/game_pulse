from pathlib import Path
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import init_db
from services.aggregator import refresh_all

if __name__ == "__main__":
    init_db()
    print(f"[{datetime.now().isoformat(timespec='seconds')}] 開始更新 GAME PULSE...")
    refresh_all()
    print(f"[{datetime.now().isoformat(timespec='seconds')}] 更新完成。")
