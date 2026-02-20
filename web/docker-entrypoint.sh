#!/bin/sh
set -e

ENGINE_BASE_URL=${ENGINE_BASE_URL:-}
ESCAPED=$(printf '%s' "$ENGINE_BASE_URL" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf 'window.RUNTIME_CONFIG = { ENGINE_BASE_URL: "%s" };' "$ESCAPED" > /usr/share/nginx/html/static/runtime-config.js

exec nginx -g 'daemon off;'
