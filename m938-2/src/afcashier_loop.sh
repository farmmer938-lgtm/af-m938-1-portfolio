#!/usr/bin/env bash
# Keep AF's x402 cashier (the money intake) alive on :12000. No cron in this image,
# so this loop is the supervisor; af_boot.sh starts it after a container restart.
HERE="$(cd "$(dirname "$0")" && pwd)"
PID=/workspace/.afcashier-loop.pid
if [ -f "$PID" ] && kill -0 "$(cat "$PID" 2>/dev/null)" 2>/dev/null; then
  echo "already running: $(cat "$PID")"; exit 0
fi
echo $$ > "$PID"
while true; do
  bash "$HERE/afcashier/run.sh" >> /workspace/.afcashier-loop.log 2>&1
  sleep 120
done
