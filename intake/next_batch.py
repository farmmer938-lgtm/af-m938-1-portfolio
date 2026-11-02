#!/usr/bin/env python3
"""Next-batch planner: turn measured winners into NEW videos to publish.

It learns the *pattern* behind each channel's winning titles, then generates
fresh topics in that same pattern. It never reuses a published title, because
YouTube suppresses duplicate uploads.

Patterns were derived from the measured data:
  - Farmmer   : "problem? -> instant fix" (นอนไม่หลับ? ลองทำท่านี้ 10 วินาที) avg 1288
  - เรื่องเล่า : relational scene (แม่/พ่อ) avg 769, abstract metaphor only avg 510
  - ตาต้า      : Shorts win, long-form philosophy gets ~6 views

Zero dependencies.
"""
import argparse
import json
import sys

import channel_analysis as ca

THUMB_MAX = 22
TITLE_MAX = 100

# Fresh topics per winning pattern. Each list is ordered by measured strength.
PATTERN_TOPICS = {
    "problem_fix": [
        "นอนไม่หลับ? ลองหายใจแบบนี้ 10 วินาที",
        "ตื่นกลางดึกบ่อย? ทำ 3 อย่างนี้ก่อนนอน",
        "คิดมากจนนอนไม่หลับ? ลองวิธีนี้คืนนี้",
        "ปวดหัวตอนเช้า? เช็คท่านอนนี้ก่อน",
        "เหนื่อยแต่หลับไม่ลง? ลองท่านี้ 1 นาที",
        "ขี้เกียจเข้านอน? ตั้งใจแบบนี้แทน",
    ],
    "relational": [
        "คืนนั้นพ่อกลับบ้านช้า เพราะไปรับจ็อบเพิ่มให้เรา",
        "วันที่แม่ป่วย แต่ยังทำกับข้าวให้เรากิน",
        "น้องโทรมาหา แต่เราบอกว่าไม่ว่าง",
        "วันที่พ่อขอโทษเราเป็นครั้งแรก",
        "แม่เก็บเงินใส่กระปุกไว้ให้เราตั้งแต่เด็ก",
        "คืนสุดท้ายที่ได้นั่งกินข้าวกับยาย",
    ],
    "emotional_release": [
        "ก่อนนอนคืนนี้ ลองปล่อยเรื่องนั้นไป",
        "เรื่องที่ยังคิดถึง ปล่อยให้มันผ่านไปเถอะ",
        "เหนื่อยมาทั้งวัน คืนนี้ไม่ต้องเก่งก็ได้",
        "คนที่จากไป ไม่ได้อยากให้เราจมอยู่กับมัน",
        "สิ่งที่เสียไปแล้ว คืนนี้วางมันลงก่อน",
        "พรุ่งนี้ค่อยคิด คืนนี้พักก่อน",
    ],
    "instant_relief": [
        "เปิดทิ้งไว้ทั้งคืน หลับลึกถึงเช้า",
        "ฟัง 10 นาที ใจเย็นลงทันที",
        "เปิดเสียงนี้ตอนเครียด ได้ผลจริง",
        "หลับง่ายขึ้น หลังฟังคลิปนี้จบ",
        "เสียงนี้ช่วยให้สมองหยุดคิดก่อนนอน",
        "ฟังตอนตื่นมา แล้ววันนี้จะต่างออกไป",
    ],
    "life_lesson": [
        "ก้าวเล็ก ๆ ที่ไม่มีใครเห็น แต่สำคัญที่สุด",
        "วันที่ไม่มีใครเชื่อเรา แต่เรายังเชื่อตัวเอง",
        "ความล้มเหลวที่สอนเรามากกว่าความสำเร็จ",
        "คนที่ไปเร็ว ไม่ได้แปลว่าจะไปไกล",
        "สิ่งที่เราเสียไป ทำให้เราได้สิ่งนี้มา",
        "วันที่คิดจะยอมแพ้ แต่ยังไปต่อ",
    ],
}

# Which patterns suit which channel (by keyword found in the niche).
CHANNEL_PATTERNS = [
    (("ธรรมะ", "นอน", "สมาธิ", "sleep"), ["problem_fix", "instant_relief", "emotional_release"]),
    (("เรื่องเล่า", "ดราม่า", "การ์ตูน", "story"), ["relational", "emotional_release"]),
    (("ปรัชญา", "กำลังใจ", "philosophy"), ["life_lesson", "emotional_release"]),
]

SHORTS_SUFFIX = [" #Shorts", " ใน 30 วินาที #Shorts", " — ฟังแล้วจะคิดได้ #Shorts"]
LONG_SUFFIX = [" — ฉบับเต็ม", " | เล่าให้ฟังทั้งหมด", " (เรื่องจริง)", " | ฟังก่อนนอน"]


def patterns_for(channel):
    niche = str(channel.get("niche", "")) + str(channel.get("channel_name", ""))
    for keys, pats in CHANNEL_PATTERNS:
        if any(k in niche for k in keys):
            return pats
    return ["life_lesson", "emotional_release"]


def measured_best(channel):
    """This channel's own best hook style, by views."""
    vids = [v for v in (channel.get("top_videos") or [])
            if isinstance(v, dict) and isinstance(v.get("views"), int)]
    if not vids:
        return None
    return ca.classify_hook(max(vids, key=lambda v: v["views"])["title"])


def thumb_text(topic):
    """Thumbnail text: the part before '?' or the first few words."""
    t = topic.split("?")[0].strip() or topic
    out = ""
    for w in t.split():
        if len(out) + len(w) + 1 > THUMB_MAX:
            break
        out = (out + " " + w).strip()
    return out or topic[:THUMB_MAX]


def published_titles(report):
    """Every title already published, so we never duplicate one."""
    seen = set()
    for ch in report.get("channels") or []:
        for v in ch.get("top_videos") or []:
            if isinstance(v, dict) and v.get("title"):
                seen.add(str(v["title"]).strip())
    return seen


def _pick(pool, i, used, published, suffix_list):
    """Find the next unused topic+suffix that is not a published title."""
    n = len(pool)
    for step in range(n * len(suffix_list) * 2):
        pat, topic = pool[(i + step) % n]
        if topic in used:
            continue
        title = topic + suffix_list[(i + step) % len(suffix_list)]
        if title not in published:
            return pat, topic, title
    return pool[i % n][0], pool[i % n][1], pool[i % n][1]


def plan_channel(channel, published, shorts_n=6, long_n=3):
    """Build a fresh batch in the channel's winning patterns."""
    pats = patterns_for(channel)
    pool = [(p, t) for p in pats for t in PATTERN_TOPICS[p]]

    shorts, longs, used = [], [], set()
    for i in range(shorts_n):
        pat, topic, title = _pick(pool, i, used, published, SHORTS_SUFFIX)
        used.add(topic)
        shorts.append({"format": "shorts", "pattern": pat, "title": title[:TITLE_MAX],
                       "thumbnail_text": thumb_text(topic),
                       "hook_line": "2 วินาทีแรกต้องพูดปัญหาหรือคำถามทันที"})
    for j in range(long_n):
        pat, topic, title = _pick(pool, shorts_n + j, used, published, LONG_SUFFIX)
        used.add(topic)
        longs.append({"format": "long", "pattern": pat, "title": title[:TITLE_MAX],
                      "thumbnail_text": thumb_text(topic),
                      "hook_line": "30 วินาทีแรกค้างคำถามไว้ ห้ามเกริ่น",
                      "length_target_min": 8})

    return {
        "channel": channel.get("channel_name"),
        "niche": channel.get("niche"),
        "measured_best_hook": measured_best(channel),
        "patterns_used": pats,
        "next_shorts": shorts,
        "next_long": longs,
    }


def build(report):
    published = published_titles(report)
    return {"account": report.get("account_label"), "published_count": len(published),
            "channels": [plan_channel(c, published) for c in (report.get("channels") or [])]}


def render(plan):
    out = [f"วางแผนจากชื่อคลิปที่เผยแพร่แล้ว {plan['published_count']} ชื่อ (ไม่ซ้ำของเดิม)", ""]
    for ch in plan["channels"]:
        out += ["=" * 58, f"ช่อง: {ch['channel']}",
                f"hook ที่ชนะจริง: {ch['measured_best_hook']}",
                f"สูตรที่ใช้: {', '.join(ch['patterns_used'])}", "",
                f"Shorts {len(ch['next_shorts'])} คลิป:"]
        for s in ch["next_shorts"]:
            out.append(f"   • {s['title']}")
            out.append(f"     ปก: {s['thumbnail_text']}")
        out += ["", f"คลิปยาว {len(ch['next_long'])} คลิป:"]
        for s in ch["next_long"]:
            out.append(f"   • {s['title']}")
            out.append(f"     ปก: {s['thumbnail_text']} | ~{s['length_target_min']} นาที")
        out.append("")
    return "\n".join(out)


def validate(plan):
    """Titles must fit, be non-empty, and never repeat inside a batch."""
    issues = []
    for ch in plan["channels"]:
        titles = [i["title"] for i in ch["next_shorts"] + ch["next_long"]]
        for t in titles:
            if not t.strip():
                issues.append(f"{ch['channel']}: empty title")
            elif len(t) > TITLE_MAX:
                issues.append(f"{ch['channel']}: over {TITLE_MAX} chars: {t}")
        if len(set(titles)) != len(titles):
            issues.append(f"{ch['channel']}: duplicate titles inside the batch")
    return issues


def main(argv=None):
    p = argparse.ArgumentParser(description="วางแผนคลิปใหม่จากสูตรที่ชนะ")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    report = json.load(open(a.path, encoding="utf-8"))
    plan = build(report)
    print(json.dumps(plan, ensure_ascii=False, indent=2) if a.json else render(plan))
    issues = validate(plan)
    if issues:
        print("\nปัญหา:", *issues, sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
