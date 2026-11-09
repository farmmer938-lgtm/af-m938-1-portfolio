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
from af_notify import alert  # noqa: E402

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
        # Self-heal instead of nagging a human: the persistent profile holds the saved
        # login, so re-run autologin and retry once before giving up.
        import subprocess
        subprocess.run(["python3", "/workspace/project/AX_MASTER_BRAIN/tools/af_autologin.py", "doink"],
                       capture_output=True, timeout=120)
        t = Tab.for_url("app.do.ink")
        counts = read_counts(t)
        total = counts.get("ทั้งหมด", 0)
    if counts.get("_session"):
        log("SESSION EXPIRED: Do.ink sign-in screen; autologin did not restore it (AF blocker, no human step)")
        alert("doink-session-expired",
              "AF: Do.ink session expired — autologin could not restore it",
              "The Do.ink watchdog found the sign-in screen and its autologin (cookies then "
              "password) did not restore the session.\n\nAF will keep retrying each cycle. "
              "No human step is required; this is a self-heal blocker.")
        return 1
    log("orders: %s" % json.dumps({k: v for k, v in counts.items() if not k.startswith("_")}, ensure_ascii=False))
    if total > 0:
        rows = t.js("""[...document.querySelectorAll('a[href*="/orders/"]')].map(a=>a.innerText.replace(/\\s+/g,' ').slice(0,80)).slice(0,5)""")
        payload = {"detected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "counts": counts, "rows": rows}
        with open(FIRST, "w") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        log("*** FIRST ORDER DETECTED *** %s" % json.dumps(payload, ensure_ascii=False)[:400])
        alert("doink-first-order",
              "AF: FIRST Do.ink order detected",
              "An order appeared on the Do.ink storefront. This is the mission's first real "
              "revenue signal.\n\n```json\n%s\n```" % json.dumps(payload, ensure_ascii=False, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
