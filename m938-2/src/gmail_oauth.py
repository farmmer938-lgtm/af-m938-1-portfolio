#!/usr/bin/env python3
"""One-time Gmail API authorization so AF can read K's Gmail without a browser.

Problem (vendor-consulted 2026-11-05): AF scrapes Gmail through the noVNC Chromium,
and Google logs that session out on every container restart, forcing K to retype his
password. Every vendor advised the same fix: stop scraping, use the Gmail API with an
OAuth refresh token. The refresh token never dies on a container restart, so K clicks
exactly once and AF reads mail headlessly forever after.

Flow (K does only step 2):
  1. AF runs `python3 gmail_oauth.py url`  -> prints the consent URL.
  2. K opens it, approves, and pastes the code back to AF.
  3. AF runs `python3 gmail_oauth.py finish "<code>"` -> writes the refresh token to
     /workspace/.secrets/gmail.json (0600, never committed).
  4. `python3 gmail_oauth.py read` lists recent inbox subjects via the API.

Requires: `pip install google-auth-oauthlib google-api-python-client`
A Google Cloud OAuth client (Desktop app) is required; its client_id/secret go in
/workspace/.secrets/gmail_client.json. This is the only part that needs K's account.
"""
from __future__ import annotations

import json
import os
import sys

SECRETS = "/workspace/.secrets"
CLIENT = os.path.join(SECRETS, "gmail_client.json")
TOKEN = os.path.join(SECRETS, "gmail.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _load_client():
    if not os.path.exists(CLIENT):
        sys.exit(
            f"missing {CLIENT}: create a Google Cloud OAuth 'Desktop app' client and "
            "save its JSON there (one-time, K's account)"
        )
    return CLIENT


def cmd_url() -> None:
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(_load_client(), scopes=SCOPES)
    flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    print(url)


def cmd_finish(code: str) -> None:
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(_load_client(), scopes=SCOPES)
    flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    flow.fetch_token(code=code)
    os.makedirs(SECRETS, exist_ok=True)
    with open(TOKEN, "w") as f:
        f.write(flow.credentials.to_json())
    os.chmod(TOKEN, 0o600)
    print(f"refresh token saved to {TOKEN}")


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN, "w") as f:
            f.write(creds.to_json())
        os.chmod(TOKEN, 0o600)
    return creds


def cmd_read() -> None:
    from googleapiclient.discovery import build

    svc = build("gmail", "v1", credentials=_creds(), cache_discovery=False)
    res = svc.users().messages().list(userId="me", maxResults=15, q="in:inbox").execute()
    for m in res.get("messages", []):
        meta = svc.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()
        heads = {h["name"]: h["value"] for h in meta["payload"].get("headers", [])}
        print(f"- {heads.get('From','?')} | {heads.get('Subject','?')}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd, *rest = sys.argv[1:]
    if cmd == "url":
        cmd_url()
    elif cmd == "finish":
        cmd_finish(rest[0] if rest else input("code: ").strip())
    elif cmd == "read":
        cmd_read()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
