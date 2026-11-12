#!/usr/bin/env python3
"""AF's eyes and hands on the visible Chromium screen.

K's point: the "human gate" is just a button at a point on a screen, and a click is a
click regardless of whose finger it is. This drives the same Chromium instance the
noVNC display shows (CDP on :9222), so AF can see and act on the pages K would.

Usage:
  python3 tools/cdp.py targets
  python3 tools/cdp.py shot <target-substr> [out.png]
  python3 tools/cdp.py eval <target-substr> "<js>"
  python3 tools/cdp.py click <target-substr> <selector-or-js-expression>
  python3 tools/cdp.py text <target-substr>
"""
import base64
import json
import sys
import urllib.request

import websocket

CDP = "http://localhost:9222"


def targets():
    with urllib.request.urlopen(CDP + "/json/list", timeout=10) as r:
        return json.loads(r.read().decode())


def find(substr):
    for t in targets():
        if t.get("type") == "page" and substr.lower() in (t.get("url", "") + t.get("title", "")).lower():
            return t
    raise SystemExit("no page target matching %r" % substr)


class Tab:
    def __init__(self, target):
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=int(__import__("os").environ.get("CDP_TIMEOUT","90")))
        self.id = 0

    def call(self, method, **params):
        self.id += 1
        self.ws.send(json.dumps({"id": self.id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def eval(self, expression):
        r = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def click(self, selector):
        """Find the element, then press the point on screen with a real mouse event."""
        js = ("(()=>{const e=%s; if(!e) return null; e.scrollIntoView({block:'center'});"
              "const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2,"
              "tag:e.tagName,text:(e.innerText||e.value||'').slice(0,60)};})()"
              % (selector if selector.strip().startswith(("document", "(")) else "document.querySelector(%s)" % json.dumps(selector)))
        box = self.eval(js)
        if not box:
            return "not-found"
        self.call("Page.bringToFront")
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=box["x"], y=box["y"])
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=box["x"], y=box["y"],
                  button="left", buttons=1, clickCount=1)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=box["x"], y=box["y"],
                  button="left", buttons=0, clickCount=1)
        return box

    def type_text(self, selector, text):
        """Focus the field, then type with real key events (what K does on screen)."""
        self.click(selector)
        self.call("Input.insertText", text=text)
        return self.eval("(()=>{const e=%s;return e?e.value:null})()"
                         % (selector if selector.strip().startswith(("document", "(")) else "document.querySelector(%s)" % json.dumps(selector)))

    def screenshot(self, path):
        r = self.call("Page.captureScreenshot", format="png")
        data = base64.b64decode(r["data"])
        with open(path, "wb") as f:
            f.write(data)
        return path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "targets":
        for t in targets():
            if t.get("type") == "page":
                print(t.get("title", "")[:40], "|", t.get("url", "")[:90])
        return 0
    tab = Tab(find(sys.argv[2]))
    if cmd == "shot":
        print(tab.screenshot(sys.argv[3] if len(sys.argv) > 3 else "/tmp/shot.png"))
    elif cmd == "eval":
        print(json.dumps(tab.eval(sys.argv[3]), ensure_ascii=False))
    elif cmd == "text":
        print(tab.eval("document.body.innerText")[:4000])
    elif cmd == "click":
        print(json.dumps(tab.click(sys.argv[3]), ensure_ascii=False))
    elif cmd == "type":
        print(json.dumps(tab.type_text(sys.argv[3], sys.argv[4]), ensure_ascii=False))
    else:
        print("unknown command", cmd)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
