"""Tests for the consolidated portfolio analysis."""
import json
import pytest

import portfolio as pf

DATA = {
    "channels": [
        {"name": "A", "subscribers": 10, "videos": 5, "total_views": 1000},
        {"name": "B", "subscribers": 5, "videos": 3, "total_views": 500},
    ],
    "platforms": [
        {"name": "YT", "posts": 10, "views": 1000},
        {"name": "FB", "posts": 60, "views": 11},
        {"name": "TT", "posts": 60, "views": 0},
    ],
}


def test_views_per_post_basic():
    assert pf.views_per_post(10, 1000) == 100.0


def test_views_per_post_none_when_no_posts():
    assert pf.views_per_post(0, 100) is None


def test_dead_weight_flags_facebook_like_numbers():
    assert pf.is_dead_weight(60, 11) is True


def test_dead_weight_false_when_attention_returns():
    assert pf.is_dead_weight(10, 1000) is False


def test_totals_sum_all_channels():
    t = pf.totals(DATA["channels"])
    assert t["channels"] == 2
    assert t["subscribers"] == 15
    assert t["videos"] == 8
    assert t["total_views"] == 1500


def test_totals_handles_missing_fields():
    t = pf.totals([{"name": "x"}])
    assert t["subscribers"] == 0
    assert t["total_views"] == 0


def test_ypp_gap_counts_remaining_subscribers():
    g = pf.ypp_gap({"subscribers": 30, "total_views": 11248})
    assert g["subs_gap"] == 970
    assert g["reachable_today"] is False


def test_ypp_gap_multiple_is_accurate():
    g = pf.ypp_gap({"subscribers": 0, "total_views": 1000})
    assert g["views_needed_multiple"] == 10000.0


def test_ypp_gap_reachable_at_threshold():
    g = pf.ypp_gap({"subscribers": 1000, "total_views": 10_000_000})
    assert g["reachable_today"] is True
    assert g["subs_gap"] == 0
    assert g["shorts_views_gap"] == 0


def test_analyse_marks_platforms_correctly():
    a = pf.analyse(DATA)
    verdicts = {p["platform"]: p["verdict"] for p in a["platforms"]}
    assert verdicts["YT"] == "alive"
    assert verdicts["FB"] == "dead"
    assert verdicts["TT"] == "dead"


def test_analyse_finds_best_and_worst_channel():
    a = pf.analyse(DATA)
    assert a["best_channel"] == "A"
    assert a["worst_channel"] == "B"


def test_dead_platforms_lists_only_dead():
    a = pf.analyse(DATA)
    assert pf.dead_platforms(a) == ["FB", "TT"]


def test_render_contains_totals_and_warning():
    text = pf.render(pf.analyse(DATA))
    assert "รวม 2 ช่อง" in text
    assert "ควรหยุดลงแรง" in text


def test_render_omits_warning_when_all_alive():
    d = {"channels": DATA["channels"], "platforms": [{"name": "YT", "posts": 1, "views": 999}]}
    text = pf.render(pf.analyse(d))
    assert "ควรหยุดลงแรง" not in text


def test_analyse_is_json_serialisable():
    json.dumps(pf.analyse(DATA), ensure_ascii=False)


def test_empty_portfolio_does_not_crash():
    a = pf.analyse({"channels": [], "platforms": []})
    assert a["totals"]["channels"] == 0
    assert a["best_channel"] is None


def test_real_portfolio_numbers_match_measured_data():
    real = json.load(open("portfolio.json", encoding="utf-8"))
    a = pf.analyse(real)
    assert a["totals"]["subscribers"] == 30
    assert a["totals"]["total_views"] == 11248
    assert a["totals"]["channels"] == 4
    assert "AERIS TikTok" in pf.dead_platforms(a)
