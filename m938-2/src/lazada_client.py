#!/usr/bin/env python3
"""Lazada Open Platform client for AF (project m938-2).

Purpose: push the m938-2 POD listings onto K's Lazada shop through the official
Open Platform API instead of hand-uploading each one. K authorizes the app once;
after that AF can create/update products, upload images and read orders.

Auth model (LazOP 2.0, OAuth 2.0 "code for token"):
  1. build_auth_url()  -> K opens it, logs in with the Lazada seller account, approves
  2. K lands on the callback URL with ?code=...
  3. create_token(code) -> access_token (short lived) + refresh_token (long lived)
  4. every call signs its params with HMAC-SHA256(app_secret)

Signature (verified against Lazada's published test vector in test_lazada_client.py):
  sort params by key (exclude `sign`) -> concat key+value -> prepend api path
  -> HMAC-SHA256(app_secret) -> UPPERCASE hex

Credentials are read from a JSON file (default /workspace/.secrets/lazada.json):
  {"app_key": "...", "app_secret": "...", "access_token": "...", "refresh_token": "..."}

CLI:
  python3 lazada_client.py auth-url
  python3 lazada_client.py token <code>
  python3 lazada_client.py whoami
  python3 lazada_client.py categories "เสื้อยืด"
  python3 lazada_client.py attributes <category_id>
  python3 lazada_client.py upload-images <print.png> [<print2.png> ...]
  python3 lazada_client.py build <pack.json> <category_id>   # dry run, prints payloads
  python3 lazada_client.py create <pack.json> <category_id> [slug]  # LIVE
"""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AUTH_BASE = "https://auth.lazada.com/rest"
# Country gateways. Thailand is the m938-2 target.
ENDPOINTS = {
    "th": "https://api.lazada.co.th/rest",
    "sg": "https://api.lazada.sg/rest",
    "my": "https://api.lazada.com.my/rest",
    "ph": "https://api.lazada.com.ph/rest",
    "id": "https://api.lazada.co.id/rest",
    "vn": "https://api.lazada.vn/rest",
}
DEFAULT_SECRETS = Path("/workspace/.secrets/lazada.json")


def sign(api_path: str, params: dict, app_secret: str) -> str:
    """HMAC-SHA256 signature exactly as Lazada specifies. Returns uppercase hex."""
    parts = [k for k in params if k != "sign" and params[k] is not None]
    parts.sort()
    base = api_path + "".join(f"{k}{params[k]}" for k in parts)
    return hmac.new(app_secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest().upper()


class LazadaError(RuntimeError):
    def __init__(self, api_path: str, body: str, status: int):
        super().__init__(f"{api_path} -> HTTP {status}: {body[:400]}")
        self.api_path = api_path
        self.body = body
        self.status = status


class LazadaClient:
    def __init__(self, app_key: str, app_secret: str, country: str = "th",
                 access_token: str | None = None, timeout: int = 30):
        if country not in ENDPOINTS:
            raise ValueError(f"unknown country {country!r}; one of {sorted(ENDPOINTS)}")
        self.app_key = app_key
        self.app_secret = app_secret
        self.country = country
        self.access_token = access_token
        self.timeout = timeout
        self.base = ENDPOINTS[country]

    # ---- credentials -----------------------------------------------------
    @classmethod
    def from_secrets(cls, path: str | os.PathLike = DEFAULT_SECRETS, **kw) -> "LazadaClient":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["app_key"], data["app_secret"],
                   country=data.get("country", "th"),
                   access_token=data.get("access_token"), **kw)

    def save_tokens(self, path: str | os.PathLike, **tokens) -> None:
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        data.update({k: v for k, v in tokens.items() if v is not None})
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ---- signing / transport --------------------------------------------
    def _common(self, api_path: str, extra: dict, use_token: bool) -> dict:
        params = {
            "app_key": self.app_key,
            "timestamp": str(int(time.time() * 1000)),
            "sign_method": "sha256",
        }
        if use_token and self.access_token:
            params["access_token"] = self.access_token
        for k, v in extra.items():
            if v is not None:
                params[k] = v
        params["sign"] = sign(api_path, params, self.app_secret)
        return params

    def call(self, api_path: str, params: dict | None = None, *,
             use_token: bool = True, base: str | None = None,
             files: dict | None = None) -> dict:
        """Call an API path. `files` maps a field name to (filename, bytes, mime)."""
        signed = self._common(api_path, params or {}, use_token)
        url = (base or self.base) + api_path
        if files:
            body, ctype = _multipart(signed, files)
        else:
            body = urllib.parse.urlencode(signed).encode("utf-8")
            ctype = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                status = r.status
        except urllib.error.HTTPError as e:
            raw, status = e.read().decode("utf-8", "replace"), e.code
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            raise LazadaError(api_path, raw, status) from None
        code = str(out.get("code", ""))
        if status >= 400 or (code and code != "0"):
            raise LazadaError(api_path, json.dumps(out, ensure_ascii=False), status)
        return out

    # ---- auth ------------------------------------------------------------
    def build_auth_url(self, redirect_uri: str, force_auth: bool = True, state: str = "") -> str:
        q = {
            "response_type": "code",
            "force_auth": "true" if force_auth else "false",
            "redirect_uri": redirect_uri,
            "client_id": self.app_key,
        }
        if state:
            q["state"] = state
        return "https://auth.lazada.com/oauth/authorize?" + urllib.parse.urlencode(q)

    def create_token(self, code: str) -> dict:
        out = self.call("/auth/token/create", {"code": code},
                        use_token=False, base=AUTH_BASE)
        if out.get("access_token"):
            self.access_token = out["access_token"]
        return out

    def refresh_token(self, refresh_token: str) -> dict:
        out = self.call("/auth/token/refresh", {"refresh_token": refresh_token},
                        use_token=False, base=AUTH_BASE)
        if out.get("access_token"):
            self.access_token = out["access_token"]
        return out

    # ---- seller / catalog ------------------------------------------------
    def seller(self) -> dict:
        return self.call("/seller/get")

    def category_tree(self, parent_id: int = 0) -> dict:
        return self.call("/category/tree/get", {"parent_category_id": parent_id})

    def category_attributes(self, category_id: int) -> dict:
        return self.call("/category/attributes/get", {"primary_category_id": category_id})

    def find_category(self, keyword: str) -> list[dict]:
        """Breadth-first search of the category tree for a Thai/English keyword."""
        kw = keyword.lower()
        hits, queue = [], [0]
        seen = set()
        while queue:
            pid = queue.pop(0)
            if pid in seen:
                continue
            seen.add(pid)
            data = self.category_tree(pid).get("data", []) or []
            for node in data:
                name = str(node.get("name", ""))
                if kw in name.lower():
                    hits.append({"id": node.get("category_id"), "name": name,
                                 "leaf": bool(node.get("leaf")), "parent": pid})
                if not node.get("leaf"):
                    queue.append(node.get("category_id"))
        return hits

    # ---- media -----------------------------------------------------------
    def upload_image(self, path: str | os.PathLike) -> dict:
        p = Path(path)
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        out = self.call("/image/upload", {},
                        files={"image": (p.name, p.read_bytes(), mime)})
        return out.get("data", out)

    # ---- product ---------------------------------------------------------
    def create_product(self, payload: dict) -> dict:
        return self.call("/product/create", {"payload": json.dumps(payload, ensure_ascii=False)})

    def get_product(self, item_id: int) -> dict:
        return self.call("/product/item/get", {"item_id": item_id})

    def list_products(self, limit: int = 50, offset: int = 0) -> dict:
        return self.call("/products/get", {"limit": limit, "offset": offset})


def build_product_payload(listing: dict, category_id: int, image_urls: list[str],
                          *, brand: str = "No Brand", warranty_type: str = "Local seller warranty",
                          warranty: str = "1 Month") -> dict:
    """Assemble a Lazada CreateProduct payload from one m938-2 pack.json item.

    `image_urls` are Lazada inlinks returned by upload_image(). The first is the
    product main image; the rest become SKU images.
    """
    if not image_urls:
        raise ValueError("at least one Lazada image URL is required")
    attrs = {
        "name": listing["title"][:255],
        "description": listing.get("description", "")[:25000],
        "brand": brand,
        "model": listing["slug"],
        "warranty_type": warranty_type,
        "warranty": warranty,
    }
    if listing.get("keywords"):
        attrs["keywords"] = listing["keywords"]
    sizes = ["S", "M", "L", "XL", "2XL"]
    skus = [{
        "SellerSku": f"{listing['slug']}-{size}",
        "quantity": 100,
        "price": listing["price_thb"],
        "Images": {"Image": image_urls},
        "size": size,
    } for size in sizes]
    return {
        "Request": {
            "Product": {
                "PrimaryCategory": str(category_id),
                "Images": {"Image": image_urls[:8]},
                "Attributes": attrs,
                "Skus": {"Sku": skus},
            }
        }
    }


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = "----AFm938" + hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
    out = bytearray()
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fname, data, mime) in files.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                f"filename=\"{fname}\"\r\nContent-Type: {mime}\r\n\r\n").encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _cli(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    secrets = os.environ.get("LAZADA_SECRETS", str(DEFAULT_SECRETS))
    if cmd == "auth-url":
        c = LazadaClient.from_secrets(secrets)
        redirect = rest[0] if rest else "https://localhost/callback"
        print(c.build_auth_url(redirect))
        return 0
    if cmd in ("token", "refresh"):
        c = LazadaClient.from_secrets(secrets)
        out = c.create_token(rest[0]) if cmd == "token" else c.refresh_token(rest[0])
        c.save_tokens(secrets, access_token=out.get("access_token"),
                      refresh_token=out.get("refresh_token"))
        print(json.dumps({k: out.get(k) for k in
                          ("access_token", "refresh_token", "expires_in", "country")}, indent=2))
        return 0
    c = LazadaClient.from_secrets(secrets)
    if cmd == "whoami":
        print(json.dumps(c.seller(), ensure_ascii=False, indent=2))
    elif cmd == "categories":
        print(json.dumps(c.find_category(rest[0]), ensure_ascii=False, indent=2))
    elif cmd == "attributes":
        print(json.dumps(c.category_attributes(int(rest[0])), ensure_ascii=False, indent=2))
    elif cmd == "upload-images":
        for p in rest:
            print(json.dumps(c.upload_image(p), ensure_ascii=False))
    elif cmd == "build":
        pack = json.loads(Path(rest[0]).read_text(encoding="utf-8"))
        cat = int(rest[1])
        items = pack if isinstance(pack, list) else [pack]
        for it in items:
            payload = build_product_payload(it, cat, ["https://example/main.jpg"])
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"unknown command {cmd!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
