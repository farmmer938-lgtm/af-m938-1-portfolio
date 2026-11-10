#!/usr/bin/env bash
# AF "first breath": bring every always-on service back up after a container
# restart. The sandbox has no cron/systemd/restart hook, so AF runs this at the
# start of every session and from every automation. Idempotent and safe to run
# repeatedly; it starts only what is missing.
#
# Why a separate script: pidfiles alone are unsafe here. After a restart the OS
# recycles PIDs, so a stale pidfile can point at an unrelated live process and a
# naive `kill -0` check would wrongly report "already running" (this is exactly
# how the x402 cashier stayed dead). Every check below matches the process
# *identity* (pgrep -f on the script/command), never just a PID.
set -u
SRC=/workspace/afsrc
LOG=/workspace/.af-up.log
log() { echo "$(date -Is) $*" | tee -a "$LOG"; }

is_running() { pgrep -f "$1" >/dev/null 2>&1; }

# 0. Ensure the durable source tree exists. /workspace survives a container
#    restart, but a full rebuild wipes it; in that case re-provision from GitHub
#    so this script never depends on a hand-placed copy.
if [ ! -f "$SRC/af_up.sh" ]; then
  log "afsrc missing -> provisioning from GitHub"
  mkdir -p "$SRC"
  tmp="$(mktemp -d)"
  if git clone -q --depth 1 "https://${GITHUB_TOKEN}@github.com/farmmer938-lgtm/af-m938-1-portfolio.git" "$tmp/repo" 2>>"$LOG"; then
    cp -r "$tmp/repo/m938-2/src/." "$SRC/"
  else
    log "provision FAILED (no GITHUB_TOKEN or clone error); cannot continue"
    rm -rf "$tmp"; exit 1
  fi
  rm -rf "$tmp"
fi
chmod +x "$SRC"/*.sh "$SRC"/afcashier/run.sh 2>/dev/null

# 1. Rootfs self-heal first (python3 symlink, noVNC packages, profile locks).
[ -x "$SRC/selfheal.sh" ] && bash "$SRC/selfheal.sh" >>/workspace/.selfheal.log 2>&1

# 2. Drop stale pidfiles so the loops below can re-acquire their guard. A pidfile
#    is stale when its service is not actually running (PID recycling after a
#    restart otherwise makes `kill -0` pass for an unrelated process).
is_running "node server.mjs"           || rm -f /workspace/.afcashier.pid
is_running "afcashier_loop.sh"         || rm -f /workspace/.afcashier-loop.pid
is_running "mail_watchdog_loop.sh"     || rm -f /workspace/.mail-watchdog.pid
is_running "doink_watchdog_loop.sh"    || rm -f /workspace/.doink-watchdog.pid
is_running "lazada_autopilot_loop.sh"  || rm -f /workspace/.lazada-autopilot-loop.pid
is_running "novnc_watchdog.sh"         || rm -f /workspace/.novnc-watchdog.pid
is_running "af_demand_loop.py"         || rm -f /workspace/.af-demand-loop.pid
is_running "af_x_loop.py"              || rm -f /workspace/.af-x-loop.pid

# 2b. Hydrate the durable secret store into this shell. A restarted sandbox has NO
#     OpenHands session, so every credential would otherwise be missing and the loops
#     below would die on their first os.environ lookup. af_env caches env->store too.
if [ -f /workspace/project/AX_MASTER_BRAIN/tools/af_env.py ]; then
  python3 /workspace/project/AX_MASTER_BRAIN/tools/af_env.py >>/workspace/.af-up.log 2>&1 \
    && log "secrets hydrated" || log "secret hydration reported missing keys (see af_env.py --check)"
  if [ -f /workspace/.secrets/af_master.json ]; then
    while IFS='=' read -r k v; do
      [ -n "$k" ] && export "$k=$v"
    done < <(python3 - <<'PY'
import json, os
try:
    d = json.load(open("/workspace/.secrets/af_master.json"))
    for k, raw in (d.get("secrets") or {}).items():
        v = raw if isinstance(raw, str) else (raw or {}).get("value")
        if v:
            print(f"{k}={v}")
except Exception:
    pass
PY
)
  fi
fi

# 3. noVNC desktop (Xvfb + chromium CDP :9222 + x11vnc + websockify :12001).
if ! is_running "novnc_watchdog.sh"; then
  bash "$SRC/restore_novnc.sh" >>/workspace/.novnc.log 2>&1
  setsid nohup bash "$SRC/novnc_watchdog.sh" >/dev/null 2>&1 &
  log "started novnc_watchdog"
fi

# 4. x402 cashier (the money intake). run.sh is idempotent; the loop supervises it.
if ! is_running "node server.mjs"; then
  bash "$SRC/afcashier/run.sh" >>/workspace/.afcashier.log 2>&1
  log "started cashier"
fi
if ! is_running "afcashier_loop.sh"; then
  setsid nohup bash "$SRC/afcashier_loop.sh" >/dev/null 2>&1 &
  log "started afcashier_loop"
fi

# 5. Watchdogs: mail (IMAP when the app password exists), Do.ink orders, Lazada.
is_running "mail_watchdog_loop.sh" || { setsid nohup bash "$SRC/mail_watchdog_loop.sh" >/dev/null 2>&1 & log "started mail_watchdog"; }
is_running "doink_watchdog_loop.sh" || { setsid nohup bash "$SRC/doink_watchdog_loop.sh" >/dev/null 2>&1 & log "started doink_watchdog"; }
is_running "lazada_autopilot_loop.sh" || { setsid nohup bash "$SRC/lazada_autopilot_loop.sh" >/dev/null 2>&1 & log "started lazada_autopilot"; }

# 6b. AF supervisor (watchdog-of-watchdogs): keeps every loop above alive, refreshes
#     the status file + dashboard, and starts the portfolio autopilot. Must run after
#     the loops so it can adopt them.
SUP=/workspace/project/AX_MASTER_BRAIN/af_supervisor_loop.sh
if [ -f "$SUP" ]; then
  is_running "af_supervisor_loop.sh" || { setsid nohup bash "$SUP" >/dev/null 2>&1 & log "started af_supervisor"; }
fi
PORT=/workspace/project/AX_MASTER_BRAIN/tools/af_portfolio_loop.sh
if [ -f "$PORT" ]; then
  is_running "af_portfolio_loop.sh" || { setsid nohup bash "$PORT" >/dev/null 2>&1 & log "started af_portfolio"; }
fi

# 7. Revenue products: verify the public mirror still serves every file the
#    OpenTask bids cite; re-publish from the durable git copy if missing. This
#    is what keeps bid proofs from rotting after a restart (no human needed).
GUARD=/workspace/project/AX_MASTER_BRAIN/tools/products_guard.py
if [ -f "$GUARD" ]; then
  python3 "$GUARD" >>/workspace/.products-guard.log 2>&1 && log "products-guard ran" || log "products-guard FAILED"
fi

# 7b. Publish the live public endpoint. The sandbox host embeds the container
#     RUNTIME_ID, so the cashier's public URL changes on every restart; monitors and
#     buyers resolve it from this manifest instead of remembering a stale host.
PUBLISH=/workspace/project/AX_MASTER_BRAIN/tools/af_publish_endpoint.py
if [ -f "$PUBLISH" ]; then
  python3 "$PUBLISH" >>/workspace/.endpoint-publish.log 2>&1 && log "endpoint published" || log "endpoint publish skipped"
fi

# 7c. Re-index the CURRENT origin in the x402scan discovery registry. Registration is
#     free (SIWX wallet proof, no gas); it must re-run each boot because the host changes,
#     otherwise buyers are sent to a dead URL.
XREG=/workspace/project/AX_MASTER_BRAIN/tools/af_x402scan_register.py
if [ -f "$XREG" ]; then
  python3 "$XREG" >>/workspace/.x402scan-register.log 2>&1 && log "x402scan registered" || log "x402scan register skipped"
fi

# 6. Browser autologin: once noVNC/chromium is up, log into sites the owner saved
#    once in the persistent profile. Chrome's own password manager fills the form
#    and AF clicks submit, so a restart no longer means "wait for K to log in".
AUTOLOGIN=/workspace/project/AX_MASTER_BRAIN/tools/af_autologin.py
if [ -f "$AUTOLOGIN" ]; then
  for s in lazada doink; do
    python3 "$AUTOLOGIN" "$s" >>/workspace/.autologin.log 2>&1 \
      && log "autologin $s ok" || log "autologin $s failed (see .autologin.log)"
  done
fi

# 7. Report.
up=0
for s in "node server.mjs" "afcashier_loop.sh" "mail_watchdog_loop.sh" "doink_watchdog_loop.sh" "novnc_watchdog.sh" "af_supervisor_loop.sh" "af_demand_loop.py" "af_x_loop.py"; do
  is_running "$s" && up=$((up+1)) || log "STILL DOWN: $s"
done
log "af-up done: $up/8 services running"
