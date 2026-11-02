#!/usr/bin/env python3
"""Launch a Do.ink POD product from the m938-2 pack, driving the logged-in noVNC
Chromium over CDP. The editor holds state in memory, so the whole flow runs in ONE
session with no page reloads.

Usage:
  python3 pod_launch.py seller-boss [--dry-run]

Prereq: src/start_novnc.sh running and K logged in to app.do.ink.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_drive import Tab  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE_TEE = "c26419bf-bc97-41d5-aa0b-09bd701720f7"  # BASIC COTTON NO.30 COMB
PRINT_AREA = "A4"  # ฿95 print, 8x12 inch


def log(step, detail):
    print(f"[{step}] {detail}")


def click(t, pattern, tags="button,a,[role=tab]"):
    """Click the first element whose trimmed text matches the regex `pattern`."""
    return t.js(
        "(()=>{const els=[...document.querySelectorAll(%s)];"
        "const b=els.find(e=>new RegExp(%s,'i').test((e.innerText||'').trim()));"
        "if(!b)return null;b.click();return (b.innerText||'').trim().slice(0,40);})()"
        % (json.dumps(tags), json.dumps(pattern))
    )


def set_value(t, selector, value):
    return t.js(
        "(()=>{const e=document.querySelector(%s);if(!e)return 'NOT_FOUND';"
        "const s=Object.getOwnPropertyDescriptor(e.constructor.prototype,'value').set;"
        "s.call(e,%s);e.dispatchEvent(new Event('input',{bubbles:true}));"
        "e.dispatchEvent(new Event('change',{bubbles:true}));return 'OK';})()"
        % (json.dumps(selector), json.dumps(value))
    )


def kill_tour(t):
    """Do.ink uses driver.js tutorial popovers that cover the page and swallow
    clicks. Remove the overlay + popover before clicking page controls."""
    return t.js(
        "(()=>{const s=document.getElementById('driver-popover-content');"
        "document.querySelectorAll('.driver-overlay,.driver-popover,.driver-active-element')"
        ".forEach(e=>e.remove());"
        "document.querySelectorAll('body>*').forEach(e=>{"
        "const z=getComputedStyle(e).zIndex;if(z&&+z>1000&&/overlay|backdrop/i.test(e.className))e.remove()});"
        "return s?'removed':'none';})()"
    )


def state(t):
    return t.js(
        "(()=>({path:location.pathname,layers:(document.body.innerText.match(/Layers\\s*(\\d+)/)||[])[1],"
        "name:(document.querySelector('input[placeholder=\"Enter my product name\"]')||{}).value||'',"
        "price:(document.body.innerText.match(/Price Breakdown:[^|]{0,28}/)||[''])[0],"
        "toast:(document.body.innerText.match(/(created|success|error|required|failed)[^|]{0,50}/i)||[''])[0]}))()"
    )


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    slug = argv[0]
    dry = "--dry-run" in argv
    item = next((x for x in json.loads((ROOT / "out/pack.json").read_text()) if x["slug"] == slug), None)
    if not item:
        print(f"no pack item for {slug!r}")
        return 2
    design = ROOT / item["print_file"]
    print(f"slug={slug} design={design} ({design.stat().st_size} bytes)")

    t = Tab()
    try:
        t.goto("https://app.do.ink/catalog", 4)
        log("catalog", t.js("location.pathname"))
        r = t.js("(()=>{const el=[...document.querySelectorAll('div.p-5')]"
                 ".find(e=>e.innerText.includes('BASIC COTTON NO.30'));if(!el)return null;el.click();return 'ok';})()")
        log("open-tee", r); time.sleep(3)
        log("start-designing", click(t, r"^Start Designing$")); time.sleep(5)
        log("select-%s" % PRINT_AREA, click(t, r"^%s \(" % PRINT_AREA)); time.sleep(2)
        r = click(t, r"Confirm Position")
        if not r:
            r = click(t, r"Don't show this again")
        log("position", r); time.sleep(2)
        log("images-tab", click(t, r"^Images$")); time.sleep(2)
        t.upload("input[type=file]", [design])
        time.sleep(6)
        s = state(t)
        log("design-uploaded", f"layers={s['layers']}")
        if not s["layers"] or s["layers"] == "0":
            print("UPLOAD FAILED - layers=0"); return 3
        log("details-tab", click(t, r"Details & Pricing")); time.sleep(2)
        log("name", set_value(t, 'input[placeholder="Enter my product name"]', item["title"]))
        log("desc", set_value(t, 'textarea[placeholder^="Add a description"]', item["description"]))
        log("margin", click(t, r"Apply 30% Margin")); time.sleep(1)
        s = state(t)
        log("priced", s["price"])
        if dry:
            print("DRY RUN - stopping before create"); return 0
        log("create", click(t, r"^Create My Product$")); time.sleep(4)
        log("agree", click(t, r"I agree . create product")); time.sleep(5)
        # Do.ink requires preview images; the warning modal offers "Set up Preview Images".
        if click(t, r"Set up Preview Images"):
            time.sleep(3)
            kill_tour(t)
            log("select-all", click(t, r"^Select all$")); time.sleep(2)
            kill_tour(t)
            log("create2", click(t, r"^Create My Product$")); time.sleep(4)
            log("agree2", click(t, r"I agree . create product")); time.sleep(6)
        for _ in range(3):
            kill_tour(t)
            r = click(t, r"^Save Anyway$") or click(t, r"^Save Draft$")
            log("dialog", r)
            if not r:
                break
            time.sleep(4)
        print("final:", json.dumps(state(t), ensure_ascii=False))
        if "--list" in sys.argv:
            time.sleep(3)
            t.goto("https://app.do.ink/products", 4)
            if click(t, __import__("re").escape(item["title"][:18]), tags="h3,a,button"):
                time.sleep(3)
                log("push", click(t, r"^Push$")); time.sleep(3)
                log("list", click(t, r"^List on store$")); time.sleep(5)
                print("listed:", t.js("(document.body.innerText.match(/Listed on[^|]{0,30}/)||[''])[0]"))
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
