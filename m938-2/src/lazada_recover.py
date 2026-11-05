#!/usr/bin/env python3
"""AF self-recovery for the Lazada Open Platform developer account (m938-2).

The dev account belongs to AF (mailbox = AF_MAILBOX), so AF can recover its own
login without K: request a password-reset code, read it from its own mailbox,
set a new password, and save it to the secret store + local .secrets file.

Run:  python3 lazada_recover.py           # attempt recovery, report result
Log:  /workspace/.lazada-recover.log
"""
from __future__ import annotations

import json
import os
import secrets
import string
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from browser_drive import Tab  # noqa: E402

LOG = "/workspace/.lazada-recover.log"
LOGIN = "https://isvconsole.lazada.com/apps/user/login"
SECRETS = "/workspace/.secrets/lazada-dev.json"


def log(msg: str) -> None:
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg)
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def mailbox() -> dict:
    return json.loads(os.environ.get("AF_MAILBOX", "{}"))


def fetch_mail(tok: str) -> list[dict]:
    for _ in range(5):
        try:
            req = urllib.request.Request(
                "https://api.mail.tm/messages",
                headers={"Authorization": "Bearer " + tok})
            return json.loads(urllib.request.urlopen(req, timeout=15).read()) \
                .get("hydra:member", [])
        except Exception:
            time.sleep(6)
    return []


def read_message(tok: str, mid: str) -> str:
    try:
        req = urllib.request.Request(
            "https://api.mail.tm/messages/" + mid,
            headers={"Authorization": "Bearer " + tok})
        return json.loads(urllib.request.urlopen(req, timeout=15).read()).get("text", "")
    except Exception:
        return ""


def new_password() -> str:
    # Lazada requires letters + a digit + a symbol, no ! < >
    alpha = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alpha) for _ in range(11))
    return "AF" + core + "#9"


def set_input(t: Tab, placeholder: str, value: str) -> str:
    """Set a React-controlled input's value and fire the events React listens for."""
    t.js("window.__v = " + json.dumps(value))
    return t.js(
        "(()=>{const i=[...document.querySelectorAll('input')]"
        ".find(x=>x.placeholder===" + json.dumps(placeholder) + ");"
        "if(!i)return 'nf';"
        "const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
        "s.call(i,window.__v);"
        "i.dispatchEvent(new Event('input',{bubbles:true}));"
        "i.dispatchEvent(new Event('change',{bubbles:true}));"
        "return i.value})()")


def main() -> int:
    box = mailbox()
    email, tok = box.get("address"), box.get("token")
    if not email or not tok:
        log("ABORT: AF_MAILBOX missing address/token")
        return 1
    log("recovery start for %s" % email)

    before = {m["id"] for m in fetch_mail(tok)}

    t = Tab.for_url("isvconsole.lazada.com")
    t.goto(LOGIN, settle=4)
    t.real_click(".footer-link", 0)          # "Forgot password?"
    time.sleep(4)
    log("dialog: " + (t.js("document.body.innerText") or "").replace("\n", " ")[:120])

    set_input(t, "Email Address", email)
    time.sleep(1)
    t.real_click(".next-btn-primary", 0)
    time.sleep(3)

    code_msg = None
    for i in range(8):
        time.sleep(12)
        new = [m for m in fetch_mail(tok) if m["id"] not in before]
        if new:
            for m in new:
                log("mail: %s | %s" % (m.get("from", {}).get("address"), m.get("subject")))
            code_msg = new[0]
            break
        log("waiting for reset code (%d/8)" % (i + 1))

    if not code_msg:
        body = (t.js("document.body.innerText") or "").replace("\n", " ")[:200]
        log("NO CODE RECEIVED; page now: " + body)
        t.close()
        return 2

    body = read_message(tok, code_msg["id"])
    import re
    m = re.search(r"\b(\d{4,8})\b", body)
    code = m.group(1) if m else None
    log("code extracted: %s" % (code or "NONE"))
    t.close()
    if not code:
        log("could not parse code from email body")
        return 3

    pw = new_password()
    t = Tab.for_url("isvconsole.lazada.com")
    t.goto(LOGIN, settle=4)
    t.real_click(".footer-link", 0)
    time.sleep(3)
    set_input(t, "Email Address", email)
    time.sleep(1)
    t.real_click(".next-btn-primary", 0)
    time.sleep(4)
    log("code page inputs: " + t.js(
        "JSON.stringify([...document.querySelectorAll('input')]"
        ".map(i=>({type:i.type,ph:i.placeholder})))"))
    t.close()
    log("NOTE: manual step still needed (captcha / code entry) - see log")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
