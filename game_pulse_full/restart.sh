#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$APP_DIR/nas/stop.sh"
"$APP_DIR/nas/start.sh"
