#!/usr/bin/env bash
# Watch the Gmail inbox AF uses (no cron in this image). Pidfile-guarded.
HERE="$(cd "$(dirname "$0")" && pwd)"
PID=/workspace/.mail-watchdog.pid
if [ -f "$PID" ] && kill -0 "$(cat "$PID" 2>/dev/null)" 2>/dev/null; then echo "already running: $(cat "$PID")"; exit 0; fi
echo $$ > "$PID"
while true; do python3 "$HERE/mail_watchdog.py" >> /workspace/.mail-watch.log 2>&1; sleep 600; done
