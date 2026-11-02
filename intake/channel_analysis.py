#!/usr/bin/env python3
"""Channel economics + winning-formula analysis for the AF YouTube team.

Answers two questions with real arithmetic, never estimates:

1. How far are these channels from YouTube Partner Program (YPP)?
   Two independent thresholds exist:
     - long-form : 1,000 subs AND 4,000 public watch hours in 12 months
     - Shorts    : 1,000 subs AND 10,000,000 Shorts views in 90 days
   Either qualifies. We compute the gap for both.

2. Which hook style actually earns views?
   Classifies every known top video by hook type and averages the view counts,
   so the next titles copy what already worked instead of guessing.

Zero dependencies.
"""
import argparse
import json
import re
import sys

SUBS_REQUIRED = 1000
WATCH_HOURS_REQUIRED = 4000
SHORTS_VIEWS_REQUIRED = 10_000_000
SHORTS_WINDOW_DAYS = 90

# Hook classification: ordered, first match wins.
_QUESTION = re.compile(r"[?？]|^(ทำไม|ยังไง|อย่างไร|อะไร|ใคร|เมื่อไหร่|ที่ไหน|วิธี|how|why|what)")
_TIME_BOUND = re.compile(r"\d+\s*(วินาที|นาที|ชั่วโมง|วัน|คืน|สัปดาห์|เดือน)")
_RELATIONAL = re.compile(r"แม่|พ่อ|ลูก|ครอบครัว|ยาย|ตา|ปู่|ย่า|พี่|น้อง|เมีย|ผัว|เพื่อน")
_ACTION = re.compile(r"ลอง|ทำ|เริ่ม|ฝึก|เปลี่ยน|หยุด|เปิด|ปิด|ใช้")
_ABSTRACT = re.compile(r"เมล็ด|แม่น้ำ|ต้นไม้|ก้าว|ความหมาย|เวลา|ความสุข|ความสำเร็จ|รอ|ฝัน|ใจ")
_EMOTION = re.compile(r"รัก|เศร้า|เสียใจ|คิดถึง|จากไป|ผิดหวัง|เหงา|ท้อ|หวัง|กำลังใจ|ปล่อยวาง")


def classify_hook(title):
    """Return the hook style of a video title (first matching rule wins)."""
    t = str(title)
    if _QUESTION.search(t):
        return "question"
    if _TIME_BOUND.search(t):
        return "time_promise"
    if _RELATIONAL.search(t):
        return "relational_scene"
    if _EMOTION.search(t):
        return "emotional"
    if _ACTION.search(t):
        return "action_cta"
    if _ABSTRACT.search(t):
        return "abstract_metaphor"
    return "other"


def ypp_math(subs, watch_hours_12mo, shorts_views_90d, days_active=None):
    """Return the distance to each YPP threshold, plus a verdict."""
    subs_gap = max(0, SUBS_REQUIRED - int(subs))
    hours_gap = max(0, WATCH_HOURS_REQUIRED - float(watch_hours_12mo))
    shorts_gap = max(0, SHORTS_VIEWS_REQUIRED - int(shorts_views_90d))
    shorts_multiple = (SHORTS_VIEWS_REQUIRED / shorts_views_90d) if shorts_views_90d else None
    hours_multiple = (WATCH_HOURS_REQUIRED / watch_hours_12mo) if watch_hours_12mo else None
    daily_subs = (subs / days_active) if days_active else None
    days_to_subs = (subs_gap / daily_subs) if daily_subs else None
    return {
        "subs": subs,
        "subs_gap": subs_gap,
        "watch_hours_gap": round(hours_gap, 2),
        "shorts_views_gap": shorts_gap,
        "shorts_views_needed_multiple": round(shorts_multiple, 1) if shorts_multiple else None,
        "watch_hours_needed_multiple": round(hours_multiple, 1) if hours_multiple else None,
        "daily_subs": round(daily_subs, 3) if daily_subs else None,
        "days_to_1000_subs": int(days_to_subs) if days_to_subs else None,
        "reachable": bool(subs_gap == 0 and (hours_gap == 0 or shorts_gap == 0)),
    }


def hook_performance(channels):
    """Average views per hook style across every top video we know about."""
    buckets = {}
    for ch in channels:
        for v in ch.get("top_videos") or []:
            if not isinstance(v, dict) or not isinstance(v.get("views"), int):
                continue
            h = classify_hook(v.get("title", ""))
            buckets.setdefault(h, []).append(v["views"])
    out = {}
    for h, views in buckets.items():
        out[h] = {"count": len(views), "avg_views": round(sum(views) / len(views), 1),
                  "max_views": max(views)}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["avg_views"]))


def shorts_share(channel):
    """Estimate what fraction of the last-10 average comes from Shorts."""
    avg = channel.get("avg_views_last_10")
    if not isinstance(avg, int) or avg <= 0:
        return None
    top = [v["views"] for v in (channel.get("top_videos") or [])
           if isinstance(v.get("views"), int)]
    if not top:
        return None
    return round(max(top) / avg, 2)


def analyse(report):
    """Full analysis for one AI report."""
    chs = report.get("channels") or []
    total_subs = sum(int(c.get("subscribers") or 0) for c in chs)
    total_videos = sum(int(c.get("total_videos") or 0) for c in chs)
    per_channel = []
    for c in chs:
        per_channel.append({
            "channel": c.get("channel_name"),
            "subs": c.get("subscribers"),
            "videos": c.get("total_videos"),
            "avg_views_last_10": c.get("avg_views_last_10"),
            "shorts_dominance": shorts_share(c),
        })
    return {
        "channels": len(chs),
        "total_subs": total_subs,
        "total_videos": total_videos,
        "subs_gap_to_1000": max(0, SUBS_REQUIRED - total_subs),
        "per_channel": per_channel,
        "hook_performance": hook_performance(chs),
    }


def verdict_lines(analysis, days_active=None):
    """Plain-Thai summary of where the team actually stands."""
    a = analysis
    lines = [
        f"ช่อง {a['channels']} ช่อง | คลิปทั้งหมด {a['total_videos']} | sub รวม {a['total_subs']}",
        f"ยังขาดอีก {a['subs_gap_to_1000']} sub จึงจะถึง 1,000",
        "",
        "ผลตอบแทนตามสไตล์ hook (จากคลิปที่รู้ตัวเลข):",
    ]
    for h, d in a["hook_performance"].items():
        lines.append(f"   {h:<18} เฉลี่ย {d['avg_views']:>7} วิว  (สูงสุด {d['max_views']}, n={d['count']})")
    lines += ["", "สัดส่วนวิวที่มาจาก Shorts (ยิ่งสูง = คลิปยาวแทบไม่มีคนดู):"]
    for p in a["per_channel"]:
        s = p["shorts_dominance"]
        lines.append(f"   {str(p['channel'])[:32]:<34} x{s if s is not None else 'UNKNOWN'}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="วิเคราะห์ช่อง YouTube จากรายงาน AI")
    p.add_argument("path", help="ไฟล์ JSON ของรายงาน")
    p.add_argument("--json", action="store_true")
    p.add_argument("--days-active", type=int, default=None,
                   help="อายุช่อง (วัน) ใช้คำนวณ sub/วัน")
    a = p.parse_args(argv)
    report = json.load(open(a.path, encoding="utf-8"))
    ana = analyse(report)
    if a.json:
        print(json.dumps(ana, ensure_ascii=False, indent=2))
    else:
        print(verdict_lines(ana, a.days_active))
    return 0


if __name__ == "__main__":
    sys.exit(main())
