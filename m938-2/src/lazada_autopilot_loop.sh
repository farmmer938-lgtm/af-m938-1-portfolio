#!/usr/bin/env bash
# Run the Lazada onboarding autopilot every 15 min. This image has no cron/crontab,
# so we self-schedule. Pidfile-guarded so restarts don't stack copies.
HERE="$(cd "$(dirname "$0")" && pwd)"
# True only for a live, non-zombie pid. `kill -0` also succeeds for a ZOMBIE, so a
# crashed loop would otherwise look "already running" forever and never restart.
af_alive() {
  [ -n "$1" ] || return 1
  [ -d "/proc/$1" ] || return 1
  [ "$(awk '{print $3}' "/proc/$1/stat" 2>/dev/null)" = "Z" ] && return 1
  return 0
}
PID=/workspace/.lazada-autopilot-loop.pid
if [ -f "$PID" ] && af_alive "$(cat "$PID" 2>/dev/null)"; then
  echo "already running: $(cat "$PID")"
  exit 0
fi
echo $$ > "$PID"
while true; do
  [ -f /workspace/.lazada-autopilot.done ] && break
  python3 "$HERE/lazada_autopilot.py" >> /workspace/.lazada-autopilot.log 2>&1
  sleep 900
done
rm -f "$PID"
