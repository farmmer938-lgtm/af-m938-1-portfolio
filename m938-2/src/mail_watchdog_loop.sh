#!/usr/bin/env bash
# Watch the Gmail inbox AF uses (no cron in this image). Pidfile-guarded.
HERE="$(cd "$(dirname "$0")" && pwd)"
# True only for a live, non-zombie pid. `kill -0` also succeeds for a ZOMBIE, so a
# crashed loop would otherwise look "already running" forever and never restart.
af_alive() {
  [ -n "$1" ] || return 1
  [ -d "/proc/$1" ] || return 1
  [ "$(awk '{print $3}' "/proc/$1/stat" 2>/dev/null)" = "Z" ] && return 1
  return 0
}
PID=/workspace/.mail-watchdog.pid
if [ -f "$PID" ] && af_alive "$(cat "$PID" 2>/dev/null)"; then echo "already running: $(cat "$PID")"; exit 0; fi
echo $$ > "$PID"
while true; do
  if [ -f /workspace/.secrets/gmail_app.json ]; then
    python3 "$HERE/gmail_imap.py" read >> /workspace/.mail-watch.log 2>&1
  else
    python3 "$HERE/mail_watchdog.py" >> /workspace/.mail-watch.log 2>&1
  fi
  sleep 600
done
