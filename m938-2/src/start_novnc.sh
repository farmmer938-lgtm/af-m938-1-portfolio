#!/usr/bin/env bash
# Visible desktop + Chromium so K can log in through noVNC (port 12001) to sites
# AF cannot sign into. Idempotent. AF then drives this browser over CDP (:9222).
export DISPLAY=:99

pgrep -f "Xvfb :99" >/dev/null || {
  setsid Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp >/tmp/xvfb.log 2>&1 < /dev/null &
  sleep 2
}

pgrep -x openbox >/dev/null || {
  setsid openbox >/tmp/openbox.log 2>&1 < /dev/null &
  sleep 1
}

pgrep -f "chrome-novnc" >/dev/null || {
  setsid chromium --no-sandbox --disable-gpu --start-maximized --no-first-run \
    --remote-debugging-port=9222 --remote-allow-origins=* \
    --user-data-dir=/workspace/.novnc-profile --window-size=1920,1080 \
    "https://app.do.ink/" >/tmp/chromium-novnc.log 2>&1 < /dev/null &
  sleep 4
}

x11vnc -storepasswd af938pod /tmp/x11vnc.pass >/dev/null 2>&1
pgrep -f "x11vnc -display :99" >/dev/null || {
  setsid x11vnc -display :99 -rfbport 5900 -rfbauth /tmp/x11vnc.pass \
    -forever -shared -localhost -quiet >/tmp/x11vnc.log 2>&1 < /dev/null &
  sleep 1
}

pgrep -f "websockify 12001" >/dev/null || {
  setsid websockify 12001 --web /usr/share/novnc 127.0.0.1:5900 >/tmp/websockify.log 2>&1 < /dev/null &
  sleep 1
}

echo "noVNC ready on port 12001 (DISPLAY :99)"
