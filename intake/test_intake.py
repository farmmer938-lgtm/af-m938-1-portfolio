"""Tests for the AI-team intake validator."""
import json
import pytest
import intake


def good_channel(**over):
    ch = {
        "channel_name": "ช่องทำเงิน",
        "channel_url": "https://youtube.com/@example",
        "niche": "การเงินส่วนบุคคล",
        "language": "th",
        "subscribers": 1200,
        "total_videos": 45,
        "uploads_per_week": 2,
        "avg_views_last_10": 340,
        "top_videos": [{"title": "หาเงินออนไลน์", "views": 12000, "url": "u"}],
        "format": "long",
        "monetized": False,
        "monthly_revenue_thb": 0,
        "biggest_problem": "คนดูไม่กดติดตาม",
        "needs_help_with": "เขียนสคริปต์",
    }
    ch.update(over)
    return ch


def good_report(**over):
    r = {
        "account_label": "AI1",
        "channels": [good_channel()],
        "other_platforms": {"facebook": "เพจขายของ"},
        "shopee": {"shop_url": "https://shopee.co.th/x", "category": "ของใช้"},
        "assets": ["คลิปเก่า 20 ไฟล์"],
    }
    r.update(over)
    return r


def test_good_report_is_valid_and_clean():
    rep = intake.validate_report(good_report())
    assert rep["ok"] is True
    assert rep["errors"] == []
    assert rep["warnings"] == []
    assert rep["channel_count"] == 1


def test_missing_top_level_field_is_an_error():
    r = good_report()
    del r["account_label"]
    rep = intake.validate_report(r)
    assert rep["ok"] is False
    assert any("account_label" in e for e in rep["errors"])


def test_empty_channels_is_an_error():
    rep = intake.validate_report(good_report(channels=[]))
    assert rep["ok"] is False


def test_missing_channel_required_field_is_an_error():
    ch = good_channel()
    del ch["niche"]
    rep = intake.validate_report(good_report(channels=[ch]))
    assert rep["ok"] is False
    assert any("niche" in e for e in rep["errors"])


def test_channel_name_cannot_be_unknown():
    rep = intake.validate_report(good_report(channels=[good_channel(channel_name="UNKNOWN")]))
    assert rep["ok"] is False


def test_unknown_numbers_are_warnings_not_errors():
    ch = good_channel(subscribers="UNKNOWN", avg_views_last_10="UNKNOWN")
    rep = intake.validate_report(good_report(channels=[ch]))
    assert rep["ok"] is True
    assert any("subscribers" in w for w in rep["warnings"])


def test_negative_subscriber_count_is_rejected():
    rep = intake.validate_report(good_report(channels=[good_channel(subscribers=-5)]))
    assert rep["ok"] is False


def test_float_subscribers_is_rejected():
    rep = intake.validate_report(good_report(channels=[good_channel(subscribers=12.5)]))
    assert rep["ok"] is False


def test_bad_format_value_is_rejected():
    rep = intake.validate_report(good_report(channels=[good_channel(format="podcast")]))
    assert rep["ok"] is False


def test_top_videos_must_be_a_non_empty_list():
    rep = intake.validate_report(good_report(channels=[good_channel(top_videos=[])]))
    assert rep["ok"] is False


def test_top_video_without_views_is_a_warning():
    ch = good_channel(top_videos=[{"title": "คลิป"}])
    rep = intake.validate_report(good_report(channels=[ch]))
    assert rep["ok"] is True
    assert any("no view count" in w for w in rep["warnings"])


def test_missing_help_field_is_flagged():
    ch = good_channel()
    del ch["needs_help_with"]
    rep = intake.validate_report(good_report(channels=[ch]))
    assert any("needs_help_with" in w for w in rep["warnings"])


def test_unknown_count_is_reported():
    ch = good_channel(subscribers="UNKNOWN", total_videos="UNKNOWN")
    rep = intake.validate_report(good_report(channels=[ch]))
    assert rep["unknown_count"] >= 2


def test_non_object_report_is_rejected():
    rep = intake.validate_report([1, 2, 3])
    assert rep["ok"] is False


def test_multiple_channels_are_all_checked():
    rep = intake.validate_report(good_report(
        channels=[good_channel(channel_name="A"), good_channel(channel_name="B", niche="เกม")]))
    assert rep["ok"] is True
    assert rep["channel_count"] == 2


def test_summarise_renders_thai_status_lines():
    rep = intake.validate_report(good_report(channels=[good_channel(subscribers="UNKNOWN")]))
    text = intake.summarise(rep)
    assert "ช่อง: 1" in text
    assert "ควรเติม" in text


def test_cli_returns_zero_on_valid_file(tmp_path, capsys):
    f = tmp_path / "r.json"
    f.write_text(json.dumps(good_report(), ensure_ascii=False), encoding="utf-8")
    assert intake.main([str(f)]) == 0


def test_cli_returns_one_on_invalid_file(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"channels": []}), encoding="utf-8")
    assert intake.main([str(f)]) == 1


def test_cli_returns_two_on_broken_json(tmp_path):
    f = tmp_path / "broken.json"
    f.write_text("{not json", encoding="utf-8")
    assert intake.main([str(f)]) == 2
