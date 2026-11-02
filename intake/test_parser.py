"""Tests for the short-answer parser and split prompts."""
import json
import pytest

import intake
import parse_answers as pa
import split_prompts as sp

TIER1 = """1. YouTube ชื่อช่อง: เรื่องจริงในครัว
2. YouTube จำนวนผู้ติดตาม: 1,250
3. YouTube จำนวนคลิปทั้งหมด: 42
4. YouTube คลิปที่คนดูมากสุด (ชื่อ) + จำนวนวิว: ทำกับข้าวให้แฟน 85,000
5. Facebook ชื่อเพจ: ครัวเรื่องจริง
6. Facebook จำนวนผู้ติดตาม: 3,400
7. TikTok ชื่อบัญชี: @kitchen.real
8. TikTok จำนวนผู้ติดตาม: 8,900
9. Shopee: เป็น affiliate หรือ seller หรือทั้งสอง: ทั้งสอง
10. Shopee ขายหมวดอะไร: ของใช้ในครัว
11. Shopee ลิงก์ร้าน (ถ้ามี): shopee.co.th/kitchenreal
12. เป้าหมายรายได้ต่อเดือน (บาท): 5000
"""


def test_strip_label_removes_echoed_question():
    assert pa.strip_label("ชื่อช่อง: เรื่องจริงในครัว") == "เรื่องจริงในครัว"


def test_strip_label_keeps_url_with_scheme():
    assert pa.strip_label("https://shopee.co.th/x") == "https://shopee.co.th/x"


def test_strip_label_keeps_url_without_scheme():
    assert pa.strip_label("shopee.co.th/kitchenreal") == "shopee.co.th/kitchenreal"


def test_strip_label_empty_answer_is_empty():
    assert pa.strip_label("ชื่อช่อง:") == ""


def test_strip_label_no_separator_returns_input():
    assert pa.strip_label("ทั้งสอง") == "ทั้งสอง"


def test_strip_label_uses_last_separator():
    assert pa.strip_label("เป็น affiliate หรือ seller: ทั้งสอง") == "ทั้งสอง"


def test_parse_number_handles_commas():
    assert pa.parse_number("1,250") == 1250


def test_parse_number_handles_float():
    assert pa.parse_number("4.5") == 4.5


def test_parse_number_unknown_on_text():
    assert pa.parse_number("ไม่รู้") == intake.UNKNOWN


def test_parse_number_unknown_on_none():
    assert pa.parse_number(None) == intake.UNKNOWN


def test_parse_lines_maps_numbers():
    lines = pa.parse_lines(TIER1)
    assert set(lines) == set(range(1, 13))
    assert lines[1] == "เรื่องจริงในครัว"


def test_tier1_report_extracts_numbers():
    r = pa.tier1_to_report(TIER1)
    ch = r["channels"][0]
    assert ch["channel_name"] == "เรื่องจริงในครัว"
    assert ch["subscribers"] == 1250
    assert ch["total_videos"] == 42
    assert r["other_platforms"]["facebook"]["followers"] == 3400
    assert r["other_platforms"]["tiktok"]["followers"] == 8900
    assert r["shopee"]["role"] == "ทั้งสอง"
    assert r["goal_thb_per_month"] == 5000


def test_tier1_report_uses_unknown_for_missing_lines():
    r = pa.tier1_to_report("1. YouTube ชื่อช่อง: ช่องเอ\n2. YouTube จำนวนผู้ติดตาม: 10")
    ch = r["channels"][0]
    assert ch["subscribers"] == 10
    assert ch["avg_views_last_10"] == intake.UNKNOWN
    assert r["shopee"]["category"] == intake.UNKNOWN


def test_tier1_report_passes_its_own_validator():
    rep = intake.validate_report(pa.tier1_to_report(TIER1))
    assert rep["ok"] is True


def test_youtube_platform_round():
    text = """1. ชื่อช่อง: ครัวจริง
2. ลิงก์ช่อง: youtube.com/@real
3. หมวดเนื้อหา: ทำอาหาร
4. จำนวนผู้ติดตาม: 1,250
5. จำนวนคลิปทั้งหมด: 42
6. อัปโหลดกี่คลิปต่อสัปดาห์: 3
7. คลิป 10 อันล่าสุด เฉลี่ยกี่วิว: 800
8. คลิปที่คนดูมากสุด 3 อัน (ชื่อ + วิว): ทำกับข้าวให้แฟน
9. ส่วนใหญ่เป็น Shorts หรือคลิปยาว หรือผสม: mixed
10. ได้รายได้จาก YouTube แล้วหรือยัง: false
11. รายได้ต่อเดือน (บาท): 0
12. ปัญหาหลักที่ทำให้ช่องไม่โต: คนดูไม่กดติดตาม
13. อยากให้ช่วยเรื่องอะไร: สคริปต์
"""
    r = pa.platform_to_report(text, "youtube")
    ch = r["channels"][0]
    assert ch["channel_name"] == "ครัวจริง"
    assert ch["subscribers"] == 1250
    assert ch["uploads_per_week"] == 3
    assert ch["format"] == "mixed"
    assert intake.validate_report(r)["ok"] is True


def test_shopee_platform_round_keeps_unknowns():
    text = """1. เป็น affiliate หรือ seller: affiliate
2. ลิงก์ร้าน: UNKNOWN
3. ขายหมวดอะไร: ของใช้
4. ค่าคอมมิชชั่น: UNKNOWN
5. คลิก 30 วัน: UNKNOWN
6. ออเดอร์ 30 วัน: UNKNOWN
7. รายได้ 30 วัน: UNKNOWN
8. หมวดที่ขายดี: UNKNOWN
9. แปะลิงก์ที่ไหน: ไบโอ
10. อุปสรรค: ไม่มีคนคลิก
"""
    r = pa.platform_to_report(text, "shopee")
    assert r["answers"]["role"] == "affiliate"
    assert r["answers"]["url"] == intake.UNKNOWN
    assert r["answers"]["link_placement"] == "ไบโอ"


def test_merge_combines_tier1_and_platform_rounds():
    t1 = pa.tier1_to_report(TIER1)
    fb = pa.platform_to_report("1. ชื่อเพจ: ครัว\n2. ลิงก์เพจ: UNKNOWN\n3. ผู้ติดตาม: 50",
                               "facebook")
    merged = pa.merge_reports([t1, fb])
    assert merged["channels"][0]["subscribers"] == 1250
    assert "facebook" in merged["other_platforms"]


def test_split_prompts_are_small():
    counts = sp.field_count()
    assert counts["tier1"] <= 15
    assert all(counts[k] <= 13 for k in ("youtube", "facebook", "tiktok", "shopee"))


def test_split_prompts_render_contains_each_round():
    text = sp.render()
    for name in ("รอบที่ 1", "รอบ 2A", "รอบ 2B", "รอบ 2C", "รอบ 2D"):
        assert name in text


def test_split_prompts_only_filter():
    text = sp.render("shopee")
    assert "รอบ 2D" in text
    assert "รอบ 2A" not in text


def test_split_rounds_ask_fewer_fields_than_the_original():
    # the original AI2 prompt asked ~37 fields in one reply
    counts = sp.field_count()
    assert sum(counts.values()) < 37 or max(counts.values()) < 15


def test_every_split_prompt_has_numbered_questions():
    for k, v in sp.SPLITS.items():
        numbered = [l for l in v["prompt"].splitlines() if l.strip()[:2].rstrip(".").isdigit()]
        assert len(numbered) == len(pa.PLATFORM_FIELDS[k]), k
