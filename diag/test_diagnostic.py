"""Tests for the posting pattern diagnostic."""
import json

import pytest

import posting_diagnostic as pd


def recs(*pairs):
    return [{"at": t, "views": v, "caption": c} for t, v, c in pairs]


HEALTHY = recs(
    ("2026-11-01T03:00:00Z", 40, "a"),
    ("2026-11-02T03:00:00Z", 55, "b"),
    ("2026-11-03T03:00:00Z", 38, "c"),
    ("2026-11-04T03:00:00Z", 61, "d"),
    ("2026-11-05T03:00:00Z", 47, "e"),
    ("2026-11-06T03:00:00Z", 52, "f"),
)

BURST_CLIFF = recs(
    ("2026-11-01T03:09:00Z", 84, "same"),
    ("2026-11-01T03:21:00Z", 31, "same"),
    ("2026-11-01T03:22:00Z", 29, "same"),
    ("2026-11-01T03:22:30Z", 63, "same"),
    ("2026-11-01T03:23:00Z", 89, "same"),
    ("2026-11-01T03:23:30Z", 90, "same"),
    ("2026-11-01T03:24:00Z", 0, "same"),
    ("2026-11-01T03:26:00Z", 0, "same"),
    ("2026-11-01T03:28:00Z", 0, "same"),
)


def test_parse_time_iso_with_z():
    assert pd.parse_time("2026-11-01T03:09:00Z") is not None


def test_parse_time_bare_hhmm():
    assert pd.parse_time("03:09") is not None


def test_parse_time_bad_input_returns_none():
    assert pd.parse_time("not a time") is None


def test_parse_time_empty_returns_none():
    assert pd.parse_time("") is None


def test_peak_posts_per_hour_detects_burst():
    assert pd.peak_posts_per_hour(pd.to_records(BURST_CLIFF)) >= 7


def test_peak_posts_per_hour_low_for_spread_posts():
    assert pd.peak_posts_per_hour(pd.to_records(HEALTHY)) == 1


def test_find_cliff_detects_collapse():
    c = pd.find_cliff(pd.to_records(BURST_CLIFF))
    assert c is not None
    assert c["avg_after"] == 0.0


def test_find_cliff_none_when_stable():
    assert pd.find_cliff(pd.to_records(HEALTHY)) is None


def test_find_cliff_needs_minimum_sample():
    assert pd.find_cliff(pd.to_records(HEALTHY[:3])) is None


def test_duplicate_caption_ratio_all_same():
    assert pd.duplicate_caption_ratio(pd.to_records(BURST_CLIFF)) > 0.8


def test_duplicate_caption_ratio_none_when_unique():
    assert pd.duplicate_caption_ratio(pd.to_records(HEALTHY)) == 0.0


def test_duplicate_caption_ratio_none_without_captions():
    assert pd.duplicate_caption_ratio([{"at": None, "views": 1}]) is None


def test_diagnose_totals():
    d = pd.diagnose(BURST_CLIFF)
    assert d["posts"] == 9
    assert d["total_views"] == 386
    assert d["zero_view_posts"] == 3


def test_verdict_suppressed_on_burst_plus_cliff():
    assert pd.verdict(pd.diagnose(BURST_CLIFF)) == "suppressed_likely"


def test_verdict_healthy_for_spread_posts():
    assert pd.verdict(pd.diagnose(HEALTHY)) == "healthy"


def test_verdict_insufficient_for_tiny_sample():
    assert pd.verdict(pd.diagnose(HEALTHY[:2])) == "insufficient_data"


def test_advice_mentions_posting_rate_for_burst():
    text = " ".join(pd.advice(pd.diagnose(BURST_CLIFF)))
    assert "โพสต์ถี่เกิน" in text


def test_advice_mentions_cliff():
    text = " ".join(pd.advice(pd.diagnose(BURST_CLIFF)))
    assert "จุดวิวตก" in text


def test_advice_mentions_duplicate_captions():
    text = " ".join(pd.advice(pd.diagnose(BURST_CLIFF)))
    assert "แคปชันซ้ำ" in text


def test_advice_says_content_for_healthy():
    text = " ".join(pd.advice(pd.diagnose(HEALTHY)))
    assert "เนื้อหา" in text


def test_render_contains_verdict_mark():
    assert "ถูกกดการมองเห็น" in pd.render(BURST_CLIFF)


def test_real_tiktok_log_matches_ar_findings():
    rows = json.load(open("tiktok_2026-11-01.json", encoding="utf-8"))
    d = pd.diagnose(rows)
    assert d["peak_posts_per_hour"] > 3
    assert d["cliff"] is not None
    assert pd.verdict(d) == "suppressed_likely"
