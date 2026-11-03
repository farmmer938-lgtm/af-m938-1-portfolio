#!/usr/bin/env python3
"""AF autopilot for the Lazada Open Platform onboarding (project m938-2).

Runs unattended. Each pass:
  1. ensures the noVNC Chromium stack is up (start_novnc.sh is idempotent);
  2. reads the ISV profile / category state from the console API;
  3. while the profile is 'Under review' it does nothing but log;
  4. the moment the profile is approved it creates the app (discovering the required
     form fields from the server's own validation errors), saves App Key/Secret to
     /workspace/.secrets/lazada.json, and stops.

Idempotent: safe to run from cron every N minutes; it never creates a second app.
Log: /workspace/.lazada-autopilot.log
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lazada_console as lc  # noqa: E402
from browser_drive import Tab  # noqa: E402

LOG = "/workspace/.lazada-autopilot.log"
SECRETS = "/workspace/.secrets/lazada.json"
STOP = "/workspace/.lazada-autopilot.done"
APP_CID = 11
APP_TITLE = "AF Studio TH"
APP_DESC = "In-house seller app for AF Studio (own Lazada store only)."
LOGO = ("https://lazada-open-platform-public.oss-ap-southeast-1.aliyuncs.com/online/"
        "oss_Seller In-house APP@2x_1703584478486__NsIC.png")
TARGET_CATEGORY = "Seller In-house APP"


def log(msg: str) -> None:
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg)
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def ensure_stack() -> None:
    subprocess.run(["bash", os.path.join(HERE, "start_novnc.sh")],
                   capture_output=True, timeout=180)


def discover_and_create(t: Tab) -> dict | None:
    """Create the app, filling in any extra required field the server asks for."""
    seed = {
        "appCid": APP_CID, "title": APP_TITLE, "appCatName": TARGET_CATEGORY,
        "logoUrl": LOGO, "description": APP_DESC,
    }
    guesses = {
        "shortCode": "AFTH", "appName": APP_TITLE, "name": APP_TITLE,
        "appDesc": APP_DESC, "callbackUrl": "https://af-studio-m938-2.surge.sh",
        "appCategory": APP_CID, "accessValidtime": 720, "refreshValidtime": 4320,
        "webUrl": "https://af-studio-m938-2.surge.sh",
    }
    fields = dict(seed)
    for _ in range(12):
        j = lc.create_app(t, **fields)
        if j.get("success"):
            return j.get("data", {})
        msg = j.get("errorMessage", "")
        if "is not present" in msg and "'" in msg:
            missing = msg.split("'")[1]
            if missing in fields:
                log("BLOCKED: server keeps asking for %r; add a real value" % missing)
                return None
            fields[missing] = guesses.get(missing, APP_TITLE)
            log("createApp: adding required field %r=%r" % (missing, fields[missing]))
            continue
        if j.get("errorCode") == "error.isv.profile.notapproved":
            return None
        log("createApp error: %s" % json.dumps(j, ensure_ascii=False)[:300])
        return None
    return None


def save_secret(data: dict) -> None:
    os.makedirs(os.path.dirname(SECRETS), exist_ok=True)
    keep = {k: v for k, v in data.items()
            if k.lower() in ("appkey", "appsecret", "appname", "appcid", "appid", "name")}
    with open(SECRETS, "w") as f:
        json.dump(keep, f, ensure_ascii=False, indent=1)
    os.chmod(SECRETS, 0o600)


def main() -> int:
    if os.path.exists(STOP):
        return 0
    ensure_stack()
    t = Tab()
    t.goto(lc.CONSOLE_URL, settle=4)

    cats = lc.categories(t)
    me = next((c for c in cats if c.get("appCid") == APP_CID), {})
    apps = lc.app_list(t)
    log("category %s applyStatus=%s | apps=%s" % (APP_CID, me.get("applyStatus"), apps.get("total")))

    if apps.get("total"):
        log("app already exists; nothing to do")
        open(STOP, "w").write("app exists\n")
        return 0

    if not lc.profile_approved(t, APP_CID):
        log("profile still 'Under review' — waiting (Lazada takes 1-3 working days)")
        return 0

    log("profile APPROVED — creating app")
    data = discover_and_create(t)
    if data:
        save_secret(data)
        open(STOP, "w").write(json.dumps(data, ensure_ascii=False))
        log("APP CREATED; key/secret saved to %s" % SECRETS)
    else:
        log("app creation did not complete this pass; will retry next run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
