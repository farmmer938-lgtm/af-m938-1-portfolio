#!/usr/bin/env python3
"""m938-2 — build the per-design upload pack + a self-contained AF storefront.

Inputs : portfolio/pod/listings.json (m938-1 copy), portfolio/pod/designs.json,
         out/print/<slug>.png, out/mockups/<slug>.jpg
Outputs: out/pack.json, out/UPLOAD_GUIDE.md, out/store.html
"""
import base64, json, html, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LISTINGS = json.loads((ROOT / "listings.json").read_text(encoding="utf-8"))
DESIGNS = {d["slug"]: d for d in json.loads((ROOT / "designs.json").read_text(encoding="utf-8"))}

COST = 110          # do.ink production per shirt (THB)
PRICE = 199         # entry price
PRICE_UP = 249
GP = 0.1160         # Lazada SME GP upper bound (rollback), used conservatively
TXN = 0.0321        # Lazada transaction fee


def net_profit(price):
    return round(price - COST - price * (GP + TXN))


def build():
    pack, cards = [], []
    for L in LISTINGS:
        slug = L["slug"]
        d = DESIGNS.get(slug, {"title": slug, "sub": ""})
        desc = (L["รายละเอียดสินค้า"].split("\n\n📌")[0]
                + "\n\n📌 รายละเอียด\n"
                "• เสื้อยืดพิมพ์ลาย DTG งานพิมพ์เนียน สีติดทน\n"
                "• ไซส์ S / M / L / XL / 2XL (ระบุตอนสั่ง)\n"
                "• ผลิตตามออร์เดอร์จากในไทย จัดส่ง 1-3 วัน\n"
                "• เนื้อผ้าใส่สบาย ระบายอากาศดี\n\n"
                "📦 สั่งแล้วรอรับที่บ้านได้เลย (Do.ink ผลิต+แพ็ค+ส่ง)")
        item = {
            "slug": slug,
            "print_file": f"out/print/{slug}.png",
            "print_spec": "PNG · 3600x4800 px · transparent · 300 DPI (12x16 in)",
            "mockup": f"out/mockups/{slug}.jpg",
            "title": L["ชื่อสินค้า"],
            "price_thb": PRICE,
            "price_premium_thb": PRICE_UP,
            "cost_thb": COST,
            "profit_thb_at_entry": net_profit(PRICE),
            "description": desc,
            "keywords": L["คีย์เวิร์ด"],
            "audience": L["กลุ่มเป้าหมาย"],
        }
        pack.append(item)
        cards.append((slug, item))

    (ROOT / "out/pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- UPLOAD_GUIDE.md ----
    g = ["# m938-2 — ชุดอัปโหลดสินค้า POD (Do.ink → Lazada)",
         "",
         f"ผลิต ฿{COST}/ตัว · ราคาขาย ฿{PRICE} → กำไรสุทธิประมาณ ฿{net_profit(PRICE)}/ตัว "
         f"(หัก GP Lazada {GP*100:.2f}% + txn {TXN*100:.2f}%)",
         "",
         "ไฟล์พิมพ์พร้อมอัปโหลดอยู่ที่ `out/print/<slug>.png` (PNG พื้นหลังโปร่งใส 300 DPI ตามสเปก Do.ink)",
         "รูปสินค้าสำหรับลงประกาศอยู่ที่ `out/mockups/<slug>.jpg`",
         ""]
    for slug, it in cards:
        g += [f"## {it['title']}", "",
              f"- **ไฟล์พิมพ์:** `{it['print_file']}` ({it['print_spec']})",
              f"- **รูปสินค้า:** `{it['mockup']}`",
              f"- **ราคา:** ฿{it['price_thb']} (พรีเมียม ฿{it['price_premium_thb']})",
              f"- **คีย์เวิร์ด:** {it['keywords']}",
              f"- **กลุ่มเป้าหมาย:** {it['audience']}", "",
              "```", it["description"], "```", ""]
    (ROOT / "out/UPLOAD_GUIDE.md").write_text("\n".join(g), encoding="utf-8")

    # ---- store.html (self-contained) ----
    def b64img(p):
        return base64.b64encode(p.read_bytes()).decode()

    tiles = []
    for slug, it in cards:
        d = DESIGNS.get(slug, {"title": slug, "sub": ""})
        img = b64img(ROOT / it["mockup"])
        subj = f"สั่งซื้อ {slug}"
        body = f"สนใจลาย {d['title']} — ขนาด (S/M/L/XL/2XL) : "
        tiles.append(f"""  <article class="card">
    <img src="data:image/jpeg;base64,{img}" alt="{html.escape(it['title'])}" loading="lazy">
    <h3>{html.escape(d['title'])}</h3>
    <p class="sub">{html.escape(d['sub'])}</p>
    <p class="price">฿{it['price_thb']} <span>รวมส่งในไทย</span></p>
    <a class="buy" href="mailto:af.m938.1@mail.tm?subject={html.escape(subj)}&body={html.escape(body)}">สั่งซื้อ</a>
  </article>""")
    store = f"""<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AF Tools — เสื้อพิมพ์ลายข้อความ 8 ลาย</title>
<style>
 :root{{--ink:#16181d;--muted:#6b7280;--line:#e5e7eb;--accent:#2563eb}}
 *{{box-sizing:border-box}}
 body{{margin:0;font-family:-apple-system,"Segoe UI",Roboto,"Noto Sans Thai",sans-serif;
      color:var(--ink);background:#fafafa;line-height:1.6;-webkit-text-size-adjust:100%}}
 .wrap{{max-width:980px;margin:0 auto;padding:22px 16px 80px}}
 header h1{{font-size:1.6rem;margin:.2em 0 .1em}}
 header p{{color:var(--muted);margin:0 0 18px}}
 .note{{background:#eff6ff;border-left:4px solid var(--accent);padding:12px 16px;
        border-radius:8px;margin:0 0 22px;font-size:.94rem}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}}
 .card{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px;
        display:flex;flex-direction:column}}
 .card img{{width:100%;border-radius:10px;display:block}}
 .card h3{{margin:12px 0 2px;font-size:1.05rem}}
 .card .sub{{margin:0;color:var(--muted);font-size:.85rem}}
 .price{{font-weight:700;margin:.5em 0}}
 .price span{{font-weight:400;color:var(--muted);font-size:.78rem}}
 .buy{{margin-top:auto;text-align:center;background:var(--accent);color:#fff;text-decoration:none;
       padding:11px;border-radius:9px;font-weight:600}}
 footer{{margin-top:34px;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding-top:16px}}
</style></head>
<body><div class="wrap">
<header>
  <h1>เสื้อพิมพ์ลายข้อความ — 8 ลาย</h1>
  <p>พิมพ์ DTG งานเนียน · ไซส์ S–2XL · ผลิตในไทย ส่ง 1–3 วัน</p>
</header>
<div class="note">📩 สั่งซื้อ: กด "สั่งซื้อ" ที่ลายที่ต้องการ ระบุไซส์ แล้วเราจะยืนยันกลับทางอีเมล<br>
ชำระเงิน: โอน / พร้อมเพย์ (แจ้งในอีเมลยืนยัน) · ราคารวมค่าส่งในไทยแล้ว</div>
<div class="grid">
{chr(10).join(tiles)}
</div>
<footer>AF Tools · ผลิตโดย Do.ink · รูปสินค้าเป็นภาพจำลอง สีจริงอาจต่างเล็กน้อยตามการแสดงผล</footer>
</div></body></html>"""
    (ROOT / "out/store.html").write_text(store, encoding="utf-8")

    print(f"pack.json: {len(pack)} items")
    print(f"store.html: {len(store)//1024} KB (self-contained)")
    print(f"profit/shirt @{PRICE}: ฿{net_profit(PRICE)} | @{PRICE_UP}: ฿{net_profit(PRICE_UP)}")


if __name__ == "__main__":
    build()
