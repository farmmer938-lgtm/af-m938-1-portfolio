#!/usr/bin/env python3
"""Session-health checker for the m938-2 browser-bound services (m938-2).

The Do.ink storefront (K's Google SSO) and the Lazada ISV console are driven
through one shared Chromium profile. When a session expires the watchdogs go
blind; this checker states exactly which session is alive so the alert to K is
precise instead of a generic "log in" nag.

Writes /workspace/.session-health.json and appends to /workspace/.session-health.log.
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from browser_drive import Tab  # noqa: E402

OUT = "/workspace/.session-health.json"
LOG = "/workspace/.session-health.log"


def log(msg: str) -> None:
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg)
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def doink(t: Tab) -> bool:
    t.goto("https://app.do.ink/orders", settle=6)
    txt = t.js("(document.body.innerText||'').replace(/\\s+/g,' ')") or ""
    if "Sign in to your account" in txt or "Welcome back" in txt:
        return False
    return "ทั้งหมด" in txt or "คำสั่งซื้อ" in txt


def lazada(t: Tab) -> bool:
    t.goto("https://isvconsole.lazada.com/apps/console/apps", settle=6)
    url = t.js("location.href") or ""
    return "login" not in url.lower()


def main() -> int:
    t = Tab.for_url("app.do.ink")
    st = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        st["doink"] = "alive" if doink(t) else "expired"
    except Exception as e:
        st["doink"] = "error:%s" % type(e).__name__
    try:
        st["lazada"] = "alive" if lazada(t) else "expired"
    except Exception as e:
        st["lazada"] = "error:%s" % type(e).__name__
    t.close()
    st["needs_k"] = [k for k in ("doink", "lazada") if st[k] == "expired"]
    json.dump(st, open(OUT, "w"), indent=1)
    log("doink=%s lazada=%s needs_k=%s" % (st["doink"], st["lazada"], st["needs_k"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
