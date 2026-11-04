#!/usr/bin/env bash
# Poll the Do.ink storefront for orders every 10 min (no cron in this image).
HERE="$(cd "$(dirname "$0")" && pwd)"
PID=/workspace/.doink-watchdog.pid
if [ -f "$PID" ] && kill -0 "$(cat "$PID" 2>/dev/null)" 2>/dev/null; then
  echo "already running: $(cat "$PID")"; exit 0
fi
echo $$ > "$PID"
while true; do
  python3 "$HERE/doink_watchdog.py" >> /workspace/.doink-orders.log 2>&1
  sleep 600
done
