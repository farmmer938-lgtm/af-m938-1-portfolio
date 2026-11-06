#!/usr/bin/env bash
# Visible desktop + Chromium so K can log in through noVNC (port 12001) to sites
# AF cannot sign into. Idempotent. AF then drives this browser over CDP (:9222).
export DISPLAY=:99

# PID 1 (openhands-agent) never reaps, so dead children stay as zombies and `pgrep`
# still matches them. "alive" ignores zombies; otherwise we skip starting a process
# that is actually gone (this left a stale /tmp/.X99-lock and a dead X server).
alive() {
  local p st
  for p in $(pgrep -f "$1" 2>/dev/null); do
    st=$(ps -o stat= -p "$p" 2>/dev/null)
    case "$st" in Z*|"") ;; *) return 0 ;; esac
  done
  return 1
}


# Xvfb needs `xkbcomp` (package x11-xkb-utils) to compile its keymap. Without it Xvfb dies
# with "Failed to activate virtual core keyboard" -> no X server -> Chromium crashes ->
# CDP :9222 and the noVNC desktop go down. Self-heal the package so the desktop survives a
# rebuilt container (a fresh image can ship xkb-data but not x11-xkb-utils).
if ! command -v xkbcomp >/dev/null 2>&1; then
  sudo apt-get install -y -qq x11-xkb-utils >/dev/null 2>&1 || {
    ( cd /tmp && curl -s -m 60 -O \
      http://deb.debian.org/debian/pool/main/x/x11-xkb-utils/x11-xkb-utils_7.7+9_amd64.deb \
      && sudo dpkg -i x11-xkb-utils_7.7+9_amd64.deb ) >/dev/null 2>&1
  }
fi

if ! alive "Xvfb :99"; then
  rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
  setsid Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp >/tmp/xvfb.log 2>&1 < /dev/null &
  sleep 2
fi

alive "openbox" || {
  setsid openbox >/tmp/openbox.log 2>&1 < /dev/null &
  sleep 1
}

alive "chrome-novnc" || alive "remote-debugging-port=9222" || {
  setsid chromium --no-sandbox --disable-gpu --start-maximized --no-first-run \
    --remote-debugging-port=9222 --remote-allow-origins=* \
    --user-data-dir=/workspace/.novnc-profile --window-size=1920,1080 \
    "https://app.do.ink/" >/tmp/chromium-novnc.log 2>&1 < /dev/null &
  sleep 4
}

x11vnc -storepasswd af938pod /tmp/x11vnc.pass >/dev/null 2>&1
alive "x11vnc -display :99" || {
  setsid x11vnc -display :99 -rfbport 5900 -rfbauth /tmp/x11vnc.pass \
    -forever -shared -localhost -quiet >/tmp/x11vnc.log 2>&1 < /dev/null &
  sleep 1
}

alive "websockify 12001" || {
  setsid websockify 12001 --web /usr/share/novnc 127.0.0.1:5900 >/tmp/websockify.log 2>&1 < /dev/null &
  sleep 1
}

echo "noVNC ready on port 12001 (DISPLAY :99)"
