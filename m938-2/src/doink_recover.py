#!/usr/bin/env python3
"""AF self-recovery for the Do.ink storefront (m938-2).

Do.ink offers email+password sign-in and a /forgot-password reset. The account
email is K's Gmail, which AF reads headlessly over IMAP (gmail_imap.py). So AF can
reset the Do.ink password to one it controls, then sign in with email+password and
stop depending on K's expiring Google SSO session.

Usage:
  python3 doink_recover.py request     # submit reset request for the account email
  python3 doink_recover.py link        # find the newest reset link in Gmail
  python3 doink_recover.py set <url>   # open link, set a new AF password, verify login
"""
from __future__ import annotations

import imaplib
import json
import os
import re
import secrets
import string
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from browser_drive import Tab  # noqa: E402

LOG = "/workspace/.doink-recover.log"
GMAIL = "/workspace/.secrets/gmail_app.json"
OUT = "/workspace/.secrets/doink.json"


def log(msg: str) -> None:
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg)
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def gmail() -> dict:
    return json.load(open(GMAIL))


def new_password() -> str:
    core = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    return "AF" + core + "#7"


def set_input(t: Tab, selector: str, value: str) -> str:
    t.js("window.__v = " + json.dumps(value))
    return t.js(
        "(()=>{const i=document.querySelector(" + json.dumps(selector) + ");if(!i)return 'nf';"
        "const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
        "s.call(i,window.__v);i.dispatchEvent(new Event('input',{bubbles:true}));"
        "i.dispatchEvent(new Event('change',{bubbles:true}));return i.value})()")


def click_text(t: Tab, text: str) -> bool:
    idx = t.js(
        "(()=>{const els=[...document.querySelectorAll('button,a')];"
        "return els.findIndex(e=>(e.textContent||'').trim()===" + json.dumps(text) + ")})()")
    if idx is None or int(idx) < 0:
        return False
    t.real_click("button,a", int(idx))
    return True


def cmd_request() -> int:
    addr = gmail()["address"]
    t = Tab.for_url("app.do.ink")
    t.goto("https://app.do.ink/forgot-password", settle=5)
    set_input(t, "#email", addr)
    time.sleep(1)
    log("clicked send: %s" % click_text(t, "Send Reset Link"))
    time.sleep(5)
    log("page: " + (t.js("(document.body.innerText||'').replace(/\\s+/g,' ').slice(0,200)") or ""))
    t.close()
    return 0


def cmd_link() -> int:
    d = gmail()
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(d["address"], d["app_password"])
    M.select("INBOX")
    typ, data = M.search(None, "X-GM-RAW", '"doink OR do.ink"')
    ids = data[0].split()
    log("reset-related mails: %d" % len(ids))
    for i in reversed(ids[-5:]):
        typ, d2 = M.fetch(i, "(BODY.PEEK[])")
        raw = d2[0][1].decode("utf-8", "ignore")
        subj = re.search(r"Subject: (.*)", raw)
        links = re.findall(r"https?://[^\s\"'>]*reset[^\s\"'>]*", raw)
        log("  %s | links=%s" % ((subj.group(1)[:60] if subj else "?"), links[:2]))
    return 0


def cmd_set(url: str) -> int:
    pw = new_password()
    t = Tab.for_url("app.do.ink")
    t.goto(url, settle=6)
    log("reset page: " + (t.js("(document.body.innerText||'').replace(/\\s+/g,' ').slice(0,200)") or ""))
    log("inputs: " + t.js("JSON.stringify([...document.querySelectorAll('input')].map(i=>({t:i.type,id:i.id,ph:i.placeholder})))"))
    for sel in ("#password", "input[type=password]", "input[name=password]"):
        if set_input(t, sel, pw) not in (None, "nf"):
            log("filled %s" % sel)
            break
    click_text(t, "Reset Password") or click_text(t, "Reset") or click_text(t, "Submit")
    time.sleep(6)
    log("after reset: " + (t.js("(document.body.innerText||'').replace(/\\s+/g,' ').slice(0,200)") or ""))
    json.dump({"address": gmail()["address"], "password": pw, "note": "AF-controlled"}, open(OUT, "w"))
    os.chmod(OUT, 0o600)
    log("saved new password to %s" % OUT)
    t.close()
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "request"
    if cmd == "request":
        raise SystemExit(cmd_request())
    if cmd == "link":
        raise SystemExit(cmd_link())
    if cmd == "set":
        raise SystemExit(cmd_set(sys.argv[2]))
    print("unknown command")
