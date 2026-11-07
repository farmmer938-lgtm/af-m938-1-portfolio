#!/usr/bin/env python3
"""AF Gmail reader — OAuth2 refresh-token flow (no browser, no password, no 2FA prompts).

Why this exists (K directive 2026-11-07): the single most frequent K-blocker was the
Google session. AF read Gmail through a headless Chromium driven over CDP; every
container restart logged the session out and K had to retype his password via noVNC.
Five independent AI vendors (pollinations, Gemini, KiloCode, CohereForAI, Yqcloud) all
ranked the SAME fix first: stop scraping the browser and use the Gmail REST API with an
OAuth2 refresh token. K approves once, then AF reads mail forever with no human in the
loop.

One-time setup (the only human step, ~3 minutes, done once):
  1. Google Cloud console -> create a project -> enable "Gmail API".
  2. Create OAuth client ID, type "Desktop app". Copy client id + secret.
  3. Put them in /workspace/.af_gmail/client.json:
        {"client_id": "...", "client_secret": "..."}
  4. Run:  python3 tools/af_gmail_oauth.py --auth
     Open the printed URL, approve, paste the code back.
     The refresh token is stored at /workspace/.af_gmail/token.json (persistent volume).
  5. From then on:  python3 tools/af_gmail_oauth.py --list [--query "from:frantic"]

No third-party dependency: talks to Google's token + Gmail REST endpoints with urllib.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

STATE_DIR = Path(os.environ.get("AF_GMAIL_DIR", "/workspace/.af_gmail"))
CLIENT_FILE = STATE_DIR / "client.json"
TOKEN_FILE = STATE_DIR / "token.json"


def _post(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return json.loads(body)
        except Exception:
            return {"error": f"http_{e.code}", "raw": body[:400]}


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return json.loads(body)
        except Exception:
            return {"error": f"http_{e.code}", "raw": body[:400]}


def load_client() -> dict:
    if not CLIENT_FILE.exists():
        sys.exit(f"missing {CLIENT_FILE}; see module docstring for the one-time setup")
    return json.loads(CLIENT_FILE.read_text())


def do_auth() -> int:
    """One-time: print consent URL, exchange the pasted code for a refresh token."""
    c = load_client()
    q = urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        "response_type": "code", "scope": SCOPE, "access_type": "offline",
        "prompt": "consent",
    })
    print("Open this URL, approve, then paste the code:\n")
    print(f"{AUTH}?{q}\n")
    code = input("code: ").strip()
    tok = _post(TOKEN, {"client_id": c["client_id"], "client_secret": c["client_secret"],
                        "code": code, "grant_type": "authorization_code",
                        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob"})
    if "refresh_token" not in tok:
        print(f"auth failed: {tok}")
        return 1
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tok, indent=1))
    os.chmod(TOKEN_FILE, 0o600)
    print(f"saved refresh token to {TOKEN_FILE} (persistent; no further human steps)")
    return 0


def access_token() -> str:
    """Exchange the stored refresh token for a short-lived access token (no human)."""
    c = load_client()
    t = json.loads(TOKEN_FILE.read_text())
    r = _post(TOKEN, {"client_id": c["client_id"], "client_secret": c["client_secret"],
                      "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
    if "access_token" not in r:
        raise RuntimeError(f"refresh failed: {r}")
    return r["access_token"]


def list_messages(query: str, limit: int) -> list[dict]:
    tok = access_token()
    url = f"{API}/messages?" + urllib.parse.urlencode({"q": query, "maxResults": limit})
    d = _get(url, tok)
    out = []
    for m in d.get("messages", [])[:limit]:
        full = _get(f"{API}/messages/{m['id']}?format=metadata"
                    "&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date", tok)
        h = {x["name"]: x["value"] for x in full.get("payload", {}).get("headers", [])}
        out.append({"id": m["id"], "from": h.get("From", ""), "subject": h.get("Subject", ""),
                    "date": h.get("Date", ""), "snippet": full.get("snippet", "")})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth", action="store_true", help="one-time consent (needs the human)")
    ap.add_argument("--list", action="store_true", help="list messages (fully autonomous)")
    ap.add_argument("--query", default="is:unread", help="Gmail search query")
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args()
    if a.auth:
        return do_auth()
    if a.list:
        msgs = list_messages(a.query, a.limit)
        print(json.dumps(msgs, ensure_ascii=False, indent=1))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
