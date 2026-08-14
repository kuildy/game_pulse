#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

cd "$APP_DIR"
mkdir -p data logs run

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "找不到 python3。請先從 DSM 套件中心安裝 Python 3。" >&2
    exit 1
fi

if [ ! -d .venv ]; then
    "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --no-cache-dir -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env
    echo "已建立 $APP_DIR/.env，請先填入 API 金鑰。"
fi

.venv/bin/python -c "from db import init_db; init_db()"

echo "安裝完成。填好 .env 後執行：$APP_DIR/nas/start.sh"
