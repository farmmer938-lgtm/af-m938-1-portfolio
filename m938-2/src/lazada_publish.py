#!/usr/bin/env python3
"""Publish the m938-2 POD designs to K's Lazada shop via the Open Platform API.

Runs unattended once the seller authorization is done (see lazada_authorize.py):
it confirms the token, resolves a t-shirt category, uploads a mockup image for
each design and creates the product. Re-running is safe — a design whose SKU
already exists on the shop is skipped.

Usage:
  python3 lazada_publish.py preflight                 # is a usable token present?
  python3 lazada_publish.py categories "เสื้อยืด"      # find a category id
  python3 lazada_publish.py attrs <category_id>       # required attributes
  python3 lazada_publish.py list                      # products already on the shop
  python3 lazada_publish.py create [pack.json] <cat_id> [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lazada_client import LazadaClient, DEFAULT_SECRETS, build_product_payload  # noqa: E402

REPO = HERE.parent
DEFAULT_PACK = REPO / "out" / "pack.json"
TOKENS = "/workspace/.secrets/lazada.json"
SIZES = ["S", "M", "L", "XL", "2XL"]


def client() -> LazadaClient:
    c = LazadaClient.from_secrets(DEFAULT_SECRETS)
    env = os.environ.get("LAZADA_ACCESS_TOKEN")
    if env:
        c.access_token = env
    return c


def cmd_preflight(_a) -> int:
    c = client()
    if not c.access_token:
        print("no access_token in %s — run lazada_authorize.py watch first" % DEFAULT_SECRETS)
        return 1
    info = c.seller()
    print(json.dumps(info, ensure_ascii=False)[:400])
    ok = str(info.get("code")) == "0"
    print("token usable:", ok)
    return 0 if ok else 1


def cmd_categories(a) -> int:
    print(json.dumps(client().find_category(a.keyword), ensure_ascii=False, indent=2))
    return 0


def cmd_attrs(a) -> int:
    out = client().category_attributes(int(a.category_id))
    data = out.get("data") or []
    required = [x for x in data if str(x.get("is_mandatory")).lower() in ("true", "1", "yes")]
    print(json.dumps({"required": required, "all_count": len(data)}, ensure_ascii=False, indent=2)[:4000])
    return 0


def cmd_list(a) -> int:
    out = client().list_products(limit=a.limit)
    items = (out.get("data") or {}).get("products") or []
    for it in items:
        print(it.get("item_id"), "|", it.get("attributes", {}).get("name", "")[:60],
              "| skus:", len(it.get("skus") or []))
    print("total:", len(items))
    return 0


def _mockup_for(listing: dict) -> Path:
    p = listing.get("mockup")
    if p:
        return (REPO / p) if not Path(p).is_absolute() else Path(p)
    return REPO / "out" / "mockups" / (listing["slug"] + ".jpg")


def resolve_category(c: LazadaClient) -> int:
    """Best-effort t-shirt category: search common Thai/English keywords, prefer a leaf."""
    for kw in ("เสื้อยืด", "เสื้อ", "t-shirt", "t shirt", "fashion"):
        hits = [h for h in c.find_category(kw) if h.get("leaf")]
        if hits:
            return int(hits[0]["id"])
    return 0


def cmd_create(a) -> int:
    c = client()
    pack = json.loads(Path(a.pack).read_text(encoding="utf-8"))
    items = pack if isinstance(pack, list) else [pack]
    if a.limit:
        items = items[:a.limit]

    cat = int(a.category_id) if str(a.category_id).isdigit() and int(a.category_id) else 0
    if not cat and not a.dry_run:
        cat = resolve_category(c)
        print("resolved category:", cat)
    if not cat and not a.dry_run:
        print("could not resolve a t-shirt category; pass one explicitly")
        return 1

    existing = set()
    if not a.dry_run:
        out = c.list_products(limit=100)
        for it in (out.get("data") or {}).get("products") or []:
            for sku in it.get("skus") or []:
                existing.add(sku.get("SellerSku"))

    created = 0
    for it in items:
        sku0 = "%s-S" % it["slug"]
        if sku0 in existing:
            print("skip (already listed):", it["slug"])
            continue
        img = _mockup_for(it)
        payload = build_product_payload(it, cat, ["https://placeholder.invalid/main.jpg"])
        if a.dry_run:
            print("DRY-RUN", it["slug"], "| image:", img.name, img.exists(),
                  "| skus:", [s["SellerSku"] for s in payload["Request"]["Product"]["Skus"]["Sku"]])
            continue
        if not img.exists():
            print("MISSING image, skip:", img)
            continue
        up = c.upload_image(img)
        url = up.get("image", {}).get("url") if isinstance(up.get("image"), dict) else up.get("url")
        if not url:
            print("image upload failed:", json.dumps(up, ensure_ascii=False)[:200])
            continue
        payload = build_product_payload(it, cat, [url])
        res = c.create_product(payload)
        print("create", it["slug"], "->", json.dumps(res, ensure_ascii=False)[:220])
        if str(res.get("code")) == "0":
            created += 1
    print("created:", created, "/", len(items))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight").set_defaults(fn=cmd_preflight)
    p = sub.add_parser("categories"); p.add_argument("keyword"); p.set_defaults(fn=cmd_categories)
    p = sub.add_parser("attrs"); p.add_argument("category_id"); p.set_defaults(fn=cmd_attrs)
    p = sub.add_parser("list"); p.add_argument("--limit", type=int, default=50); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("create")
    p.add_argument("category_id")
    p.add_argument("--pack", default=str(DEFAULT_PACK))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_create)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
