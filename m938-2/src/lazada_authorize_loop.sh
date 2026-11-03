#!/usr/bin/env bash
# Keep waiting for K's one-time Lazada seller authorization, then exchange the code
# for an access token (project m938-2). Idempotent; safe to run in a loop.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TOK=/workspace/.secrets/lazada.json
LOG=/workspace/.lazada-authorize.log

while true; do
  if python3 - "$TOK" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    d = {}
sys.exit(0 if d.get("access_token") else 1)
PY
  then
    echo "$(date -Is) access token present; publishing listings" >>"$LOG"
    python3 "$HERE/lazada_publish.py" preflight >>"$LOG" 2>&1 || true
    if [ ! -f /workspace/.lazada-published ]; then
      python3 "$HERE/lazada_publish.py" create 0 >>"$LOG" 2>&1 \
        && touch /workspace/.lazada-published
    fi
    sleep 600
    continue
  fi
  echo "$(date -Is) waiting for seller authorization (up to 10 min)" >>"$LOG"
  python3 "$HERE/lazada_authorize.py" watch 10 >>"$LOG" 2>&1 || true
  sleep 20
done
