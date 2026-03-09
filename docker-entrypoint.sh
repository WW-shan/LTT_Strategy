#!/bin/sh
set -eu

required_vars="TG_BOT_TOKEN TG_CHAT_ID SUBSCRIBE_PASSWORD"

for var in $required_vars; do
    eval "value=\${$var:-}"
    if [ -z "$value" ]; then
        echo "[startup-check] Missing required environment variable: $var" >&2
        exit 1
    fi
done

mkdir -p /app/data

if [ ! -f /app/data/allowed_users.txt ]; then
    : > /app/data/allowed_users.txt
fi

if [ ! -f /app/data/user_settings.json ]; then
    printf '{}' > /app/data/user_settings.json
fi

ln -sf /app/data/allowed_users.txt /app/allowed_users.txt
ln -sf /app/data/user_settings.json /app/user_settings.json

exec python main.py
