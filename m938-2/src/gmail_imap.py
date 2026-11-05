#!/usr/bin/env python3
"""Read K's Gmail headlessly over IMAP using an app password.

Replaces the noVNC/browser scraping path (mail_watchdog.py) which loses the
session on every container restart. IMAP needs no browser, no OAuth consent
screen and no Google Cloud project: K creates one app password once, AF stores
it, and reading survives every restart.

Setup (one time, K): enable 2-Step Verification, then
https://myaccount.google.com/apppasswords -> create "AF" -> copy the 16-char code.
Store it as JSON {"address": "...@gmail.com", "app_password": "xxxxxxxxxxxxxxxx"}
in /workspace/.secrets/gmail_app.json (chmod 600).

Usage:
  python3 gmail_imap.py check     # verify login, print INBOX count
  python3 gmail_imap.py read      # diff INBOX vs seen set, flag actionable mail
Output (same contract as mail_watchdog.py): /workspace/.mail-seen.json,
/workspace/.mail-alerts.json, log /workspace/.mail-watch.log
"""
from __future__ import annotations

import email
import imaplib
import json
import os
import re
import sys
import time
from email.header import decode_header

CRED = os.environ.get("GMAIL_APP_CRED", "/workspace/.secrets/gmail_app.json")
LOG = "/workspace/.mail-watch.log"
SEEN = "/workspace/.mail-seen.json"
ALERTS = "/workspace/.mail-alerts.json"
HOST = "imap.gmail.com"

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


def _load():
    if not os.path.exists(CRED):
        sys.exit(
            f"missing {CRED}: K must create a Gmail app password at "
            "https://myaccount.google.com/apppasswords and store "
            '{"address":"...@gmail.com","app_password":"xxxxxxxxxxxxxxxx"} there'
        )
    with open(CRED) as f:
        d = json.load(f)
    return d["address"], d["app_password"].replace(" ", "")


def connect():
    address, pw = _load()
    m = imaplib.IMAP4_SSL(HOST)
    m.login(address, pw)
    return m


def _decode(raw: str) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", "replace"))
        else:
            out.append(text)
    return "".join(out)


def fetch_headers(m, limit: int = 20):
    m.select("INBOX", readonly=True)
    typ, data = m.search(None, "ALL")
    ids = data[0].split()[-limit:]
    rows = []
    for i in reversed(ids):
        typ, msg_data = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        rows.append({
            "from": _decode(msg.get("From", "")),
            "subject": _decode(msg.get("Subject", "")),
            "date": msg.get("Date", ""),
        })
    return rows


def cmd_check() -> int:
    m = connect()
    m.select("INBOX", readonly=True)
    typ, data = m.search(None, "ALL")
    print(f"login OK; INBOX has {len(data[0].split())} messages")
    m.logout()
    return 0


def cmd_read() -> int:
    m = connect()
    rows = fetch_headers(m)
    m.logout()
    if not rows:
        log("inbox empty")
        return 0
    try:
        seen = set(json.load(open(SEEN)))
    except Exception:
        seen = set()
    fresh, alerts = [], []
    for r in rows:
        key = ("%s | %s" % (r["from"][:40], r["subject"]))[:90]
        if not key or key in seen:
            continue
        fresh.append(key)
        if HOT.search(key):
            alerts.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "text": key})
    seen.update(fresh)
    json.dump(sorted(seen)[-300:], open(SEEN, "w"), ensure_ascii=False)
    log("inbox: %d shown, %d new, %d flagged" % (len(rows), len(fresh), len(alerts)))
    for a in alerts:
        log("  FLAG: %s" % a["text"][:120])
    if alerts:
        try:
            old = json.load(open(ALERTS))
        except Exception:
            old = []
        json.dump((old + alerts)[-100:], open(ALERTS, "w"), ensure_ascii=False, indent=1)
    return 0


def cmd_set(address: str, password: str) -> int:
    os.makedirs(os.path.dirname(CRED), exist_ok=True)
    pw = password.replace(" ", "")
    with open(CRED, "w") as f:
        json.dump({"address": address, "app_password": pw}, f)
    os.chmod(CRED, 0o600)
    print(f"saved {address} -> {CRED} (app password {len(pw)} chars)")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "check":
        return cmd_check()
    if cmd == "read":
        return cmd_read()
    if cmd == "set":
        return cmd_set(sys.argv[2], sys.argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
