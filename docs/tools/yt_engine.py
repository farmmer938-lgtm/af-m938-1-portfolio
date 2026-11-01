#!/usr/bin/env python3
"""YouTube content engine — turn one topic into a publish-ready video package.

Zero dependencies. Produces title variants, an SEO description with chapters,
tags, thumbnail text, a hook and an outline. Designed for batch production
across several channels.
"""
import argparse
import json
import re
import sys

TITLE_FORMULAS = [
    ("how_to", "{topic} — ทำยังไงให้ได้ผลจริงใน {year}"),
    ("listicle", "{n} เรื่องที่ต้องรู้ก่อนเริ่ม {topic}"),
    ("mistake", "5 ความผิดพลาดเรื่อง {topic} ที่มือใหม่เจอบ่อย"),
    ("result", "จาก 0 ถึงใช้ได้จริงกับ {topic} (ทำตามได้เลย)"),
    ("question", "{topic} เริ่มจากตรงไหน? ตอบครบในคลิปเดียว"),
]

DEFAULT_SECTIONS = ["ทำไมเรื่องนี้สำคัญ", "สิ่งที่ต้องเตรียม", "ขั้นตอนทีละขั้น",
                    "ข้อผิดพลาดที่ต้องเลี่ยง", "สรุปและก้าวต่อไป"]

CTA = "ถ้าคลิปนี้มีประโยชน์ กดติดตามและกดกระดิ่งไว้ อย่าพลาดคลิปต่อไป"


def slug(text, max_len=60):
    """URL-safe slug from Thai or English text."""
    s = re.sub(r"[^\w\s-]", "", str(text), flags=re.UNICODE).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:max_len].strip("-")


def title_variants(topic, year=2026, count=5):
    out = []
    for i, (_kind, f) in enumerate(TITLE_FORMULAS[:count]):
        t = f.format(topic=topic, year=year, n=7 + i)
        out.append(t[:100])
    return out


def outline(topic, sections=None):
    return [{"step": i + 1, "heading": h, "talking_points": 2}
            for i, h in enumerate(sections or DEFAULT_SECTIONS)]


def description(topic, keywords=None, sections=None, channel=None):
    keywords = keywords or []
    steps = outline(topic, sections)
    lines = [
        f"{topic} — คลิปนี้สรุปให้ครบ จบในที่เดียว เหมาะกับมือใหม่ที่อยากเริ่มแบบไม่เสียเวลาลองผิดลองถูก",
        "",
        "⏱️ Chapters",
    ]
    for s in steps:
        lines.append(f"{s['step']:02d}:00 {s['heading']}")
    lines += ["", "📌 สิ่งที่คุณจะได้จากคลิปนี้"]
    lines += [f"- {s['heading']}" for s in steps]
    if keywords:
        lines += ["", "🔎 หัวข้อที่เกี่ยวข้อง: " + ", ".join(keywords[:10])]
    if channel:
        lines += ["", f"ติดตามช่อง {channel} สำหรับคลิปแบบนี้ทุกสัปดาห์"]
    lines += ["", CTA]
    return "\n".join(lines)


def tags(topic, niche=None, keywords=None, limit=15):
    pool = [topic] + (keywords or []) + ([niche] if niche else [])
    pool += [f"{topic} มือใหม่", f"{topic} 2026", f"วิธี {topic}", "สอนฟรี",
             "ทำตามได้เลย", "มือใหม่", "how to", "tutorial"]
    seen, out = set(), []
    for t in pool:
        k = t.strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    return out[:limit]


def thumbnail_text(topic, max_words=4):
    words = str(topic).split()
    return " ".join(words[:max_words])[:40]


def package(topic, niche=None, keywords=None, channel=None, sections=None, year=2026):
    return {
        "topic": topic,
        "slug": slug(topic),
        "titles": title_variants(topic, year),
        "description": description(topic, keywords, sections, channel),
        "tags": tags(topic, niche, keywords),
        "thumbnail_text": thumbnail_text(topic),
        "hook": f"รู้ไหมว่าคนส่วนใหญ่พลาดเรื่อง {topic} เพราะไม่รู้ 3 ข้อนี้ — มาดูกัน",
        "outline": outline(topic, sections),
    }


def validate(pkg):
    """Return a list of problems; empty list means publish-ready."""
    issues = []
    if not pkg.get("titles"):
        issues.append("no titles")
    if pkg.get("titles") and any(len(t) > 100 for t in pkg["titles"]):
        issues.append("title over 100 chars")
    if len(pkg.get("description", "")) > 5000:
        issues.append("description over 5000 chars")
    if sum(len(t) for t in pkg.get("tags", [])) + len(pkg.get("tags", [])) > 500:
        issues.append("tags over 500 chars")
    if not pkg.get("outline"):
        issues.append("no outline")
    return issues


def batch(niche, topics, channel=None, keywords=None):
    return [package(t, niche=niche, channel=channel, keywords=keywords) for t in topics]


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate YouTube video packages.")
    p.add_argument("topic", nargs="?", default="ทำคอนเทนต์ด้วย AI")
    p.add_argument("--niche", default=None)
    p.add_argument("--channel", default=None)
    p.add_argument("--keywords", default="")
    p.add_argument("--batch", default="", help="comma-separated extra topics")
    a = p.parse_args(argv)
    kw = [k.strip() for k in a.keywords.split(",") if k.strip()]
    if a.batch:
        topics = [a.topic] + [t.strip() for t in a.batch.split(",") if t.strip()]
        out = batch(a.niche, topics, a.channel, kw)
    else:
        out = [package(a.topic, niche=a.niche, channel=a.channel, keywords=kw)]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
