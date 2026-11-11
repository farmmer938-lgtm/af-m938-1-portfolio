#!/usr/bin/env python3
"""Lazada Open Platform App-Console API (project m938-2).

The console pages are served from open.lazada.com but their API lives on
isvconsole.lazada.com. The page JS therefore treats API calls as cross-host, tries to
fetch a CSRF token from a non-existent endpoint, and every POST dies with HTTP 404.
We bypass that entirely: call the isvconsole endpoints straight from the page (same
cookie jar) using the token Lazada already injected into window.csrf.

POSTs MUST be application/x-www-form-urlencoded. A JSON body silently fails
(error.appcat.notexist) because the server only reads form params.

Requires the noVNC Chromium on :9222, logged in to the Lazada developer account
(see src/start_novnc.sh).

CLI:  python3 lazada_console.py status
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_drive import Tab  # noqa: E402

BASE = "https://isvconsole.lazada.com"
CONSOLE_URL = "https://isvconsole.lazada.com/apps/console/apps"

_PROLOGUE = (
    "const tb=window._tb_token_;const tok=(window.csrf&&window.csrf.tokenValue)||'';"
)


def _post(t: Tab, path: str, params: dict) -> dict:
    js = (
        "(async()=>{try{%s"
        "const p=new URLSearchParams(%s);p.set('_tb_token_',tb);p.set('xcsrf-token',tok);"
        "const h={'Content-Type':'application/x-www-form-urlencoded','xcsrf-token':tok};"
        "const r=await fetch(%s+'?_tb_token_='+tb,{method:'POST',credentials:'include',headers:h,"
        "body:p.toString()});return await r.text();}catch(e){return '{\"_fetch_error\":true}';}})()"
        % (_PROLOGUE, json.dumps(params), json.dumps(BASE + path))
    )
    return json.loads(t.js(js, await_promise=True))


def _get(t: Tab, path: str, params: dict | None = None) -> dict:
    q = "&".join("%s=%s" % (k, v) for k, v in (params or {}).items())
    js = (
        "(async()=>{try{%s"
        "const r=await fetch(%s+'?_tb_token_='+tb+%s,{credentials:'include'});"
        "return await r.text();}catch(e){return '{\"_fetch_error\":true}';}})()"
        % (_PROLOGUE, json.dumps(BASE + path), json.dumps("&" + q if q else ""))
    )
    return json.loads(t.js(js, await_promise=True))


def logged_in(t: Tab) -> bool:
    """False when the console bounced us to the sign-in page (session gone / captcha gate)."""
    t.goto(CONSOLE_URL, settle=4)
    return "login" not in (t.js("location.href") or "").lower()


def categories(t: Tab) -> list:
    j = _get(t, "/handler/share/appcat/getAppcatList.json", {"page": 1, "pageSize": 100})
    return j.get("data", {}).get("list", [])


def apply_category(t: Tab, app_cid: int, reason: str, app_cat_name: str = "") -> dict:
    return _post(t, "/handler/share/appcat/applyAppcat",
                 {"appCid": str(app_cid), "appCatName": app_cat_name, "reason": reason})


def create_app(t: Tab, **fields) -> dict:
    return _post(t, "/handler/share/app/createApp", {k: str(v) for k, v in fields.items()})


def save_app_basic(t: Tab, **fields) -> dict:
    return _post(t, "/handler/share/app/saveAppBasic", {k: str(v) for k, v in fields.items()})


def app_list(t: Tab) -> dict:
    return _get(t, "/handler/share/app/getAppList.json", {"page": 1, "pageSize": 100}).get("data", {})


def profile_approved(t: Tab, app_cid: int = 11) -> bool:
    """True once the ISV profile has left 'Under review'.

    The server validates required params before the profile, so we must send a
    payload with every known field; only then does error.isv.profile.notapproved
    surface for an un-approved profile.
    """
    j = create_app(t, appCid=app_cid, title="probe", appCatName="Seller In-house APP",
                   logoUrl="https://lazada-open-platform-public.oss-ap-southeast-1.aliyuncs.com/online/x.png",
                   description="probe")
    return j.get("errorCode") != "error.isv.profile.notapproved"


def _main() -> int:
    t = Tab()
    t.goto(CONSOLE_URL, settle=4)
    cats = categories(t)
    print(json.dumps({
        "host": t.js("location.host"),
        "tb_token": t.js("window._tb_token_ || null"),
        "csrf": t.js("(window.csrf&&window.csrf.tokenValue)||null"),
        "apps": app_list(t),
        "categories": [{k: c.get(k) for k in
                        ("appCid", "name", "canApply", "canCreateApp", "applyStatus", "rejectMsg")}
                       for c in cats],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
