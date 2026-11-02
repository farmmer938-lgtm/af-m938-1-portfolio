#!/usr/bin/env python3
"""Consolidated view of every channel K owns, and what each one actually earns.

Two questions this answers with arithmetic only:

1. Where does attention actually come from?
   Content produced is compared against views received, per platform. A
   platform that consumes posts but returns no views is dead weight, however
   much effort goes into it.

2. How far is the whole portfolio from monetization?
   Every threshold is computed for the combined totals, not per channel, since
   YPP is assessed per channel but the growth effort is shared.

Zero dependencies.
"""
import argparse
import json
import sys

SUBS_REQUIRED = 1000
SHORTS_VIEWS_REQUIRED = 10_000_000
SHORTS_WINDOW_DAYS = 90


def views_per_post(posts, views):
    """Attention returned per unit of effort. None when no posts."""
    if not posts:
        return None
    return round(views / posts, 2)


def is_dead_weight(posts, views, floor=1.0):
    """A channel that consumes effort but returns almost nothing."""
    vpp = views_per_post(posts, views)
    if vpp is None:
        return False
    return vpp < floor


def platform_report(name, posts, views, note=""):
    vpp = views_per_post(posts, views)
    return {
        "platform": name,
        "posts": posts,
        "views": views,
        "views_per_post": vpp,
        "verdict": "dead" if is_dead_weight(posts, views) else "alive",
        "note": note,
    }


def totals(channels):
    subs = sum(c.get("subscribers") or 0 for c in channels)
    videos = sum(c.get("videos") or 0 for c in channels)
    views = sum(c.get("total_views") or 0 for c in channels)
    return {"channels": len(channels), "subscribers": subs,
            "videos": videos, "total_views": views}


def ypp_gap(t):
    """Distance to monetization for the whole portfolio."""
    return {
        "subs_gap": max(0, SUBS_REQUIRED - t["subscribers"]),
        "shorts_views_gap": max(0, SHORTS_VIEWS_REQUIRED - t["total_views"]),
        "views_needed_multiple": (round(SHORTS_VIEWS_REQUIRED / t["total_views"], 1)
                                  if t["total_views"] else None),
        "reachable_today": t["subscribers"] >= SUBS_REQUIRED,
    }


def analyse(data):
    chans = data.get("channels") or []
    plats = data.get("platforms") or []
    t = totals(chans)
    return {
        "totals": t,
        "ypp_gap": ypp_gap(t),
        "platforms": [platform_report(p["name"], p["posts"], p["views"], p.get("note", ""))
                      for p in plats],
        "best_channel": (max(chans, key=lambda c: c.get("total_views") or 0).get("name")
                         if chans else None),
        "worst_channel": (min(chans, key=lambda c: c.get("total_views") or 0).get("name")
                          if chans else None),
    }


def dead_platforms(analysis):
    return [p["platform"] for p in analysis["platforms"] if p["verdict"] == "dead"]


def render(a):
    t = a["totals"]
    g = a["ypp_gap"]
    out = ["=" * 62,
           f"รวม {t['channels']} ช่อง | sub {t['subscribers']} | คลิป {t['videos']} | ดูรวม {t['total_views']:,}",
           "=" * 62, "",
           "แพลตฟอร์มที่ผลิต vs ความสนใจที่ได้กลับมา:"]
    for p in a["platforms"]:
        mark = "❌ ตาย" if p["verdict"] == "dead" else "✅ มีคนดู"
        out.append(f"  {mark}  {p['platform']:<16} โพสต์ {p['posts']:>4} -> วิว {p['views']:>6} "
                   f"= {p['views_per_post']} วิว/โพสต์")
    out += ["", f"ต้องเพิ่ม sub อีก {g['subs_gap']} คน",
            f"ต้องเพิ่มยอดดูอีก {g['shorts_views_gap']:,} ครั้ง "
            f"(x{g['views_needed_multiple']} ของที่มีอยู่)"]
    dead = dead_platforms(a)
    if dead:
        out += ["", f"⚠️  แพลตฟอร์มที่ควรหยุดลงแรง: {', '.join(dead)}"]
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description="ภาพรวมทุกช่องของ K")
    p.add_argument("path", help="ไฟล์ JSON ข้อมูลรวม")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    data = json.load(open(a.path, encoding="utf-8"))
    res = analyse(data)
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
