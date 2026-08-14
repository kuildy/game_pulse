#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PID_FILE="$APP_DIR/run/wavesig.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "WAVESIG 目前沒有執行。"
    exit 0
fi

PID=$(cat "$PID_FILE" 2>/dev/null || true)
if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "已清除失效的 PID 檔。"
    exit 0
fi

kill "$PID"
COUNT=0
while kill -0 "$PID" 2>/dev/null && [ "$COUNT" -lt 20 ]; do
    COUNT=$((COUNT + 1))
    sleep 1
done

if kill -0 "$PID" 2>/dev/null; then
    echo "服務仍在結束中，請稍後再檢查。" >&2
    exit 1
fi

rm -f "$PID_FILE"
echo "WAVESIG 已停止。"
