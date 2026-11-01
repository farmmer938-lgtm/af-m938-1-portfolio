"""Tests for the YouTube content engine — output must be publish-ready."""
import json
import pytest
import yt_engine as y


def test_title_variants_are_unique_and_within_limit():
    titles = y.title_variants("ขายของออนไลน์")
    assert len(titles) == 5
    assert len(set(titles)) == 5
    assert all(0 < len(t) <= 100 for t in titles)


def test_title_includes_topic_and_year():
    t = y.title_variants("ลงทุนหุ้น", year=2027)
    assert any("ลงทุนหุ้น" in x for x in t)
    assert any("2027" in x for x in t)


def test_description_has_chapters_and_cta():
    d = y.description("ทำ SEO", channel="AF Money")
    assert "Chapters" in d
    assert "00:00" not in d.split("Chapters")[1].split("\n")[1]  # first chapter is 01:00
    assert "01:00" in d
    assert "AF Money" in d
    assert y.CTA in d


def test_description_within_youtube_limit():
    d = y.description("หัวข้อ", keywords=[f"kw{i}" for i in range(50)])
    assert len(d) <= 5000


def test_tags_are_deduped_and_capped():
    t = y.tags("shopee", keywords=["shopee", "SHOPEE", "ขายของ"])
    assert len(t) <= 15
    lowered = [x.lower() for x in t]
    assert len(lowered) == len(set(lowered))


def test_tags_within_youtube_char_limit():
    t = y.tags("หัวข้อทดสอบ", niche="ช่อง", keywords=["ก" * 60 for _ in range(10)])
    assert sum(len(x) for x in t) + len(t) <= 500


def test_thumbnail_text_is_short():
    tt = y.thumbnail_text("วิธีขายไฟล์ดิจิทัลบน Shopee ให้ได้เงินจริง")
    assert len(tt) <= 40
    assert len(tt.split()) <= 4


def test_slug_is_url_safe_for_thai():
    s = y.slug("ขายไฟล์ดิจิทัลบน Shopee!")
    assert " " not in s and "!" not in s
    assert s == s.lower()


def test_package_validates_clean():
    pkg = y.package("ขายไฟล์ดิจิทัลบน Shopee", niche="ขายออนไลน์",
                    keywords=["shopee", "digital"], channel="AF Money")
    assert y.validate(pkg) == []
    json.dumps(pkg, ensure_ascii=False)  # must be serialisable


def test_batch_generates_one_package_per_topic():
    out = y.batch("ขายออนไลน์", ["A", "B", "C"], channel="AF")
    assert len(out) == 3
    assert all(y.validate(p) == [] for p in out)
    assert len({p["slug"] for p in out}) == 3
