#!/usr/bin/env python3
"""Diagnose why a batch of posts got no views.

The question this answers: when 60 posts receive almost no views, is the
content bad, or did the account get suppressed for how it posted?

The distinction matters because the fixes are opposites. Bad content needs new
ideas. Suppressed account needs the same content, posted slowly.

Three signals are computed from a post log (timestamp + views):

1. Burst posting. Platforms treat many posts per hour as automation. A
   recommendation threshold is applied and the peak rate is reported.
2. A view cliff. Views that collapse after a point in the log indicate the
   platform stopped distributing, not that viewers lost interest.
3. Duplicate captions. Repeated captions across posts read as re-uploaded
   content.

Zero dependencies.
"""
import argparse
import json
import re
import sys
from datetime import datetime

# Posts closer together than this are treated as one burst.
BURST_GAP_MIN = 10
# Posting faster than this is expected to be penalised by platforms.
MAX_POSTS_PER_HOUR = 3
# A drop this large in views marks a cliff.
CLIFF_DROP_RATIO = 0.9
# Below this many posts the sample is too small to judge.
MIN_POSTS_FOR_VERDICT = 5


def parse_time(value):
    """Accept '2026-11-01T03:09:00Z' or '2026-11-01 03:09' or HH:MM."""
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def to_records(rows):
    """Normalise input rows into (datetime, views, caption) tuples."""
    out = []
    for r in rows:
        t = parse_time(r.get("at") or r.get("time"))
        views = r.get("views")
        views = int(views) if isinstance(views, (int, float)) else None
        out.append({"at": t, "views": views, "caption": r.get("caption")})
    return out


def intervals_sec(records):
    """Seconds between consecutive posts, skipping unparsable timestamps."""
    ts = [r["at"] for r in records if r["at"]]
    return [(ts[i + 1] - ts[i]).total_seconds() for i in range(len(ts) - 1)]


def peak_posts_per_hour(records):
    """Highest number of posts within any one-hour window."""
    ts = sorted(r["at"] for r in records if r["at"])
    best = 0
    for i, start in enumerate(ts):
        count = sum(1 for t in ts[i:] if (t - start).total_seconds() <= 3600)
        best = max(best, count)
    return best


def find_bursts(records, gap_min=BURST_GAP_MIN):
    """Group posts into bursts, split wherever the gap exceeds gap_min."""
    ts = sorted((r["at"] for r in records if r["at"]))
    if not ts:
        return []
    groups = [[ts[0]]]
    for t in ts[1:]:
        if (t - groups[-1][-1]).total_seconds() > gap_min * 60:
            groups.append([t])
        else:
            groups[-1].append(t)
    return groups


def find_cliff(records):
    """Index where average views collapse and stay collapsed.

    Returns None when no collapse is found. The cliff is the earliest post
    whose own views, and the views of everything after it, fall below
    (1 - CLIFF_DROP_RATIO) of the average before it.
    """
    scored = [r for r in records if r["views"] is not None]
    if len(scored) < MIN_POSTS_FOR_VERDICT:
        return None
    for i in range(1, len(scored)):
        before = [r["views"] for r in scored[:i]]
        after = [r["views"] for r in scored[i:]]
        if not before or not after:
            continue
        avg_before = sum(before) / len(before)
        avg_after = sum(after) / len(after)
        if avg_before > 0 and avg_after <= avg_before * (1 - CLIFF_DROP_RATIO):
            return {"index": i, "avg_before": round(avg_before, 1),
                    "avg_after": round(avg_after, 1),
                    "at": scored[i]["at"].isoformat() if scored[i]["at"] else None}
    return None


def duplicate_caption_ratio(records):
    """Share of posts whose caption repeats an earlier post's caption."""
    caps = [r["caption"] for r in records if r.get("caption")]
    if not caps:
        return None
    seen, dupes = set(), 0
    for c in caps:
        if c in seen:
            dupes += 1
        seen.add(c)
    return round(dupes / len(caps), 3)


def diagnose(rows):
    """Full report for one platform's post log."""
    recs = to_records(rows)
    total = sum(r["views"] for r in recs if r["views"] is not None)
    with_views = [r for r in recs if r["views"] is not None]
    return {
        "posts": len(recs),
        "posts_with_views": len(with_views),
        "total_views": total,
        "views_per_post": round(total / len(with_views), 2) if with_views else None,
        "zero_view_posts": sum(1 for r in with_views if r["views"] == 0),
        "peak_posts_per_hour": peak_posts_per_hour(recs),
        "median_gap_sec": (sorted(intervals_sec(recs))[len(intervals_sec(recs)) // 2]
                           if len(recs) > 1 else None),
        "bursts": [len(b) for b in find_bursts(recs)],
        "cliff": find_cliff(recs),
        "duplicate_caption_ratio": duplicate_caption_ratio(recs),
    }


def verdict(d):
    """Classify the run: throttled, rapid_posting, healthy, or thin data."""
    if d["posts"] < MIN_POSTS_FOR_VERDICT:
        return "insufficient_data"
    if d["cliff"] and d["peak_posts_per_hour"] > MAX_POSTS_PER_HOUR:
        return "suppressed_likely"
    if d["peak_posts_per_hour"] > MAX_POSTS_PER_HOUR:
        return "rapid_posting"
    if d["zero_view_posts"] > d["posts"] * 0.5:
        return "suppressed_likely"
    return "healthy"


def advice(d):
    """Concrete next actions, in Thai, for the detected pattern."""
    v = verdict(d)
    if v == "insufficient_data":
        return ["ข้อมูลน้อยเกินไป ยังสรุปไม่ได้ — เก็บให้ครบก่อน"]
    if v == "healthy":
        return ["รูปแบบการโพสต์ปกติ — ปัญหาอยู่ที่เนื้อหา ไม่ใช่บัญชี"]
    out = []
    if d["peak_posts_per_hour"] > MAX_POSTS_PER_HOUR:
        out.append(f"โพสต์ถี่เกิน: สูงสุด {d['peak_posts_per_hour']} โพสต์/ชั่วโมง "
                   f"(ควรไม่เกิน {MAX_POSTS_PER_HOUR}) → ลดเหลือ 1-3/วัน เว้นหลายชั่วโมง")
    if d["cliff"]:
        out.append(f"พบจุดวิวตกที่โพสต์ที่ {d['cliff']['index'] + 1}: "
                   f"ก่อนหน้าเฉลี่ย {d['cliff']['avg_before']} → หลังจากนั้น "
                   f"{d['cliff']['avg_after']} วิว = แพลตฟอร์มหยุดกระจาย")
    if d["duplicate_caption_ratio"] and d["duplicate_caption_ratio"] > 0.3:
        out.append(f"แคปชันซ้ำ {d['duplicate_caption_ratio']*100:.0f}% "
                   f"→ เขียนแคปชันใหม่ทุกโพสต์")
    out.append("ทดสอบใหม่แบบยุติธรรม: 1 โพสต์/วัน × 30 วัน เนื้อหาไม่ซ้ำ แล้ววัดอีกครั้ง")
    return out


def render(rows, label="posts"):
    d = diagnose(rows)
    v = verdict(d)
    mark = {"suppressed_likely": "🚫 ถูกกดการมองเห็น (น่าจะ)",
            "rapid_posting": "⚠️ โพสต์ถี่เกิน",
            "healthy": "✅ ปกติ",
            "insufficient_data": "❔ ข้อมูลน้อย"}[v]
    lines = [f"=== {label} ===",
             f"{mark}",
             f"โพสต์ {d['posts']} | วิวรวม {d['total_views']:,} | "
             f"วิว/โพสต์ {d['views_per_post']} | โพสต์ 0 วิว {d['zero_view_posts']}",
             f"โพสต์ถี่สุด {d['peak_posts_per_hour']}/ชม | "
             f"ห่างกันกลาง ๆ {d['median_gap_sec']:.0f} วินาที" if d['median_gap_sec'] else "",
             f"กลุ่มโพสต์รัว: {d['bursts']}"]
    if d["cliff"]:
        lines.append(f"จุดวิวตก: โพสต์ที่ {d['cliff']['index'] + 1} "
                     f"({d['cliff']['avg_before']} → {d['cliff']['avg_after']} วิว)")
    lines.append("")
    lines += ["สิ่งที่ควรทำ:"] + [f"  • {a}" for a in advice(d)]
    return "\n".join(x for x in lines if x != "")


def main(argv=None):
    p = argparse.ArgumentParser(description="วินิจฉัยว่าทำไมโพสต์ไม่ได้วิว")
    p.add_argument("path", help="ไฟล์ JSON: [{at, views, caption}]")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    rows = json.load(open(a.path, encoding="utf-8"))
    if a.json:
        print(json.dumps({"diagnosis": diagnose(rows),
                          "verdict": verdict(diagnose(rows)),
                          "advice": advice(diagnose(rows))},
                         ensure_ascii=False, indent=2))
    else:
        print(render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
