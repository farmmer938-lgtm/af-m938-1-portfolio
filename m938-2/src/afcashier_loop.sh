#!/usr/bin/env bash
# Keep AF's x402 cashier (the money intake) alive on :12000. No cron in this image,
# so this loop is the supervisor; af_boot.sh starts it after a container restart.
HERE="$(cd "$(dirname "$0")" && pwd)"
# True only for a live, non-zombie pid. `kill -0` also succeeds for a ZOMBIE, so a
# crashed loop would otherwise look "already running" forever and never restart.
af_alive() {
  [ -n "$1" ] || return 1
  [ -d "/proc/$1" ] || return 1
  [ "$(awk '{print $3}' "/proc/$1/stat" 2>/dev/null)" = "Z" ] && return 1
  return 0
}
PID=/workspace/.afcashier-loop.pid
if [ -f "$PID" ] && af_alive "$(cat "$PID" 2>/dev/null)"; then
  echo "already running: $(cat "$PID")"; exit 0
fi
echo $$ > "$PID"
while true; do
  bash "$HERE/afcashier/run.sh" >> /workspace/.afcashier-loop.log 2>&1
  sleep 120
done
