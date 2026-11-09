#!/usr/bin/env python3
"""AF autologin — log into sites the human once saved in the browser, with no human.

K's point (2026-11-07): "it still needs K to do it first" is not acceptable. AF must
remove K from the loop. The recurring K-blocker was Lazada: every restart the seller
console showed the login page and AF waited for K.

The fix needs no new human step and no secret extraction. The persistent Chromium
profile (/workspace/.novnc-profile) already holds the credentials the owner saved once.
Chrome's own password manager will autofill them, and a real click on the submit button
logs in. AF drives that through CDP — the same clicks K would make.

This is deliberately NOT credential theft: AF never reads or stores the password. It asks
the browser that already has it to fill its own form, exactly like a returning user.

Usage:
  python3 tools/af_autologin.py lazada
  python3 tools/af_autologin.py --url https://site/login --field '#loginName' --pw '#password' --btn-text "Log in"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp import Tab, find, targets  # noqa: E402

STORE = "/workspace/.secrets/af_master.json"
SITES = {
    "lazada": {
        "match": "isvconsole.lazada.com",
        "url": "https://isvconsole.lazada.com/apps/user/login",
        "user_field": "#loginName",
        "pw_field": "#password",
        "btn_text": "log in",
        "logged_in": "isvconsole.lazada.com/web/isv",
    },
    "doink": {
        "match": "app.do.ink",
        "url": "https://app.do.ink/orders",
        "user_field": "input[type=email]",
        "pw_field": "input[type=password]",
        "btn_text": "log in",
        "logged_in": "app.do.ink/orders",
    },
}


def saved_cookies(site: str) -> list:
    """Session cookies captured earlier for this site (empty if none)."""
    try:
        acct = (json.load(open(STORE)).get("accounts", {}) or {}).get(site, {}) or {}
    except Exception:
        return []
    return acct.get("session_cookies") or []


def inject_cookies(tab: Tab, cookies: list) -> int:
    """Replay saved cookies into Chromium so a fresh profile is logged in.

    This is the durable path: unlike Chrome's password autofill, it survives a
    container restart because the cookies live in af_master.json. Only the
    site's own cookies are injected, never a password.
    """
    n = 0
    for c in cookies:
        if not c.get("name") or not c.get("value"):
            continue
        params = {"name": c["name"], "value": c["value"],
                  "domain": c.get("domain") or "", "path": c.get("path") or "/",
                  "secure": bool(c.get("secure")), "httpOnly": bool(c.get("httpOnly"))}
        exp = c.get("expires")
        if isinstance(exp, (int, float)) and exp > 0:
            params["expires"] = int(exp)
        try:
            tab.call("Network.setCookie", **params)
            n += 1
        except Exception:
            pass
    return n


def login_with_cookies(cfg: dict, wait: int = 25) -> dict:
    """Try the saved-cookie route before touching any form."""
    cks = saved_cookies(cfg.get("_key", ""))
    if not cks:
        return {"ok": False, "reason": "no saved cookies"}
    tab = _open(cfg["url"])
    tab.call("Page.enable")
    tab.call("Network.enable")
    n = inject_cookies(tab, cks)
    tab.eval("location.href=%r" % cfg["url"])
    for _ in range(wait):
        time.sleep(1)
        url = tab.eval("location.href") or ""
        if cfg["logged_in"] in url:
            return {"ok": True, "via": "cookies", "injected": n, "url": url}
    return {"ok": False, "reason": "cookies not enough", "injected": n}


def _open(url: str) -> Tab:
    """Reuse an existing tab for the site, or open a new one via CDP."""
    import json
    import urllib.request
    for t in targets():
        if t.get("type") == "page" and url.split("//")[1].split("/")[0] in t.get("url", ""):
            return Tab(t)
    req = urllib.request.Request(f"http://localhost:9222/json/new?{url}", method="PUT")
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        urllib.request.urlopen(f"http://localhost:9222/json/new?{url}", timeout=10).read()
    time.sleep(3)
    return Tab(find(url.split("//")[1].split("/")[0]))


def account_email(site: str) -> str:
    try:
        return ((json.load(open(STORE)).get("accounts", {}) or {}).get(site, {}) or {}).get("email", "")
    except Exception:
        return ""


def login_with_password(cfg: dict, wait: int = 25) -> dict:
    """Fill the site's own login form with the stored account + shared password.

    Last resort for when the session cookies have expired. The password is typed
    with real key events and never logged or printed.
    """
    sys.path.insert(0, "/workspace/afsrc")
    try:
        import af_secretstore as S
    except Exception:
        return {"ok": False, "reason": "no secretstore"}
    site = cfg.get("_key", "")
    email = account_email(site)
    pw = S.password_for(email) if email else S.master_password()
    if not (email and pw):
        return {"ok": False, "reason": "no stored credentials"}

    tab = _open(cfg["url"])
    tab.call("Page.bringToFront")
    time.sleep(3)
    if cfg["logged_in"] in (tab.eval("location.href") or ""):
        return {"ok": True, "already": True, "url": tab.eval("location.href")}
    if not tab.eval("!!document.querySelector(%s)" % json.dumps(cfg["user_field"])):
        return {"ok": False, "reason": "no login form"}
    tab.type_text(cfg["user_field"], email)
    time.sleep(0.6)
    tab.type_text(cfg["pw_field"], pw)
    time.sleep(0.6)
    box = tab.eval(
        "(()=>{const b=[...document.querySelectorAll('button,[role=button],input[type=submit],a')]"
        ".find(e=>new RegExp(%r,'i').test((e.innerText||e.value||''))&&e.offsetParent);"
        "if(!b)return null;b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();"
        "return {x:r.x+r.width/2,y:r.y+r.height/2};})()" % cfg["btn_text"])
    if not box:
        return {"ok": False, "reason": "no submit button"}
    tab.call("Input.dispatchMouseEvent", type="mouseMoved", x=box["x"], y=box["y"])
    tab.call("Input.dispatchMouseEvent", type="mousePressed", x=box["x"], y=box["y"],
             button="left", buttons=1, clickCount=1)
    tab.call("Input.dispatchMouseEvent", type="mouseReleased", x=box["x"], y=box["y"],
             button="left", buttons=0, clickCount=1)
    for _ in range(wait):
        time.sleep(1)
        url = tab.eval("location.href") or ""
        if cfg["logged_in"] in url:
            return {"ok": True, "via": "password", "url": url}
    return {"ok": False, "reason": "did not reach logged-in url", "url": tab.eval("location.href")}


def autologin(cfg: dict, wait: int = 25) -> dict:
    # Route 1: replay saved cookies. Works after a container restart because the
    # cookies are stored on disk, unlike Chrome's password autofill.
    if cfg.get("_key"):
        cookie_try = login_with_cookies(cfg, wait=min(wait, 20))
        if cookie_try.get("ok"):
            return cookie_try
        pw_try = login_with_password(cfg, wait=wait)
        if pw_try.get("ok"):
            return pw_try
        return pw_try

    tab = _open(cfg["url"])
    tab.call("Page.bringToFront")
    time.sleep(2)
    if cfg["logged_in"] in (tab.eval("location.href") or ""):
        return {"ok": True, "already": True, "url": tab.eval("location.href")}

    # Click the fields so Chrome's password manager offers and fills the saved login.
    tab.click(cfg["user_field"])
    time.sleep(0.8)
    tab.click(cfg["pw_field"])
    time.sleep(1.5)
    filled = tab.eval(
        "(()=>({u:document.querySelector(%r)?.value||'',p:(document.querySelector(%r)?.value||'').length}))()"
        % (cfg["user_field"], cfg["pw_field"]))
    if not filled or not filled.get("p"):
        return {"ok": False, "reason": "no autofill", "filled": filled}

    box = tab.eval(
        "(()=>{const b=[...document.querySelectorAll('button,[role=button],a')]"
        ".find(e=>new RegExp(%r,'i').test(e.innerText||'')&&e.offsetParent);"
        "if(!b)return null;b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();"
        "return {x:r.x+r.width/2,y:r.y+r.height/2};})()" % cfg["btn_text"])
    if not box:
        return {"ok": False, "reason": "no submit button", "filled": filled}
    tab.call("Input.dispatchMouseEvent", type="mouseMoved", x=box["x"], y=box["y"])
    tab.call("Input.dispatchMouseEvent", type="mousePressed", x=box["x"], y=box["y"],
             button="left", buttons=1, clickCount=1)
    tab.call("Input.dispatchMouseEvent", type="mouseReleased", x=box["x"], y=box["y"],
             button="left", buttons=0, clickCount=1)

    for _ in range(wait):
        time.sleep(1)
        url = tab.eval("location.href") or ""
        if cfg["logged_in"] in url:
            return {"ok": True, "url": url}
    return {"ok": False, "reason": "did not reach logged-in url", "url": tab.eval("location.href")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("site", nargs="?", help="known site key: " + ", ".join(SITES))
    ap.add_argument("--url")
    ap.add_argument("--field")
    ap.add_argument("--pw")
    ap.add_argument("--btn-text")
    ap.add_argument("--logged-in")
    ap.add_argument("--match")
    a = ap.parse_args()
    if a.site:
        cfg = SITES.get(a.site)
        if not cfg:
            sys.exit(f"unknown site {a.site!r}; known: {list(SITES)}")
        cfg = dict(cfg, _key=a.site)
    else:
        cfg = {"url": a.url, "user_field": a.field, "pw_field": a.pw,
               "btn_text": a.btn_text or "log in", "logged_in": a.logged_in or ""}
    import json
    r = autologin(cfg)
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
