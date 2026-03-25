#!/bin/sh
set -eu

require_env() {
    var_name="$1"
    var_value="$2"

    if [ -z "$var_value" ]; then
        echo "[startup-check] Missing required environment variable: $var_name" >&2
        exit 1
    fi
}

require_env "TG_BOT_TOKEN" "${TG_BOT_TOKEN:-}"
require_env "TG_CHAT_ID" "${TG_CHAT_ID:-}"
require_env "SUBSCRIBE_PASSWORD" "${SUBSCRIBE_PASSWORD:-}"

DATA_DIR="${DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR" "$DATA_DIR/tmp"

exec python main.py
