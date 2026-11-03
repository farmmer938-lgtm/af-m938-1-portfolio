#!/bin/bash
# Keep the noVNC stack alive between container restarts. Logs to /workspace/.novnc-watchdog.log
# NOTE: this image has no `ss`/`netstat`; probe with curl instead.
LOG=/workspace/.novnc-watchdog.log
RESTORED=/workspace/.novnc-restored
while true; do
  if ! curl -s -m 3 -o /dev/null http://127.0.0.1:12001/vnc.html; then
    # one-shot per boot: /workspace persists, so don't re-run after a successful restore
    if [ ! -f "$RESTORED" ]; then
      echo "$(date -Is) websockify down -> restoring (first time this boot)" >> "$LOG"
      rm -f /workspace/.novnc-profile/Singleton* 2>/dev/null
      ( cd /workspace/af-m938-1-portfolio/m938-2 && bash src/restore_novnc.sh ) >> "$LOG" 2>&1 \
        && touch "$RESTORED"
    else
      echo "$(date -Is) websockify down (already restored once this boot; manual check needed)" >> "$LOG"
      sleep 60
    fi
  else
    rm -f "$RESTORED"
  fi
  sleep 30
done
