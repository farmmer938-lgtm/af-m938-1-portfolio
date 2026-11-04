#!/usr/bin/env python3
"""Revenue watchdog for the Do.ink storefront (project m938-2).

The mission target is the FIRST verified sale. Nothing else on the machine can
detect that, so this polls the Do.ink orders page in the logged-in noVNC Chromium
and shouts (log + a marker file) the moment an order appears.

Run every N minutes (see doink_watchdog_loop.sh). Log: /workspace/.doink-orders.log
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from browser_drive import Tab  # noqa: E402

LOG = "/workspace/.doink-orders.log"
FIRST = "/workspace/.doink-first-order.json"
ORDERS_URL = "https://app.do.ink/orders"

_LABELS = ["ทั้งหมด", "รอชำระเงิน", "รอดำเนินการ", "กำลังผลิต", "จัดส่งแล้ว", "ยกเลิกแล้ว"]


def log(msg: str) -> None:
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg)
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def ensure_stack() -> None:
    subprocess.run(["bash", os.path.join(HERE, "start_novnc.sh")], capture_output=True, timeout=180)


def read_counts(t: Tab) -> dict:
    t.goto(ORDERS_URL, settle=6)
    txt = t.js("(document.querySelector('main')||document.body).innerText.replace(/\\s+/g,' ')") or ""
    counts = {}
    for lab in _LABELS:
        m = re.search(re.escape(lab) + r"\s*(\d+)", txt)
        if m:
            counts[lab] = int(m.group(1))
    counts["_empty"] = "ยังไม่มีคำสั่งซื้อ" in txt
    # Do.ink bounces a logged-out visitor to the sign-in screen. Without this flag an
    # expired session would log "orders: {}" and read exactly like zero orders.
    counts["_session"] = "Sign in to your account" in txt or "Welcome back" in txt
    return counts


def main() -> int:
    ensure_stack()
    t = Tab.for_url("app.do.ink")
    counts = read_counts(t)
    total = counts.get("ทั้งหมด", 0)
    if counts.get("_session"):
        log("SESSION EXPIRED: Do.ink is showing the sign-in screen; order data unavailable (K must log in via noVNC)")
        return 0
    log("orders: %s" % json.dumps({k: v for k, v in counts.items() if not k.startswith("_")}, ensure_ascii=False))
    if total > 0:
        rows = t.js("""[...document.querySelectorAll('a[href*="/orders/"]')].map(a=>a.innerText.replace(/\\s+/g,' ').slice(0,80)).slice(0,5)""")
        payload = {"detected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "counts": counts, "rows": rows}
        with open(FIRST, "w") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        log("*** FIRST ORDER DETECTED *** %s" % json.dumps(payload, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
