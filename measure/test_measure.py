"""Tests for the public account measurement tool (no network required)."""
import pytest

import channel_measure as cm

YT_ABOUT = '''
<meta property="og:title" content="Farmmer — ธรรมะก่อนนอน" />
"country":"ไทย","subscriberCountText":"ผู้ติดตาม 11 คน",
"videoCountText":"วิดีโอ 11 รายการ","viewCountText":"การดู 2,674 ครั้ง",
"externalId":"UCM3QO5L_pmj34n1JVlbhh-w"
'''

YT_ABOUT_EN = '''
<meta property="og:title" content="My Channel" />
"subscriberCountText":"1.2K subscribers","videoCountText":"340 videos",
"viewCountText":"1,234,567 views","externalId":"UCabc123"
'''

YT_VIDEOS = '''
"lockupViewModel":{"contentImage":{"thumb":"x"},"contentId":"GLPKPl_MMR4",
"lockupMetadataViewModel":{"title":{"content":"สะพานใบไม้ที่หายไป (ฉบับเต็ม)"},
"metadata":{"contentMetadataViewModel":{"metadataRows":[{"metadataParts":[{"text":{"content":"2"},
"accessibilityLabel":"การดู 2 ครั้ง"}]}]}}}}
"lockupViewModel":{"contentImage":{"thumb":"y"},"contentId":"_qOSft3tzJ8",
"lockupMetadataViewModel":{"title":{"content":"ปล่อยวาง แล้วใจจะเบา"},
"metadata":{"contentMetadataViewModel":{"metadataRows":[{"metadataParts":[{"text":{"content":"1"},
"accessibilityLabel":"การดู 1 ครั้ง"}]}]}}}}
'''

TT = ('<meta property="og:title" content="Kitchen" />'
      '"followerCount":8900,"videoCount":120,"heartCount":45000')

FB = ('<meta property="og:title" content="Facebook" />'
      '<meta property="og:description" content="Facebook. 154,890,687 followers '
      '&#xb7; 598,616 talking about this." />')

SP = ('<meta property="og:title" content="ร้านของใช้" />'
      '"follower_count":1234,"rating_star":4.8,"item_count":56')


def test_compact_number_parses_thai_subs():
    assert cm.parse_compact_number("ผู้ติดตาม 11 คน") == 11


def test_compact_number_parses_english_subs():
    assert cm.parse_compact_number("1.2K subscribers") == 1200


def test_compact_number_parses_commas():
    assert cm.parse_compact_number("การดู 2,674 ครั้ง") == 2674


def test_compact_number_parses_millions():
    assert cm.parse_compact_number("1,234,567 views") == 1234567


def test_compact_number_unknown_on_none():
    assert cm.parse_compact_number(None) == cm.UNKNOWN


def test_compact_number_unknown_on_text_without_digits():
    assert cm.parse_compact_number("ไม่รู้") == cm.UNKNOWN


def test_parse_youtube_thai_page():
    r = cm.parse_youtube(YT_ABOUT, "farmmer-n9t")
    assert r["name"] == "Farmmer — ธรรมะก่อนนอน"
    assert r["subscribers"] == 11
    assert r["videos_public"] == 11
    assert r["total_views"] == 2674
    assert r["channel_id"] == "UCM3QO5L_pmj34n1JVlbhh-w"
    assert r["country"] == "ไทย"


def test_parse_youtube_english_page():
    r = cm.parse_youtube(YT_ABOUT_EN, "mychannel")
    assert r["subscribers"] == 1200
    assert r["videos_public"] == 340
    assert r["total_views"] == 1234567


def test_parse_youtube_missing_fields_are_unknown():
    r = cm.parse_youtube("<html>nothing here</html>", "x")
    assert r["subscribers"] == cm.UNKNOWN
    assert r["videos_public"] == cm.UNKNOWN
    assert r["name"] == cm.UNKNOWN


def test_parse_youtube_videos_returns_title_and_views():
    vids = cm.parse_youtube_videos(YT_VIDEOS)
    assert len(vids) == 2
    assert vids[0]["title"] == "สะพานใบไม้ที่หายไป (ฉบับเต็ม)"
    assert vids[0]["views"] == 2
    assert vids[0]["url"] == "https://youtu.be/GLPKPl_MMR4"


def test_parse_youtube_videos_respects_limit():
    assert len(cm.parse_youtube_videos(YT_VIDEOS, limit=1)) == 1


def test_parse_youtube_videos_handles_empty_page():
    assert cm.parse_youtube_videos("<html></html>") == []


def test_parse_tiktok():
    r = cm.parse_tiktok(TT, "kitchen.real")
    assert r["followers"] == 8900
    assert r["videos"] == 120
    assert r["likes"] == 45000


def test_parse_facebook_followers():
    r = cm.parse_facebook(FB, "facebook")
    assert r["followers"] == 154890687
    assert r["talking_about"] == 598616


def test_parse_shopee():
    r = cm.parse_shopee(SP, "myshop")
    assert r["followers"] == 1234
    assert r["rating"] == 4.8
    assert r["item_count"] == 56


def test_measure_unsupported_platform():
    r = cm.measure("myspace", "x")
    assert "error" in r


def test_summary_renders_youtube_line():
    rows = [cm.parse_youtube(YT_ABOUT, "farmmer-n9t")]
    text = cm.summary(rows)
    assert "Farmmer" in text
    assert "sub 11" in text


def test_summary_renders_error():
    text = cm.summary([{"platform": "youtube", "handle": "x", "error": "fetch failed"}])
    assert "fetch failed" in text


def test_main_rejects_bad_target_format(capsys):
    assert cm.main(["nocolon"]) == 2


def test_main_requires_a_target():
    assert cm.main([]) == 2
