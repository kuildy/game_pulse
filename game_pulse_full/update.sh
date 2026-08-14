#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$APP_DIR"
mkdir -p logs

if [ ! -x .venv/bin/python ]; then
    echo "尚未安裝執行環境，請先執行 $APP_DIR/nas/install.sh" >&2
    exit 1
fi

.venv/bin/python scripts/update_games.py >>"$APP_DIR/logs/update.log" 2>&1
echo "WAVESIG 資料更新完成。"
