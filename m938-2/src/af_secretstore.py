#!/usr/bin/env python3
"""AF secret store — enter a credential ONCE, use it everywhere.

K enters the shared account password a single time. This module resolves it for
every script and every automation, in this order:

  1. environment variable  (OpenHands auto-injects registered secrets into a session)
  2. /workspace/.secrets/af_master.json  (0600 file, survives container restart)
  3. the sandbox secret store  (what automations can reach; via get_secret)
  4. the automation KV store   (last resort)

A value read from (1) or (3) is cached to (2) on first use, so later runs never
need the upstream source again.

The file is a JSON object; `master_password` applies to EVERY account that has no
account-specific password, which is what "this password works for all accounts"
means in practice.

CLI (never pass the secret as an argument - it would show up in `ps`):
  af_secretstore.py set --from-env AF_MASTER_PASSWORD     # copy env -> store
  af_secretstore.py set --stdin                           # type/paste, then EOF
  af_secretstore.py set --stdin --account user@host       # account-specific
  af_secretstore.py get MASTER_PASSWORD                   # print (careful: logs)
  af_secretstore.py password-for user@example.com         # account or master
  af_secretstore.py verify                                # presence + permissions
  af_secretstore.py where                                 # which sources resolve
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time

STORE_DIR = os.environ.get("AF_SECRETS_DIR", "/workspace/.secrets")
STORE = os.path.join(STORE_DIR, "af_master.json")
# Names checked, in order, when resolving the shared/master password.
MASTER_NAMES = ("AF_MASTER_PASSWORD", "AF_MAIL_PASSWORD", "MASTER_PASSWORD")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _read_store() -> dict:
    try:
        with open(STORE) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_store(d: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    try:
        os.chmod(STORE_DIR, 0o700)
    except OSError:
        pass
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, STORE)


def _get_secret(name: str):
    """Read one secret from the sandbox secret store; returns None if unreachable."""
    import urllib.request

    base = os.environ.get("AGENT_SERVER_URL", "").rstrip("/")
    key = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
    if base:
        url = f"{base}/api/settings/secrets/{name}"
    else:
        api = os.environ.get("OPENHANDS_CLOUD_API_URL", "").rstrip("/")
        sandbox = os.environ.get("SANDBOX_ID", "")
        if not (api and sandbox):
            return None
        url = f"{api}/api/v1/sandboxes/{sandbox}/settings/secrets/{name}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"X-Session-API-Key": key}), timeout=20
        ) as r:
            return r.read().decode().strip() or None
    except Exception:
        return None


def get(name: str, cache: bool = True):
    """Resolve any secret: env -> sandbox store -> on-disk store. Caches hits."""
    v = os.environ.get(name)
    if v:
        return v
    v = _get_secret(name)
    if v:
        if cache:
            _cache_named(name, v)
        return v
    d = _read_store()
    if name in MASTER_NAMES:
        return d.get("master_password")
    return ((d.get("secrets") or {}).get(name, {}) or {}).get("value") \
        or (d.get("accounts") or {}).get(name, {}).get("password")


def _cache_named(name: str, val: str) -> None:
    d = _read_store()
    d.setdefault("secrets", {})[name] = {"value": val, "updated_at": _now()}
    _write_store(d)


def master_password(cache: bool = True):
    """Resolve the shared password from every available source."""
    for name in MASTER_NAMES:
        v = os.environ.get(name)
        if v:
            if cache:
                d = _read_store()
                if d.get("master_password") != v:
                    d["master_password"] = v
                    d["applies_to"] = "all_accounts"
                    d.setdefault("created_at", _now())
                    d["updated_at"] = _now()
                    _write_store(d)
            return v

    d = _read_store()
    if d.get("master_password"):
        return d["master_password"]

    for name in MASTER_NAMES:
        v = _get_secret(name)
        if v:
            if cache:
                d["master_password"] = v
                d["applies_to"] = "all_accounts"
                d.setdefault("created_at", _now())
                d["updated_at"] = _now()
                _write_store(d)
            return v
    return None


def password_for(account: str):
    """Password for one account: account-specific first, else the shared master."""
    d = _read_store()
    acct = (d.get("accounts") or {}).get(account) or {}
    if acct.get("password"):
        return acct["password"]
    return master_password()


def verify() -> dict:
    d = _read_store()
    st = None
    try:
        st = stat.S_IMODE(os.stat(STORE).st_mode)
    except OSError:
        pass
    return {
        "store": STORE,
        "exists": os.path.exists(STORE),
        "file_mode": oct(st) if st is not None else None,
        "dir_mode": oct(stat.S_IMODE(os.stat(STORE_DIR).st_mode)) if os.path.isdir(STORE_DIR) else None,
        "has_master": bool(d.get("master_password")),
        "master_len": len(d.get("master_password") or ""),
        "applies_to": d.get("applies_to"),
        "accounts": sorted((d.get("accounts") or {}).keys()),
        "updated_at": d.get("updated_at"),
        "env_present": [n for n in MASTER_NAMES if os.environ.get(n)],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("set")
    p.add_argument("--from-env", metavar="NAME")
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--name", help="store under this secret name (e.g. GITHUB_TOKEN)")
    p.add_argument("--account", help="store for one account instead of the master")
    p.add_argument("--no-master", action="store_true",
                   help="do not also set the shared master password")

    g = sub.add_parser("get")
    g.add_argument("name")

    pf = sub.add_parser("password-for")
    pf.add_argument("account")

    sub.add_parser("verify")
    sub.add_parser("where")

    a = ap.parse_args()

    if a.cmd == "set":
        if a.from_env:
            val = os.environ.get(a.from_env)
            if not val:
                print(f"env {a.from_env} is empty/absent", file=sys.stderr)
                return 1
        elif a.stdin:
            val = sys.stdin.read().strip()
        else:
            print("use --from-env NAME or --stdin", file=sys.stderr)
            return 1
        if not val:
            print("empty secret refused", file=sys.stderr)
            return 1

        d = _read_store()
        d.setdefault("schema", 1)
        d.setdefault("created_at", _now())
        d["updated_at"] = _now()
        if a.name:
            d.setdefault("secrets", {})[a.name] = {"value": val, "updated_at": _now()}
            print(f"stored secret {a.name} ({len(val)} chars)")
        elif a.account:
            d.setdefault("accounts", {})[a.account] = {"password": val, "updated_at": _now()}
            print(f"stored password for {a.account} ({len(val)} chars)")
            if not a.no_master:
                d["master_password"] = val
                d["applies_to"] = "all_accounts"
                print(f"also set as shared master ({len(val)} chars)")
        else:
            d["master_password"] = val
            d["applies_to"] = "all_accounts"
            print(f"stored shared master password ({len(val)} chars)")
        _write_store(d)
        return 0

    if a.cmd == "get":
        v = os.environ.get(a.name) or _get_secret(a.name)
        if not v:
            d = _read_store()
            if a.name in MASTER_NAMES:
                v = d.get("master_password")
            else:
                v = ((d.get("secrets") or {}).get(a.name, {}) or {}).get("value") \
                    or (d.get("accounts") or {}).get(a.name, {}).get("password")
        if not v:
            print("not found", file=sys.stderr)
            return 1
        sys.stdout.write(v)
        return 0

    if a.cmd == "password-for":
        v = password_for(a.account)
        if not v:
            print("not found", file=sys.stderr)
            return 1
        sys.stdout.write(v)
        return 0

    if a.cmd == "verify":
        print(json.dumps(verify(), ensure_ascii=False, indent=1))
        return 0

    if a.cmd == "where":
        d = _read_store()
        print(json.dumps({
            "env": [n for n in MASTER_NAMES if os.environ.get(n)],
            "file": bool(d.get("master_password")),
            "secret_store": bool(_get_secret(MASTER_NAMES[0])) if (os.environ.get("AGENT_SERVER_URL") or os.environ.get("SANDBOX_ID")) else "unreachable-here",
        }, ensure_ascii=False, indent=1))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
