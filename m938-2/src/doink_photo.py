#!/usr/bin/env python3
"""Put AF's print art on a Do.ink product's storefront gallery.

Do.ink keeps two separate image systems. The storefront card shows the *gallery*
one (Preview -> "เลือกรูปที่จะแสดง"), which defaults to an account-wide template
mockup; the Design tab (print layers) is separate and, on an already-published
product, locked. So the visible fix for "card shows no art" is the gallery.

The gallery's photo tiles are buttons; the "อัปโหลดเอง" tile opens the file
input for that print side. Setting the file only takes effect when the tile was
clicked first, hence the strict order below.

Usage:
  python3 doink_photo.py <product-uuid> <slug>
  python3 doink_photo.py --all
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, "/workspace/afsrc")
sys.path.insert(0, "/workspace/project/AX_MASTER_BRAIN/tools")

import doink_publish as D  # noqa: E402

EDIT = "https://app.do.ink/products/%s/edit"
GAL = "ติ๊กรูปที่ต้องการแสดง"
PHOTO = "/tmp/af_photo_%s.jpg"


def photo_for(slug: str) -> str:
    """Small JPEG of the print: the gallery rejects oversized uploads."""
    from PIL import Image
    out = PHOTO % slug
    if os.path.exists(out):
        return out
    im = Image.open(D.print_path(slug)).convert("RGBA")
    bg = Image.new("RGB", im.size, (14, 14, 14))
    bg.paste(im, (0, 0), im)
    bg.resize((1350, 1800), Image.LANCZOS).save(out, quality=88)
    return out


def click_xy(t, xy):
    if not xy:
        return False
    t.call("Page.bringToFront")
    t.call("Input.dispatchMouseEvent", type="mouseMoved", x=xy[0], y=xy[1])
    t.call("Input.dispatchMouseEvent", type="mousePressed", x=xy[0], y=xy[1],
           button="left", buttons=1, clickCount=1)
    t.call("Input.dispatchMouseEvent", type="mouseReleased", x=xy[0], y=xy[1],
           button="left", buttons=0, clickCount=1)
    return True


def click_btn(t, pattern, root=None, nth=0, wait_after=2.0):
    """Real mouse click on the nth visible button matching pattern (optionally scoped)."""
    scope = "" if root is None else ("let s=b;for(let i=0;i<9&&s;i++){s=s.parentElement;"
                                     "if(s&&/%s/.test(s.innerText||''))break;}" % root)
    base = "[...document.querySelectorAll('button')]"
    js = ("(function(){const b=%s.find(x=>/%s/.test(x.textContent||''));if(!b)return null;%s"
          "const m=[...%s].filter(x=>/%s/.test(x.textContent||''))[%d];"
          "if(!m)return null;m.scrollIntoView({block:'center'});const r=m.getBoundingClientRect();"
          "return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()"
          % (base, pattern, scope, base if root is None else "s.querySelectorAll('button')",
             pattern, nth))
    if root is None:
        js = ("(function(){const m=%s.filter(x=>/%s/.test(x.textContent||''))[%d];"
              "if(!m)return null;m.scrollIntoView({block:'center'});const r=m.getBoundingClientRect();"
              "return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()"
              % (base, pattern, nth))
    ok = click_xy(t, t.eval(js))
    time.sleep(wait_after)
    return ok


def used(t):
    return t.eval("(function(){const m=(document.body.innerText.match(/ใช้ไปแล้ว\\s*(\\d+)/)||[])[1];"
                  "return m?parseInt(m):-1})()")


def open_gallery(t, tries=8):
    for _ in range(tries):
        if t.eval("/%s/.test(document.body.innerText)" % GAL):
            return True
        if not t.eval("/เลือก|อัปโหลด/.test(document.body.innerText)"):
            D.tab_click(t, "preview")
            time.sleep(5)
        click_btn(t, "เลือกรูปที่จะแสดง", wait_after=5)
    return bool(t.eval("/%s/.test(document.body.innerText)" % GAL))


OUR_TILE = """(function(){const d=[...document.querySelectorAll('div')]
  .find(x=>/%s/.test(x.textContent||''));if(!d)return null;
  const bs=[...d.querySelectorAll('button')].filter(b=>{const im=b.querySelector('img');
    if(!im)return false;let s='';try{s=decodeURIComponent(im.src||'');}catch(e){s=im.src||'';}
    return /custom-previews/.test(s);});
  const b=bs[bs.length-1];if(!b)return null;b.scrollIntoView({block:'center'});
  const r=b.getBoundingClientRect();
  return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()""" % GAL

FIRST_TICKED = """(function(){const d=[...document.querySelectorAll('div')]
  .find(x=>/%s/.test(x.textContent||''));if(!d)return null;
  const ts=[...d.querySelectorAll('button')].filter(x=>x.getAttribute('aria-pressed')==='true');
  const b=ts[0];if(!b)return null;b.scrollIntoView({block:'center'});
  const r=b.getBoundingClientRect();
  return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()""" % GAL


def selection(t):
    return t.eval("(function(){const d=[...document.querySelectorAll('div')]"
                  ".find(x=>/%s/.test(x.textContent||''));if(!d)return null;"
                  "const ts=[...d.querySelectorAll('button')].filter(x=>x.getAttribute('aria-pressed')==='true');"
                  "const isC=b=>{const im=b.querySelector('img');let s='';try{s=decodeURIComponent((im&&im.src)||'');}"
                  "catch(e){s=(im&&im.src)||'';}return /custom-previews/.test(s)};"
                  "const b=[...d.querySelectorAll('button')].find(x=>x.textContent.trim()==='บันทึก');"
                  "return {sel:(d.innerText.match(/เลือกแล้ว\\\\s*(\\\\d+)/)||[])[1],"
                  "ticked:ts.length,ours:ts.filter(isC).length,canSave:b?!b.disabled:false};})()" % GAL)


def has_ours(t):
    return bool(t.eval("(function(){const d=[...document.querySelectorAll('div')]"
                       ".find(x=>/%s/.test(x.textContent||''));if(!d)return false;"
                       "return [...d.querySelectorAll('img')].some(im=>{let s='';"
                       "try{s=decodeURIComponent(im.src||'');}catch(e){s=im.src||'';}"
                       "return /custom-previews/.test(s);});})()" % GAL))


def select_only_ours(t, want=1):
    """Clear every ticked mockup, then tick only our uploaded photo.

    The storefront card shows the first selected image, and Do.ink pre-selects 8
    auto-mockups, so leaving them ticked keeps the card on the template no matter
    what we upload.
    """
    for _ in range(12):
        s = selection(t)
        if not s:
            return "no-modal"
        if s["ticked"] == 0:
            break
        click_xy(t, t.eval(FIRST_TICKED))
        time.sleep(1.2)
    click_xy(t, t.eval(OUR_TILE))
    time.sleep(2)
    s = selection(t) or {}
    if s.get("ours", 0) < 1:
        return "no-ours:%s" % json.dumps(s)
    return "ok:%s" % json.dumps(s)


def save(t):
    """Close the gallery modal and commit the product."""
    for _ in range(3):
        if not t.eval("/%s/.test(document.body.innerText)" % GAL):
            break
        if not click_btn(t, "^บันทึก$", wait_after=5):
            t.eval("(function(){const d=[...document.querySelectorAll('div')]"
                   ".find(x=>/%s/.test(x.textContent||''));if(d){const b=[...d.querySelectorAll('button')]"
                   ".find(x=>x.textContent.trim()==='บันทึก');if(b)b.click();}})()" % GAL)
            time.sleep(5)
    if t.eval("/%s/.test(document.body.innerText)" % GAL):
        return "modal-still-open"
    click_btn(t, "Save Changes", wait_after=8)
    if not t.eval("/บันทึกแล้ว|Saved/.test(document.body.innerText)"):
        t.eval("(function(){const b=[...document.querySelectorAll('button')]"
               ".find(x=>/Save Changes/.test(x.textContent||''));if(b)b.click();})()")
        time.sleep(8)
    return "saved" if t.eval("/บันทึกแล้ว|Saved/.test(document.body.innerText)") else "save-clicked"


def upload_own(t, path):
    """Upload a print as a gallery photo (needed once per product)."""
    t.eval("""(function(){const h=[...document.querySelectorAll('h4')].find(x=>x.textContent.trim()==='รูปของคุณ');
              if(h)(h.closest('button')||h).click();return 1})()""")
    time.sleep(4)
    before = used(t)
    click_btn(t, "อัปโหลดเอง", wait_after=4)
    oid = t.call("Runtime.evaluate",
                 expression="[...document.querySelectorAll('input[type=file]')].pop()")["result"].get("objectId")
    if not oid:
        return "no-input"
    t.call("DOM.setFileInputFiles", files=[path], objectId=oid)
    for _ in range(18):
        time.sleep(2)
        if used(t) > before:
            return "used=%d" % used(t)
    return "stuck=%d" % used(t)


def run(uuid, slug):
    t = D.fresh_tab()
    time.sleep(2)
    t.eval("location.href=%r" % (EDIT % uuid))
    time.sleep(12)
    out = {"uuid": uuid, "slug": slug}
    if not open_gallery(t):
        out["result"] = "gallery-wont-open"
        return out
    if not has_ours(t):
        out["upload"] = upload_own(t, photo_for(slug))
    out["select"] = select_only_ours(t)
    out["save"] = save(t)
    t.eval("location.reload()")
    time.sleep(14)
    out["used_after_reload"] = used(t)
    out["verified"] = out["used_after_reload"] > 0
    return out


def main():
    ids = {}
    try:
        ids = json.load(open("/workspace/project/AX_MASTER_BRAIN/pod_wild/ex_ids.json"))
    except Exception:
        pass
    if "--all" in sys.argv:
        for uuid, slug in ids.items():
            print(json.dumps(run(uuid, slug), ensure_ascii=False), flush=True)
        return
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    print(json.dumps(run(a[0], a[1]), ensure_ascii=False))


if __name__ == "__main__":
    main()
