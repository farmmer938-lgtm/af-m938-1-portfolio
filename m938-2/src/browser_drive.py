#!/usr/bin/env python3
"""Drive the noVNC Chromium over CDP (project m938-2).

K logs in once through noVNC; AF then uses this to read pages, click and type in
that same logged-in browser, so AF can complete tasks K finds hard.

Setup: src/start_novnc.sh must be running (Chromium on :9222, VNC on :12001).

CLI:
  python3 browser_drive.py tabs
  python3 browser_drive.py goto <url>
  python3 browser_drive.py text [max_chars]
  python3 browser_drive.py links
  python3 browser_drive.py inputs
  python3 browser_drive.py click <css_selector>
  python3 browser_drive.py fill <css_selector> <value>
  python3 browser_drive.py eval "<javascript>"
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

import websocket  # websocket-client

CDP = "http://127.0.0.1:9222"


def _http(path: str):
    with urllib.request.urlopen(CDP + path, timeout=10) as r:
        return json.loads(r.read().decode())


def _page_ws() -> str:
    for t in _http("/json"):
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no page target; is the noVNC Chromium running?")


class Tab:
    def __init__(self, ws_url: str | None = None):
        self.ws = websocket.create_connection(ws_url or _page_ws(), timeout=30)
        self._id = 0

    def send(self, method: str, params: dict | None = None):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr: str, await_promise: bool = False):
        r = self.send("Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": await_promise,
        })
        res = r.get("result", {})
        if r.get("exceptionDetails"):
            raise RuntimeError(json.dumps(r["exceptionDetails"], ensure_ascii=False)[:500])
        return res.get("value")

    def goto(self, url: str, settle: float = 2.0):
        self.send("Page.enable")
        self.send("Page.navigate", {"url": url})
        time.sleep(settle)

    def upload(self, selector: str, paths: list[str]):
        """Attach local files to a file input (CDP DOM.setFileInputFiles)."""
        r = self.send("Runtime.evaluate", {"expression": f"document.querySelector({json.dumps(selector)})"})
        obj = r.get("result", {}).get("objectId")
        if not obj:
            raise RuntimeError(f"no element for {selector!r}")
        self.send("DOM.enable")
        self.send("DOM.setFileInputFiles", {"files": [str(p) for p in paths], "objectId": obj})

    def real_click(self, selector: str, index: int = 0):
        """Trusted mouse click at an element's centre (Svelte needs real events)."""
        box = self.js(
            "(()=>{const e=document.querySelectorAll(%s)[%d];if(!e)return null;"
            "e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();"
            "return {x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,h:r.height};})()"
            % (json.dumps(selector), index)
        )
        if not box or not box.get("w"):
            return None
        x, y = box["x"], box["y"]
        for typ in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", {"type": typ, "x": x, "y": y, "button": "left", "clickCount": 1})
            time.sleep(0.05)
        return box

    def close(self):
        self.ws.close()


# --- helpers that run in the page ------------------------------------------
_READ = """(() => ({
  url: location.href,
  title: document.title,
  text: (document.body ? document.body.innerText : '').slice(0, %d),
}))()"""
_LINKS = """(() => Array.from(document.querySelectorAll('a')).slice(0,%d)
  .map(a => ({t:(a.innerText||'').trim().slice(0,60), h:a.href})).filter(x=>x.h))()"""
_INPUTS = """(() => Array.from(document.querySelectorAll('input,textarea,select,button')).slice(0,%d)
  .map(e => ({tag:e.tagName.toLowerCase(), type:e.type||'', name:e.name||'',
              id:e.id||'', ph:e.placeholder||'', txt:(e.innerText||'').trim().slice(0,40)})))()"""
_CLICK = """(() => { const e=document.querySelector(%s); if(!e) return 'NOT_FOUND';
  e.scrollIntoView({block:'center'}); e.click(); return 'CLICKED:'+(e.innerText||e.value||e.tagName).slice(0,50); })()"""
_FILL = """(() => { const e=document.querySelector(%s); if(!e) return 'NOT_FOUND';
  e.focus();
  const setter=Object.getOwnPropertyDescriptor(e.constructor.prototype,'value').set;
  setter.call(e, %s);
  e.dispatchEvent(new Event('input',{bubbles:true}));
  e.dispatchEvent(new Event('change',{bubbles:true}));
  return 'FILLED:'+(e.name||e.id||e.tagName); })()"""


def _js_str(s: str) -> str:
    return json.dumps(s)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    t = Tab()
    try:
        if cmd == "tabs":
            for x in _http("/json"):
                if x.get("type") == "page":
                    print(x.get("title", ""), "|", x.get("url", ""))
        elif cmd == "goto":
            t.goto(rest[0])
            print(json.dumps(t.js(_READ % 400, ), ensure_ascii=False, indent=1)[:600])
        elif cmd == "text":
            n = int(rest[0]) if rest else 3000
            print(t.js(_READ % n))
        elif cmd == "links":
            print(json.dumps(t.js(_LINKS % (int(rest[0]) if rest else 60)), ensure_ascii=False, indent=1))
        elif cmd == "inputs":
            print(json.dumps(t.js(_INPUTS % (int(rest[0]) if rest else 40)), ensure_ascii=False, indent=1))
        elif cmd == "click":
            print(t.js(_CLICK % _js_str(rest[0])))
        elif cmd == "fill":
            print(t.js(_FILL % (_js_str(rest[0]), _js_str(rest[1]))))
        elif cmd == "eval":
            print(json.dumps(t.js(rest[0]), ensure_ascii=False))
        elif cmd == "upload":
            sel = rest[0]
            t.upload(sel, rest[1:])
            print(f"uploaded {len(rest)-1} file(s) to {sel}")
        else:
            print(f"unknown command {cmd!r}", file=sys.stderr)
            return 2
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
