#!/usr/bin/env bash
# Run the Lazada onboarding autopilot every 15 min. This image has no cron/crontab,
# so we self-schedule. Pidfile-guarded so restarts don't stack copies.
HERE="$(cd "$(dirname "$0")" && pwd)"
PID=/workspace/.lazada-autopilot-loop.pid
if [ -f "$PID" ] && kill -0 "$(cat "$PID" 2>/dev/null)" 2>/dev/null; then
  echo "already running: $(cat "$PID")"
  exit 0
fi
echo $$ > "$PID"
while true; do
  [ -f /workspace/.lazada-autopilot.done ] && break
  /usr/bin/python3 "$HERE/lazada_autopilot.py" >> /workspace/.lazada-autopilot.log 2>&1
  sleep 900
done
rm -f "$PID"
