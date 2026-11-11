#!/usr/bin/env bash
# Keep the session-health snapshot fresh. session_health.py existed but nothing ever
# ran it, so /workspace/.session-health.json went stale for hours and the dashboard
# showed an outdated "doink/lazada" state. This loop re-checks every 15 min.
HERE="$(cd "$(dirname "$0")" && pwd)"
# True only for a live, non-zombie pid. `kill -0` also succeeds for a ZOMBIE, so a
# crashed loop would otherwise look "already running" forever and never restart.
af_alive() {
  [ -n "$1" ] || return 1
  [ -d "/proc/$1" ] || return 1
  [ "$(awk '{print $3}' "/proc/$1/stat" 2>/dev/null)" = "Z" ] && return 1
  return 0
}
PID=/workspace/.session-health-loop.pid
if [ -f "$PID" ] && af_alive "$(cat "$PID" 2>/dev/null)"; then
  echo "already running: $(cat "$PID")"; exit 0
fi
echo $$ > "$PID"
while true; do
  python3 "$HERE/session_health.py" >> /workspace/.session-health.log 2>&1
  sleep 900
done
