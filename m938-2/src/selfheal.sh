#!/usr/bin/env bash
# Idempotent environment self-heal for AF's container.
# The rootfs is wiped on every restart (apt/pip packages, /usr/bin symlinks,
# running processes) while /workspace survives. This runs first on every boot so
# the rest of af_boot.sh can rely on a working `python3`, the noVNC packages and a
# clean Chromium profile. Safe to run repeatedly. Log: /workspace/.selfheal.log
set -u
LOG=/workspace/.selfheal.log
log() { echo "$(date -Is) $*" | tee -a "$LOG"; }

# 1. `python3` must resolve. On this image a restart can leave /usr/bin/python3 a
#    dangling symlink while the real interpreter lives in /usr/local/bin. Repair it
#    so every loop script that calls bare `python3` keeps working.
if ! python3 -c "pass" >/dev/null 2>&1; then
  REAL="$(command -v python3.13 || command -v python3.12 || command -v python3.11 || true)"
  if [ -n "$REAL" ] && [ -w /usr/bin ]; then
    ln -sf "$REAL" /usr/bin/python3 && log "repaired /usr/bin/python3 -> $REAL"
  fi
fi

# 2. noVNC desktop packages live in the rootfs and vanish on restart.
need=""
for b in Xvfb x11vnc websockify openbox; do command -v "$b" >/dev/null 2>&1 || need="$need $b"; done
[ -d /usr/share/novnc ] || need="$need novnc"
if [ -n "$need" ]; then
  log "installing:$need"
  SUDO=""; [ "$(id -u)" != "0" ] && SUDO="sudo"
  $SUDO mkdir -p /var/lib/apt/lists/partial 2>/dev/null
  # snapshot.debian.org is frequently rate-limited (503 TooManyRequests); retry a
  # few times before giving up, and never abort the boot on a failed install.
  ok=0
  for i in 1 2 3 4 5; do
    $SUDO apt-get update -qq >>"$LOG" 2>&1
    if $SUDO apt-get install -y -qq --fix-missing xvfb x11vnc novnc websockify openbox >>"$LOG" 2>&1; then
      ok=1; break
    fi
    log "apt attempt $i failed; retrying in 20s"
    sleep 20
  done
  [ "$ok" = 1 ] && log "noVNC packages installed" || log "apt install failed (will retry next boot)"
fi

# 3. A killed Chromium leaves Singleton locks that stop the next launch from
#    reusing the profile, which forces a fresh (logged-out) session.
rm -f /workspace/.novnc-profile/Singleton* 2>/dev/null

# 4. Python deps AF's drivers need, when missing.
python3 -c "import websocket" >/dev/null 2>&1 || pip install -q websocket-client >>"$LOG" 2>&1 || true

# 5. Gmail API deps, only once K has dropped the OAuth client secret in place.
if [ -f /workspace/.secrets/gmail_client.json ] && ! python3 -c "import google_auth_oauthlib" >/dev/null 2>&1; then
  pip install -q google-auth-oauthlib google-api-python-client >>"$LOG" 2>&1 || true
fi

log "self-heal done"
