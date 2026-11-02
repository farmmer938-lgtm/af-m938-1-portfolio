#!/usr/bin/env python3
"""Turn AI2's short numbered answers into a validated report.

Asking an agent for a large JSON object was itself part of the output-limit
problem. Instead AI2 answers short numbered lines, and this parser does the
formatting. Unparseable or missing values become "UNKNOWN" rather than guesses.

Zero dependencies.
"""
import argparse
import json
import re
import sys

import intake

TIER1_MAP = {
    1: "youtube_channel_name",
    2: "youtube_subscribers",
    3: "youtube_total_videos",
    4: "youtube_top_video",
    5: "facebook_name",
    6: "facebook_followers",
    7: "tiktok_handle",
    8: "tiktok_followers",
    9: "shopee_role",
    10: "shopee_category",
    11: "shopee_url",
    12: "goal_thb_per_month",
}

PLATFORM_FIELDS = {
    "youtube": ["channel_name", "channel_url", "niche", "subscribers", "total_videos",
                "uploads_per_week", "avg_views_last_10", "top_videos", "format",
                "monetized", "monthly_revenue_thb", "biggest_problem", "needs_help_with"],
    "facebook": ["name", "url", "followers", "posts_per_week", "avg_reach_per_post",
                 "what_sells_best", "monetizes"],
    "tiktok": ["handle", "followers", "total_videos", "avg_views", "best_video", "monetized"],
    "shopee": ["role", "url", "category", "commission_pct", "clicks_last_30d",
               "orders_last_30d", "revenue_thb_last_30d", "best_categories",
               "link_placement", "blockers"],
}

UNKNOWN_WORDS = {"", "-", "ไม่รู้", "ไม่มี", "none", "n/a", "na", "unknown"}


def parse_number(text):
    """Pull the first integer/float out of a line, or return UNKNOWN."""
    if text is None:
        return intake.UNKNOWN
    cleaned = str(text).replace(",", "").replace("บาท", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not m:
        return intake.UNKNOWN
    val = float(m.group())
    return int(val) if val.is_integer() else val


def strip_label(value):
    """Drop an echoed question label, keeping URLs intact.

    'ชื่อช่อง: เรื่องจริงในครัว'      -> 'เรื่องจริงในครัว'
    'เป็น affiliate หรือ seller: ทั้งสอง' -> 'ทั้งสอง'
    'https://shopee.co.th/x'         -> unchanged (right side starts with '//')
    'ชื่อช่อง:'                      -> '' (answered blank)
    """
    v = value.strip()
    if not v:
        return v
    sep = "：" if "：" in v else (":" if ":" in v else None)
    if sep is None:
        return v
    left, _, right = v.rpartition(sep)
    right = right.strip()
    if not right:
        return ""
    if right.startswith("//"):
        return v
    if "http" in left.lower():
        return v
    return right


def parse_lines(text):
    """Split numbered answers into {number: value}."""
    out = {}
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(\d{1,2})\s*[\.\)]\s*(.*)$", line)
        if m:
            num, val = int(m.group(1)), m.group(2)
            out[num] = strip_label(val)
    return out


def _val(d, key, default=intake.UNKNOWN):
    v = d.get(key)
    if v is None:
        return default
    if str(v).strip().lower() in UNKNOWN_WORDS:
        return intake.UNKNOWN
    return str(v).strip()


def tier1_to_report(text):
    """Build a minimal report from the 12-line tier-1 answer."""
    lines = parse_lines(text)
    g = {name: _val(lines, num) for num, name in TIER1_MAP.items()}
    ch = {
        "channel_name": g["youtube_channel_name"],
        "niche": intake.UNKNOWN,
        "subscribers": parse_number(g["youtube_subscribers"]),
        "total_videos": parse_number(g["youtube_total_videos"]),
        "avg_views_last_10": intake.UNKNOWN,
        "top_videos": [{"title": g["youtube_top_video"], "views": intake.UNKNOWN}],
        "format": intake.UNKNOWN,
        "monetized": intake.UNKNOWN,
        "monthly_revenue_thb": intake.UNKNOWN,
        "biggest_problem": intake.UNKNOWN,
        "needs_help_with": intake.UNKNOWN,
    }
    return {
        "account_label": "AI2",
        "channels": [ch],
        "other_platforms": {
            "facebook": {"name": g["facebook_name"], "followers": parse_number(g["facebook_followers"])},
            "tiktok": {"handle": g["tiktok_handle"], "followers": parse_number(g["tiktok_followers"])},
        },
        "shopee": {"role": g["shopee_role"], "category": g["shopee_category"], "shop_url": g["shopee_url"]},
        "goal_thb_per_month": parse_number(g["goal_thb_per_month"]),
    }


def platform_to_report(text, platform):
    """Build a partial report from one platform round."""
    lines = parse_lines(text)
    fields = PLATFORM_FIELDS[platform]
    got = {}
    for i, f in enumerate(fields, start=1):
        got[f] = _val(lines, i)
    if platform == "youtube":
        ch = {
            "channel_name": got["channel_name"],
            "channel_url": got["channel_url"],
            "niche": got["niche"],
            "subscribers": parse_number(got["subscribers"]),
            "total_videos": parse_number(got["total_videos"]),
            "uploads_per_week": parse_number(got["uploads_per_week"]),
            "avg_views_last_10": parse_number(got["avg_views_last_10"]),
            "top_videos": [{"title": got["top_videos"], "views": intake.UNKNOWN}],
            "format": got["format"],
            "monetized": got["monetized"],
            "monthly_revenue_thb": parse_number(got["monthly_revenue_thb"]),
            "biggest_problem": got["biggest_problem"],
            "needs_help_with": got["needs_help_with"],
        }
        return {"account_label": "AI2", "channels": [ch]}
    return {"account_label": "AI2", "platform": platform, "answers": got}


def merge_reports(reports):
    """Combine tier-1 + per-platform reports into one object."""
    merged = {"account_label": "AI2", "channels": [], "other_platforms": {}, "shopee": {}}
    for r in reports:
        if r.get("channels"):
            merged["channels"].extend(r["channels"])
        if "other_platforms" in r:
            merged["other_platforms"].update(r["other_platforms"])
        if "shopee" in r:
            merged["shopee"].update(r["shopee"])
        if r.get("platform"):
            merged["other_platforms"][r["platform"]] = r["answers"]
        if "goal_thb_per_month" in r:
            merged["goal_thb_per_month"] = r["goal_thb_per_month"]
    return merged


def main(argv=None):
    p = argparse.ArgumentParser(description="แปลงคำตอบสั้นของ AI2 เป็นรายงาน JSON")
    p.add_argument("path", help="ไฟล์ข้อความคำตอบ")
    p.add_argument("--mode", choices=["tier1", "youtube", "facebook", "tiktok", "shopee"],
                   default="tier1")
    p.add_argument("--validate", action="store_true")
    a = p.parse_args(argv)
    text = open(a.path, encoding="utf-8").read()
    report = tier1_to_report(text) if a.mode == "tier1" else platform_to_report(text, a.mode)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if a.validate and report.get("channels"):
        rep = intake.validate_report(report)
        print("\n--- ตรวจสอบ ---\n" + intake.summarise(rep), file=sys.stderr)
        return 0 if rep["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
