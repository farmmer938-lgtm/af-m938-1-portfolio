#!/usr/bin/env bash
# Bring AF's unattended m938-2 services back after a container restart.
# A restart wipes the container rootfs (apt/pip pkgs, processes) but keeps /workspace,
# so this reinstalls what's missing and relaunches everything. Idempotent.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"

# 1. noVNC desktop (Xvfb + chromium CDP :9222 + x11vnc + websockify :12001)
bash "$HERE/restore_novnc.sh"
rm -f /workspace/.novnc-restored

# 2. noVNC watchdog (self-heals the desktop)
pgrep -f novnc-watchdog.sh >/dev/null || setsid nohup /workspace/.novnc-watchdog.sh >/dev/null 2>&1 &

# 3. Lazada onboarding autopilot (creates the app once the profile is approved)
python3 -c "import websocket" 2>/dev/null || pip install -q websocket-client
setsid nohup bash "$HERE/lazada_autopilot_loop.sh" >/dev/null 2>&1 &

# 4. Do.ink order watchdog (the storefront is live; this is the revenue tripwire)
setsid nohup bash "$HERE/doink_watchdog_loop.sh" >/dev/null 2>&1 &

echo "AF m938-2 services booted"
