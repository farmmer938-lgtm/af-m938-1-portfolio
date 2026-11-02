#!/usr/bin/env bash
# Restore the noVNC desktop after a sandbox restart (apt pkgs live in the container
# rootfs, which resets; /workspace persists). Idempotent.
set -u
need=""
for b in Xvfb x11vnc websockify openbox; do command -v $b >/dev/null || need="$need $b"; done
command -v novnc_proxy >/dev/null || [ -d /usr/share/novnc ] || need="$need novnc"
if [ -n "$need" ]; then
  echo "installing:$need"
  sudo apt-get update -qq
  sudo apt-get install -y -qq xvfb x11vnc novnc websockify openbox
fi
exec bash "$(dirname "$0")/start_novnc.sh"
