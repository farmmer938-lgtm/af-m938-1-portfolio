#!/usr/bin/env python3
"""Tests for the m938-2 POD pipeline. Run: python3 -m pytest test_pod_assets.py -q"""
import json, pathlib, struct, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
DESIGNS = json.loads((ROOT / "designs.json").read_text(encoding="utf-8"))


def png_header(p):
    d = p.read_bytes()[:33]
    assert d[:8] == b"\x89PNG\r\n\x1a\n", f"{p.name} not a PNG"
    w, h = struct.unpack(">II", d[16:24])
    return w, h, d[25]  # color type: 6 == RGBA


def test_all_print_files_exist_and_spec():
    for d in DESIGNS:
        p = OUT / "print" / f"{d['slug']}.png"
        assert p.exists(), f"missing print file {p}"
        w, h, ct = png_header(p)
        assert (w, h) == (3600, 4800), f"{p.name} wrong size {w}x{h}"
        assert ct == 6, f"{p.name} not RGBA (color type {ct}) -> no transparency"


def test_print_file_actually_transparent():
    # top-left pixel must be fully transparent (RGBA 0,0,0,0)
    import zlib
    raw = (OUT / "print" / "seller-boss.png").read_bytes()
    pos, idat = 8, b""
    while pos < len(raw):
        ln = struct.unpack(">I", raw[pos:pos + 4])[0]
        typ = raw[pos + 4:pos + 8]
        if typ == b"IDAT":
            idat += raw[pos + 8:pos + 8 + ln]
        pos += 12 + ln
    data = zlib.decompress(idat)
    assert data[0] == 0, "unexpected first scanline filter"
    assert data[1:5] == b"\x00\x00\x00\x00", "top-left pixel is not transparent"


def test_mockups_exist():
    for d in DESIGNS:
        assert (OUT / "mockups" / f"{d['slug']}.jpg").exists(), d["slug"]


def test_pack_complete():
    pack = json.loads((OUT / "pack.json").read_text(encoding="utf-8"))
    assert len(pack) == len(DESIGNS) == 8
    for it in pack:
        for k in ("slug", "print_file", "title", "price_thb", "description", "keywords"):
            assert it.get(k), f"{it.get('slug')} missing {k}"
        assert it["price_thb"] >= it["cost_thb"], "price below cost"


def test_profit_positive():
    from make_kit import net_profit, COST, PRICE
    assert net_profit(PRICE) > 0
    assert net_profit(COST) < 0  # selling at cost loses money (fee sanity)


def test_store_html_has_all_cards():
    html = (OUT / "store.html").read_text(encoding="utf-8")
    assert html.count('class="card"') == 8
    assert html.count("data:image/jpeg;base64,") == 8
    assert "สั่งซื้อ" in html


def test_designs_have_thai_text():
    for d in DESIGNS:
        assert re.search(r"[\u0E00-\u0E7F]", d["title"]), f"{d['slug']} title not Thai"
