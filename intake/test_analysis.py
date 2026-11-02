"""Tests for the channel analysis and next-batch planner."""
import json
import pytest

import channel_analysis as ca
import next_batch as nb

REPORT = {
    "account_label": "AI1",
    "channels": [
        {
            "channel_name": "Farmmer — ธรรมะก่อนนอน",
            "niche": "ธรรมะก่อนนอน / สมาธิช่วยการนอน",
            "subscribers": 11, "total_videos": 11, "uploads_per_week": 9,
            "avg_views_last_10": 392,
            "top_videos": [
                {"title": "นอนไม่หลับ? ลองทำท่านี้ 10 วินาที #Shorts", "views": 1288},
                {"title": "เปิดทิ้งไว้ทั้งคืน หลับลึกถึงเช้า #Shorts", "views": 1233},
                {"title": "ก่อนนอนคืนนี้ ลองปล่อยวางสักเรื่อง #Shorts", "views": 1080},
            ],
            "format": "mixed", "monetized": False, "monthly_revenue_thb": 0,
            "biggest_problem": "long-form 2 views", "needs_help_with": "compilation",
        },
        {
            "channel_name": "เรื่องเล่าการ์ตูน",
            "niche": "เรื่องเล่า/ดราม่าครอบครัว ซีรีส์การ์ตูนไทย",
            "subscribers": 6, "total_videos": 10, "uploads_per_week": 7,
            "avg_views_last_10": 176,
            "top_videos": [
                {"title": "คืนนั้นแม่ทำกับข้าวให้เขา", "views": 1079},
                {"title": "เมล็ดที่รออยู่ใต้ดิน | เรื่องเล่าการ์ตูน #Shorts", "views": 107},
            ],
            "format": "mixed", "monetized": False, "monthly_revenue_thb": 0,
            "biggest_problem": "metaphor weak", "needs_help_with": "series",
        },
    ],
    "assets": [], "blockers": [],
}


def test_classify_question_hook():
    assert ca.classify_hook("นอนไม่หลับ? ลองทำท่านี้ 10 วินาที") == "question"


def test_classify_time_bound_hook():
    assert ca.classify_hook("หลับใน 10 นาที") == "time_promise"


def test_classify_relational_scene():
    assert ca.classify_hook("คืนนั้นแม่ทำกับข้าวให้เขา") == "relational_scene"


def test_classify_abstract_metaphor():
    assert ca.classify_hook("เมล็ดที่รออยู่ใต้ดิน") == "abstract_metaphor"


def test_classify_emotional_release():
    assert ca.classify_hook("ก่อนนอนคืนนี้ ลองปล่อยวางสักเรื่อง") in ("action_cta", "emotional")


def test_question_beats_action_when_both_present():
    # '?' is the strongest signal; must not be overridden by 'ลอง'
    assert ca.classify_hook("นอนไม่หลับ? ลองทำ") == "question"


def test_hook_performance_ranks_by_average():
    perf = ca.hook_performance(REPORT["channels"])
    keys = list(perf)
    avgs = [perf[k]["avg_views"] for k in keys]
    assert avgs == sorted(avgs, reverse=True)
    assert perf["relational_scene"]["max_views"] == 1079


def test_shorts_dominance_is_ratio_of_best_to_average():
    assert ca.shorts_share(REPORT["channels"][0]) == pytest.approx(1288 / 392, abs=0.01)


def test_shorts_dominance_handles_zero_average():
    assert ca.shorts_share({"avg_views_last_10": 0, "top_videos": [{"views": 5}]}) is None


def test_analyse_totals():
    a = ca.analyse(REPORT)
    assert a["channels"] == 2
    assert a["total_subs"] == 17
    assert a["total_videos"] == 21
    assert a["subs_gap_to_1000"] == 983


def test_ypp_math_gap_and_reachability():
    r = ca.ypp_math(11, 0, 489, days_active=16)
    assert r["subs_gap"] == 989
    assert r["reachable"] is False
    assert r["shorts_views_needed_multiple"] > 20000


def test_ypp_reachable_when_both_thresholds_met():
    r = ca.ypp_math(1200, 5000, 0)
    assert r["reachable"] is True
    assert r["subs_gap"] == 0


def test_patterns_match_sleep_channel():
    pats = nb.patterns_for(REPORT["channels"][0])
    assert "problem_fix" in pats


def test_patterns_match_story_channel():
    pats = nb.patterns_for(REPORT["channels"][1])
    assert "relational" in pats


def test_measured_best_hook_uses_highest_view_video():
    assert nb.measured_best(REPORT["channels"][0]) == "question"
    assert nb.measured_best(REPORT["channels"][1]) == "relational_scene"


def test_plan_never_reuses_a_published_title():
    published = nb.published_titles(REPORT)
    plan = nb.build(REPORT)
    for ch in plan["channels"]:
        for item in ch["next_shorts"] + ch["next_long"]:
            assert item["title"] not in published


def test_plan_has_no_duplicates_inside_a_batch():
    plan = nb.build(REPORT)
    assert nb.validate(plan) == []


def test_plan_titles_fit_youtube_limit():
    plan = nb.build(REPORT)
    for ch in plan["channels"]:
        for item in ch["next_shorts"] + ch["next_long"]:
            assert 0 < len(item["title"]) <= 100


def test_plan_generates_expected_counts():
    plan = nb.build(REPORT)
    for ch in plan["channels"]:
        assert len(ch["next_shorts"]) == 6
        assert len(ch["next_long"]) == 3


def test_thumbnail_text_is_short():
    plan = nb.build(REPORT)
    for ch in plan["channels"]:
        for item in ch["next_shorts"] + ch["next_long"]:
            assert len(item["thumbnail_text"]) <= 22


def test_plan_is_json_serialisable():
    json.dumps(nb.build(REPORT), ensure_ascii=False)


def test_validate_catches_an_over_long_title():
    plan = nb.build(REPORT)
    plan["channels"][0]["next_shorts"][0]["title"] = "ก" * 101
    assert nb.validate(plan)


def test_validate_catches_duplicate_titles():
    plan = nb.build(REPORT)
    plan["channels"][0]["next_shorts"][1]["title"] = plan["channels"][0]["next_shorts"][0]["title"]
    assert nb.validate(plan)


def test_channel_with_no_top_videos_still_plans():
    ch = {"channel_name": "ใหม่", "niche": "ปรัชญา", "top_videos": []}
    plan = nb.plan_channel(ch, published=set())
    assert len(plan["next_shorts"]) == 6
    assert nb.validate({"channels": [plan]}) == []
