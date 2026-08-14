#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PID_FILE="$APP_DIR/run/wavesig.pid"
PORT=${WAVESIG_PORT:-5050}

cd "$APP_DIR"
mkdir -p data logs run

if [ ! -x .venv/bin/gunicorn ]; then
    echo "尚未安裝執行環境，請先執行 $APP_DIR/nas/install.sh" >&2
    exit 1
fi

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "WAVESIG 已在執行，PID $OLD_PID"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

nohup .venv/bin/gunicorn \
    --workers 1 \
    --threads 2 \
    --timeout 180 \
    --bind "127.0.0.1:$PORT" \
    --pid "$PID_FILE" \
    --access-logfile "$APP_DIR/logs/access.log" \
    --error-logfile "$APP_DIR/logs/error.log" \
    app:app >/dev/null 2>&1 &

COUNT=0
while [ "$COUNT" -lt 20 ]; do
    if [ -f "$PID_FILE" ]; then
        NEW_PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$NEW_PID" ] && kill -0 "$NEW_PID" 2>/dev/null; then
            echo "WAVESIG 已啟動：http://127.0.0.1:$PORT（PID $NEW_PID）"
            exit 0
        fi
    fi
    COUNT=$((COUNT + 1))
    sleep 1
done

echo "啟動失敗，請查看 $APP_DIR/logs/error.log" >&2
exit 1
