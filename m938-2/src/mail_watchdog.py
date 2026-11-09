#!/usr/bin/env python3
"""Mailbox watchdog: surface new, actionable email from the noVNC Gmail session.

K's standing instruction is to watch every mailbox AF uses. Order confirmations,
payment notices and verification links all arrive by email, so this is the second
tripwire next to the Do.ink order watchdog. Reads the logged-in Gmail over CDP,
diffs the inbox subjects against the last seen set, and flags anything that looks
like it needs action.

Run every N minutes (see mail_watchdog_loop.sh). Log: /workspace/.mail-watch.log
State: /workspace/.mail-seen.json
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

LOG = "/workspace/.mail-watch.log"
SEEN = "/workspace/.mail-seen.json"
ALERTS = "/workspace/.mail-alerts.json"
INBOX = "https://mail.google.com/mail/u/0/#inbox"

# Order/payment/verification mail that AF should act on rather than skim.
HOT = re.compile(
    r"คำสั่งซื้อ|order|payment|การรับเงิน|ค่าคอมมิชชั่น|commission|ยืนยัน|verify|verification|"
    r"อนุมัติ|approved|ปฏิเสธ|reject|แจ้งเตือนความปลอดภัย|security alert",
    re.I,
)


def log(msg: str) -> None:
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg)
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def ensure_stack() -> None:
    subprocess.run(["bash", os.path.join(HERE, "start_novnc.sh")], capture_output=True, timeout=180)


def read_inbox(t: Tab) -> list[dict]:
    t.goto(INBOX, settle=7)
    if t.js("/Sign in|เข้าสู่ระบบ/i.test(document.body.innerText) && /Choose an account|เลือกบัญชี/i.test(document.body.innerText)"):
        return []
    rows = t.js(
        """JSON.stringify([...document.querySelectorAll('tr.zA')].slice(0,15).map(r=>({
            id:(r.querySelector('a')||{}).href||'',
            unread:r.classList.contains('zE'),
            text:(r.innerText||'').replace(/\\s+/g,' ').trim().slice(0,140)
        })))"""
    )
    try:
        return json.loads(rows or "[]")
    except Exception:
        return []


def main() -> int:
    ensure_stack()
    t = Tab.for_url("mail.google.com")
    msgs = read_inbox(t)
    if not msgs:
        log("GMAIL UNAVAILABLE via browser; IMAP path (gmail_imap.py) is the durable one — no human step")
        return 0
    try:
        seen = set(json.load(open(SEEN)))
    except Exception:
        seen = set()
    fresh, alerts = [], []
    for m in msgs:
        key = (m.get("text") or "")[:90]
        if not key or key in seen:
            continue
        fresh.append(key)
        if HOT.search(key):
            alerts.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "unread": m.get("unread"), "text": m.get("text")})
    seen.update(fresh)
    json.dump(sorted(seen)[-300:], open(SEEN, "w"), ensure_ascii=False)
    log("inbox: %d shown, %d new, %d flagged" % (len(msgs), len(fresh), len(alerts)))
    for a in alerts:
        log("  FLAG: %s" % a["text"][:120])
    if alerts:
        try:
            old = json.load(open(ALERTS))
        except Exception:
            old = []
        json.dump((old + alerts)[-100:], open(ALERTS, "w"), ensure_ascii=False, indent=1)
        try:
            from af_notify import alert
            for a in alerts[:5]:
                text = (a.get("text") or "").strip()
                slug = "mail-" + re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-")
                alert(slug, "AF: actionable mail — %s" % text[:70],
                      "The mailbox watchdog flagged this message as needing action.\n\n> %s" % text)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
