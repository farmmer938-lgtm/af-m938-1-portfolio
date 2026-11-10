#!/usr/bin/env bash
# Keep AF's x402 cashier alive on :12000 (survives container restarts via af_boot.sh).
# node_modules is NOT committed (725 MB) — this reinstalls it when the rootfs is wiped.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PID=/workspace/.afcashier.pid
LOG=/workspace/.afcashier.log
# A zombie (defunct) process still passes `kill -0`, which would make this guard
# believe the cashier is up forever. Treat state Z as not-running.
alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null && [ "$(awk '{print $3}' /proc/"$1"/stat 2>/dev/null)" != "Z" ]; }
if [ -f "$PID" ] && alive "$(cat "$PID" 2>/dev/null)"; then
  echo "already running: $(cat "$PID")"; exit 0
fi
cd "$HERE"
if [ ! -d node_modules/@x402/express ]; then
  echo "$(date -Is) installing cashier deps" >>"$LOG"
  npm install --no-audit --no-fund >>"$LOG" 2>&1
fi
# payTo comes from the AF wallet secret so the key never lands in the repo.
if [ -z "${AF_PAY_TO:-}" ] && [ -n "${AF_MAIN_WALLET:-}" ]; then
  export AF_PAY_TO="$(python3 -c "import os,json;print(json.loads(os.environ['AF_MAIN_WALLET'])['address'])" 2>/dev/null)"
fi
setsid nohup node server.mjs >>"$LOG" 2>&1 &
echo $! > "$PID"
echo "afcashier started pid=$(cat "$PID")"
