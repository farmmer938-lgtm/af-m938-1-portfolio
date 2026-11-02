#!/usr/bin/env bash
# Visible desktop + Chromium for K to log in to sites AF cannot (noVNC on port 12001).
export DISPLAY=:99
pgrep -f "Xvfb :99" >/dev/null || { setsid Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp >/tmp/xvfb.log 2>&1 < /dev/null & sleep 2; }
pgrep -x openbox >/dev/null || { setsid openbox >/tmp/openbox.log 2>&1 < /dev/null & sleep 1; }
pgrep -f "chrome-novnc" >/dev/null || {
  setsid chromium --no-sandbox --disable-gpu --start-maximized --no-first-run \
    --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=/tmp/chrome-novnc \
    --window-size=1920,1080 about:blank >/tmp/chromium-novnc.log 2>&1 < /dev/null & sleep 4; }
pgrep -f "x11vnc -display :99" >/dev/null || { setsid x11vnc -display :99 -rfbport 5900 -nopw -forever -shared -localhost -quiet >/tmp/x11vnc.log 2>&1 < /dev/null & sleep 1; }
pgrep -f "websockify 12001" >/dev/null || { setsid websockify 12001 --web /usr/share/novnc 127.0.0.1:5900 >/tmp/websockify.log 2>&1 < /dev/null & sleep 1; }
echo "noVNC ready on port 12001 (DISPLAY :99)"
