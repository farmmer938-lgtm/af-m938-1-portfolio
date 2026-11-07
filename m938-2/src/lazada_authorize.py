#!/usr/bin/env python3
"""Complete the Lazada seller authorization with no human (project m938-2).

AF logs into the Lazada seller account itself (tools/af_autologin.py uses the saved
profile login); this script does the rest: it opens the OAuth authorize URL, waits for
the callback URL to carry the authorization code, exchanges it for an access token
and saves it. K is not in the loop.

Why this exists: the Lazada Open Platform app (Seller In-house APP) can only call
the API for a shop that has authorized it. Authorization needs the seller's own
login, which AF now performs itself; AF then keeps the token fresh afterwards.

Usage:
  python3 lazada_authorize.py url                 # print the authorize URL
  python3 lazada_authorize.py open                # open it in the noVNC browser
  python3 lazada_authorize.py watch [minutes]     # wait for the code, exchange it
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_drive import Tab, _http  # noqa: E402
from lazada_client import LazadaClient, DEFAULT_SECRETS  # noqa: E402

CALLBACK = "https://farmmer938-lgtm.github.io/autonomous-zero-baht/lazada-callback.html"
TOKENS = "/workspace/.secrets/lazada.json"


def authorize_url() -> str:
    c = LazadaClient.from_secrets(DEFAULT_SECRETS)
    return c.build_auth_url(CALLBACK, force_auth=True, state="af938")


def open_in_browser(url: str) -> None:
    t = Tab()
    try:
        t.goto(url, settle=3)
    finally:
        t.close()


def find_code(minutes: int = 15) -> str | None:
    """Poll every CDP tab for the callback URL carrying ?code=..."""
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        for tgt in _http("/json"):
            u = tgt.get("url", "")
            if "lazada-callback" in u:
                q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
                if q.get("code"):
                    return q["code"][0]
        time.sleep(3)
    return None


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "url"
    if cmd == "url":
        print(authorize_url())
        return 0
    if cmd == "open":
        open_in_browser(authorize_url())
        print("opened authorize page in the noVNC browser")
        return 0
    if cmd == "watch":
        minutes = int(argv[1]) if len(argv) > 1 else 15
        code = find_code(minutes)
        if not code:
            print("no authorization code captured in time")
            return 1
        c = LazadaClient.from_secrets(DEFAULT_SECRETS)
        out = c.create_token(code)
        c.save_tokens(TOKENS, **out)
        print(json.dumps({k: (v[:8] + "…" if isinstance(v, str) and len(v) > 12 else v)
                          for k, v in out.items()}, ensure_ascii=False))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
