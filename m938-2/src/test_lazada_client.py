#!/usr/bin/env python3
"""Tests for lazada_client.py. No network: signature, payloads, encoding only."""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lazada_client import (  # noqa: E402
    LazadaClient, build_product_payload, sign, _multipart,
)

# Lazada's own published example. app_secret "helloworld", path "/order/get".
# Source: open.lazada.com Developer's Guide, signature algorithm section.
DOC_PARAMS = {
    "access_token": "test",
    "app_key": "123456",
    "order_id": "1234",
    "sign_method": "sha256",
    "timestamp": "1517820392000",
}
DOC_EXPECTED = "4190D32361CFB9581350222F345CB77F3B19F0E31D162316848A2C1FFD5FAB4A"


def test_signature_matches_official_vector():
    assert sign("/order/get", DOC_PARAMS, "helloworld") == DOC_EXPECTED


def test_signature_ignores_sign_param_and_none():
    with_sign = dict(DOC_PARAMS, sign="SHOULD_BE_IGNORED", extra=None)
    assert sign("/order/get", with_sign, "helloworld") == DOC_EXPECTED


def test_signature_is_order_independent_but_param_order_matters():
    shuffled = dict(reversed(list(DOC_PARAMS.items())))
    assert sign("/order/get", shuffled, "helloworld") == DOC_EXPECTED
    # a different path yields a different signature
    assert sign("/order/items/get", DOC_PARAMS, "helloworld") != DOC_EXPECTED


def test_signature_is_uppercase_hex_64():
    s = sign("/x", {"a": "1"}, "secret")
    assert len(s) == 64 and s == s.upper() and all(c in "0123456789ABCDEF" for c in s)


def _client(**kw):
    return LazadaClient("ak", "as", "th", access_token="tok", **kw)


def test_auth_url_contains_required_fields():
    url = _client().build_auth_url("https://x/cb", state="s1")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert urllib.parse.urlparse(url).netloc == "auth.lazada.com"
    assert q["response_type"] == "code"
    assert q["client_id"] == "ak"
    assert q["redirect_uri"] == "https://x/cb"
    assert q["force_auth"] == "true"
    assert q["state"] == "s1"


def test_unknown_country_rejected():
    with pytest.raises(ValueError):
        LazadaClient("a", "b", "zz")


def test_common_params_are_signed_and_token_included():
    c = _client()
    p = c._common("/product/create", {"payload": "{}"}, use_token=True)
    assert p["app_key"] == "ak" and p["sign_method"] == "sha256"
    assert p["access_token"] == "tok"
    assert p["sign"] == sign("/product/create", p, "as")


def test_common_params_exclude_token_when_asked():
    c = _client()
    p = c._common("/auth/token/create", {"code": "c"}, use_token=False)
    assert "access_token" not in p


LISTING = {
    "slug": "seller-boss",
    "title": "เสื้อเจ้านายตัวเอง ไม่ต้องขอใครลา",
    "description": "รายละเอียดสินค้า",
    "price_thb": 199,
    "keywords": "เสื้อแม่ค้า, เจ้านายตัวเอง",
}


def test_build_payload_structure():
    p = build_product_payload(LISTING, 10002019, ["https://img/1.jpg", "https://img/2.jpg"])
    prod = p["Request"]["Product"]
    assert prod["PrimaryCategory"] == "10002019"
    assert prod["Images"]["Image"] == ["https://img/1.jpg", "https://img/2.jpg"]
    assert prod["Attributes"]["name"] == LISTING["title"]
    assert prod["Attributes"]["brand"] == "No Brand"
    assert prod["Attributes"]["model"] == "seller-boss"
    skus = prod["Skus"]["Sku"]
    assert [s["size"] for s in skus] == ["S", "M", "L", "XL", "2XL"]
    assert all(s["price"] == 199 for s in skus)
    assert all(s["SellerSku"].startswith("seller-boss-") for s in skus)
    assert len({s["SellerSku"] for s in skus}) == 5  # unique SKU codes


def test_build_payload_rejects_no_image():
    with pytest.raises(ValueError):
        build_product_payload(LISTING, 1, [])


def test_build_payload_truncates_long_name():
    long_listing = dict(LISTING, title="ก" * 500)
    p = build_product_payload(long_listing, 1, ["https://i/1.jpg"])
    assert len(p["Request"]["Product"]["Attributes"]["name"]) == 255


def test_build_payload_is_json_serialisable_unicode():
    p = build_product_payload(LISTING, 1, ["https://i/1.jpg"])
    s = json.dumps(p, ensure_ascii=False)
    assert "เสื้อเจ้านายตัวเอง" in s


def test_build_payload_caps_main_images_at_eight():
    urls = [f"https://i/{n}.jpg" for n in range(12)]
    p = build_product_payload(LISTING, 1, urls)
    assert len(p["Request"]["Product"]["Images"]["Image"]) == 8


def test_multipart_encoding_has_boundary_and_file():
    body, ctype = _multipart({"app_key": "ak"}, {"image": ("p.png", b"\x89PNG", "image/png")})
    assert ctype.startswith("multipart/form-data; boundary=")
    assert b'name="app_key"' in body and b"ak" in body
    assert b'filename="p.png"' in body and b"\x89PNG" in body
    assert body.endswith(b"--\r\n")


def test_pack_json_feeds_payload_for_all_eight():
    pack = json.loads((ROOT / "out" / "pack.json").read_text(encoding="utf-8"))
    assert len(pack) == 8
    for item in pack:
        p = build_product_payload(item, 10002019, ["https://i/1.jpg"])
        assert p["Request"]["Product"]["Skus"]["Sku"]
        assert p["Request"]["Product"]["Attributes"]["name"]
