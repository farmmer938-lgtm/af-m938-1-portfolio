#!/usr/bin/env bash
# Poll the Do.ink storefront for orders every 10 min (no cron in this image).
HERE="$(cd "$(dirname "$0")" && pwd)"
# True only for a live, non-zombie pid. `kill -0` also succeeds for a ZOMBIE, so a
# crashed loop would otherwise look "already running" forever and never restart.
af_alive() {
  [ -n "$1" ] || return 1
  [ -d "/proc/$1" ] || return 1
  [ "$(awk '{print $3}' "/proc/$1/stat" 2>/dev/null)" = "Z" ] && return 1
  return 0
}
PID=/workspace/.doink-watchdog.pid
if [ -f "$PID" ] && af_alive "$(cat "$PID" 2>/dev/null)"; then
  echo "already running: $(cat "$PID")"; exit 0
fi
echo $$ > "$PID"
while true; do
  python3 "$HERE/doink_watchdog.py" >> /workspace/.doink-orders.log 2>&1
  sleep 600
done
