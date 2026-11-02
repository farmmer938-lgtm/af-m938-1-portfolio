#!/usr/bin/env python3
"""Split the AI2 request into small, independently-answerable prompts.

Root cause of the limit: the original AI2 prompt asked for ~37 fields across
4 platforms in one reply, which overflows the output budget. Fix: ask for one
platform at a time, smallest first, and merge the answers locally.

Zero dependencies.
"""
import json

TIER1 = {
    "name": "รอบที่ 1 — ตัวเลขที่จำเป็นที่สุด (ตอบสั้น ไม่เกิน 12 บรรทัด)",
    "prompt": """ตอบสั้น ๆ ตามนี้ ไม่ต้องอธิบาย ไม่ต้องจัดรูปแบบสวย
ถ้าไม่รู้ให้เขียน UNKNOWN

1. YouTube ชื่อช่อง:
2. YouTube จำนวนผู้ติดตาม:
3. YouTube จำนวนคลิปทั้งหมด:
4. YouTube คลิปที่คนดูมากสุด (ชื่อ) + จำนวนวิว:
5. Facebook ชื่อเพจ:
6. Facebook จำนวนผู้ติดตาม:
7. TikTok ชื่อบัญชี:
8. TikTok จำนวนผู้ติดตาม:
9. Shopee: เป็น affiliate หรือ seller หรือทั้งสอง:
10. Shopee ขายหมวดอะไร:
11. Shopee ลิงก์ร้าน (ถ้ามี):
12. เป้าหมายรายได้ต่อเดือน (บาท):""",
}

SPLITS = {
    "youtube": {
        "name": "รอบ 2A — YouTube เท่านั้น",
        "prompt": """ตอบเฉพาะ YouTube ไม่ต้องพูดถึงอย่างอื่น ตอบสั้น ไม่ต้องอธิบาย

1. ชื่อช่อง:
2. ลิงก์ช่อง:
3. หมวดเนื้อหา:
4. จำนวนผู้ติดตาม:
5. จำนวนคลิปทั้งหมด:
6. อัปโหลดกี่คลิปต่อสัปดาห์:
7. คลิป 10 อันล่าสุด เฉลี่ยกี่วิว:
8. คลิปที่คนดูมากสุด 3 อัน (ชื่อ + วิว):
9. ส่วนใหญ่เป็น Shorts หรือคลิปยาว หรือผสม:
10. ได้รายได้จาก YouTube แล้วหรือยัง:
11. รายได้ต่อเดือน (บาท):
12. ปัญหาหลักที่ทำให้ช่องไม่โต:
13. อยากให้ช่วยเรื่องอะไร:""",
    },
    "facebook": {
        "name": "รอบ 2B — Facebook เท่านั้น",
        "prompt": """ตอบเฉพาะ Facebook ตอบสั้น ไม่ต้องอธิบาย
ถ้าไม่มีเพจ Facebook ให้เขียนว่า ไม่มี

1. ชื่อเพจ:
2. ลิงก์เพจ:
3. จำนวนผู้ติดตาม:
4. โพสต์กี่ครั้งต่อสัปดาห์:
5. โพสต์แต่ละอันมีคนเห็นเฉลี่ยกี่คน:
6. โพสต์แบบไหนคนสนใจมากสุด:
7. เพจนี้ทำเงินได้ไหม ถ้าได้ได้เท่าไหร่ต่อเดือน:""",
    },
    "tiktok": {
        "name": "รอบ 2C — TikTok เท่านั้น",
        "prompt": """ตอบเฉพาะ TikTok ตอบสั้น ไม่ต้องอธิบาย
ถ้าไม่มี TikTok ให้เขียนว่า ไม่มี

1. ชื่อบัญชี (@):
2. จำนวนผู้ติดตาม:
3. จำนวนคลิปทั้งหมด:
4. คลิปเฉลี่ยกี่วิว:
5. คลิปที่คนดูมากสุด (ชื่อ + วิว):
6. ได้รายได้จาก TikTok แล้วหรือยัง:""",
    },
    "shopee": {
        "name": "รอบ 2D — Shopee เท่านั้น (สำคัญที่สุด)",
        "prompt": """ตอบเฉพาะ Shopee ตอบสั้น ไม่ต้องอธิบาย
ถ้าไม่รู้ให้เขียน UNKNOWN

1. เป็น affiliate (แปะลิงก์) หรือ seller (ขายเอง) หรือทั้งสอง:
2. ลิงก์ร้าน/ลิงก์ affiliate:
3. ขาย/แนะนำสินค้าหมวดอะไร:
4. ค่าคอมมิชชั่นที่ได้ (เปอร์เซ็นต์):
5. 30 วันล่าสุด มีคนคลิกลิงก์กี่ครั้ง:
6. 30 วันล่าสุด ได้กี่ออเดอร์:
7. 30 วันล่าสุด ได้เงินเท่าไหร่ (บาท):
8. หมวดไหนขายได้ดีสุด:
9. แปะลิงก์ไว้ตรงไหน (ไบโอ/คอมเมนต์/ในคลิป):
10. อะไรคืออุปสรรคที่ทำให้ยังขายไม่ได้มาก:""",
    },
}

ORDER = ["youtube", "facebook", "tiktok", "shopee"]


def render(which=None):
    out = ["=" * 60, TIER1["name"], "=" * 60, TIER1["prompt"], ""]
    keys = [which] if which else ORDER
    for k in keys:
        s = SPLITS[k]
        out += ["=" * 60, s["name"], "=" * 60, s["prompt"], ""]
    return "\n".join(out)


def field_count():
    """How many answer lines each round asks for."""
    counts = {"tier1": TIER1["prompt"].count("\n")}
    for k, v in SPLITS.items():
        counts[k] = sum(1 for line in v["prompt"].splitlines() if line.strip()[:2].rstrip(".").isdigit())
    return counts


def merge(parts):
    """Merge partial plain-text answers into one report skeleton."""
    return {"account_label": "AI2", "partial": parts,
            "note": "merged from split rounds; UNKNOWN kept as-is"}


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="แบ่งพร้อมท์ AI2 เป็นรอบเล็ก ๆ")
    p.add_argument("--only", choices=ORDER, default=None)
    p.add_argument("--counts", action="store_true")
    a = p.parse_args(argv)
    if a.counts:
        print(json.dumps(field_count(), ensure_ascii=False, indent=2))
    else:
        print(render(a.only))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
