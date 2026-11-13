#!/bin/bash
# Keep AF's CDP Live View (tools/af_liveview.py) alive on port 12001.
# 12001 is the sandbox's public "work-2" port; the noVNC websockify used to hold it.
# The live view replaces noVNC (no X streaming), but if it is down and a websockify
# is configured we fall back so K always has *some* view. Idempotent. Log:
# /workspace/.liveview-watchdog.log
LOG=/workspace/.liveview-watchdog.log
BRAIN="${AF_BRAIN_DIR:-/workspace/project/AX_MASTER_BRAIN}"
PORT="${AF_LIVEVIEW_PORT:-12001}"

while true; do
  if ! curl -s -m 3 -o /dev/null "http://127.0.0.1:$PORT/?t=$(cat /workspace/.af-liveview-token 2>/dev/null)"; then
    echo "$(date -Is) live view down -> starting af_liveview.py on :$PORT" >> "$LOG"
    pkill -f "af_liveview.py" 2>/dev/null
    sleep 1
    AF_LIVEVIEW_PORT="$PORT" setsid nohup python3 "$BRAIN/tools/af_liveview.py" \
      >>"$LOG" 2>&1 < /dev/null &
    sleep 4
  fi
  sleep 30
done
