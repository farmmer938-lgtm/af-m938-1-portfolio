#!/usr/bin/env python3
"""Measure public social accounts with no API key and no login.

Why this exists: asking another AI to read its own dashboard hit an output
limit, and its sandbox ran out of room. Anyone can open these pages in a
browser, so AF measures them directly instead.

Supported: YouTube channel, TikTok profile, Facebook page, Shopee shop.
Values are measured or reported UNKNOWN. Nothing is estimated.

Zero dependencies (urllib + json + re).
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
UNKNOWN = "UNKNOWN"
TIMEOUT = 25
HEADERS = {"User-Agent": UA, "Accept-Language": "th,en;q=0.8",
           "Cookie": "CONSENT=YES+cb; SOCS=CAI"}


def fetch(url):
    """Return page text, or None when it cannot be fetched.

    Tries urllib first; falls back to curl because some sites (Facebook) serve
    a usable page only to a plain curl user agent.
    """
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        pass
    try:
        out = subprocess.run(
            ["curl", "-sL", "-m", str(TIMEOUT), "-A", UA,
             "-H", "Accept-Language: th,en;q=0.8", url],
            capture_output=True, timeout=TIMEOUT + 5)
        if out.returncode == 0 and out.stdout:
            return out.stdout.decode("utf-8", errors="ignore")
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _meta(text, prop):
    m = re.search(r'<meta property="' + re.escape(prop) + r'" content="([^"]*)"', text)
    return m.group(1) if m else None


def parse_compact_number(text):
    """'ผู้ติดตาม 11 คน' / '11 subscribers' / '1.2K' / '2,674' -> int."""
    if not text:
        return UNKNOWN
    cleaned = str(text).replace(",", "").replace("\u00a0", " ")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KMB])?", cleaned, re.I)
    if not m:
        return UNKNOWN
    val = float(m.group(1))
    mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get((m.group(2) or "").lower(), 1)
    out = val * mult
    return int(out) if float(out).is_integer() else out


def _flat_field(text, key):
    """Read a flat ytInitialData field like \"subscriberCountText\":\"ผู้ติดตาม 11 คน\"."""
    m = re.search('"' + re.escape(key) + '":\\{"simpleText":"([^"]+)"', text)
    if not m:
        m = re.search('"' + re.escape(key) + '":"([^"]+)"', text)
    return m.group(1) if m else None


def parse_youtube(text, handle):
    """Name, subscribers, public videos, total views, channel id."""
    name = _meta(text, "og:title") or UNKNOWN
    subs_raw = _flat_field(text, "subscriberCountText")
    vids_raw = _flat_field(text, "videoCountText")
    views_raw = _flat_field(text, "viewCountText")
    cid = re.search(r'"externalId":"(UC[\w-]+)"', text)
    country = re.search(r'"country":"([^"]+)"', text)
    return {
        "platform": "youtube",
        "handle": handle,
        "url": f"https://www.youtube.com/@{handle}",
        "name": name,
        "subscribers": parse_compact_number(subs_raw),
        "subscribers_raw": subs_raw or UNKNOWN,
        "videos_public": parse_compact_number(vids_raw),
        "total_views": parse_compact_number(views_raw),
        "channel_id": cid.group(1) if cid else UNKNOWN,
        "country": country.group(1) if country else UNKNOWN,
    }


def parse_youtube_videos(text, limit=10):
    """Video titles + view counts from a channel videos page.

    YouTube now renders the grid as lockupViewModel blocks, so each item is
    split on that key and read field by field.
    """
    out = []
    for b in text.split('"lockupViewModel":{')[1:]:
        title = re.search(r'"lockupMetadataViewModel":\{"title":\{"content":"([^"]{2,200})"', b)
        if not title:
            continue
        cid = re.search(r'"contentId":"([\w-]{11})"', b)
        views = re.search(r'"metadataParts":\[\{"text":\{"content":"([\d.,]+)"', b)
        out.append({
            "video_id": cid.group(1) if cid else UNKNOWN,
            "title": title.group(1)[:120],
            "views": parse_compact_number(views.group(1) if views else None),
            "url": f"https://youtu.be/{cid.group(1)}" if cid else UNKNOWN,
        })
        if len(out) >= limit:
            break
    return out


def parse_youtube_shorts(text, limit=20):
    """Shorts tab uses shortsLockupViewModel, not lockupViewModel.

    Each item carries an accessibilityText of the form
    '<title>, การดู <views> ครั้ง - เล่นวิดีโอสั้น'.
    """
    out = []
    for b in text.split('"shortsLockupViewModel":{')[1:]:
        eid = re.search(r'"entityId":"shorts-shelf-item-([\w-]{11})"', b)
        acc = re.search(r'"accessibilityText":"([^"]+)"', b)
        if not acc:
            continue
        label = acc.group(1)
        title = label.split(", การดู")[0].strip()
        views = re.search(r"การดู\s*([\d.,]+)\s*ครั้ง", label)
        out.append({
            "video_id": eid.group(1) if eid else UNKNOWN,
            "title": title[:120],
            "views": parse_compact_number(views.group(1) if views else None),
            "url": f"https://youtu.be/{eid.group(1)}" if eid else UNKNOWN,
        })
        if len(out) >= limit:
            break
    return out


def parse_tiktok(text, handle):
    name = _meta(text, "og:title") or UNKNOWN
    f = re.search(r'"followerCount":(\d+)', text)
    v = re.search(r'"videoCount":(\d+)', text)
    h = re.search(r'"heartCount":(\d+)', text)
    return {
        "platform": "tiktok",
        "handle": handle,
        "url": f"https://www.tiktok.com/@{handle}",
        "name": name,
        "followers": int(f.group(1)) if f else UNKNOWN,
        "videos": int(v.group(1)) if v else UNKNOWN,
        "likes": int(h.group(1)) if h else UNKNOWN,
    }


def parse_facebook(text, ref):
    name = _meta(text, "og:title") or UNKNOWN
    desc = _meta(text, "og:description") or ""
    f = re.search(r"([\d,]+)\s*(?:followers|ผู้ติดตาม)", desc)
    t = re.search(r"([\d,]+)\s*(?:talking about this|กำลังพูดถึง)", desc)
    return {
        "platform": "facebook",
        "ref": ref,
        "name": name,
        "followers": int(f.group(1).replace(",", "")) if f else UNKNOWN,
        "talking_about": int(t.group(1).replace(",", "")) if t else UNKNOWN,
    }


def parse_shopee(text, ref):
    name = _meta(text, "og:title") or UNKNOWN
    followers = re.search(r'"follower_count":(\d+)', text)
    rating = re.search(r'"rating_star":([\d.]+)', text)
    items = re.search(r'"item_count":(\d+)', text)
    return {
        "platform": "shopee",
        "ref": ref,
        "name": name,
        "followers": int(followers.group(1)) if followers else UNKNOWN,
        "rating": float(rating.group(1)) if rating else UNKNOWN,
        "item_count": int(items.group(1)) if items else UNKNOWN,
    }


def measure(platform, handle, with_videos=False):
    """Measure one account. Never raises."""
    if platform == "youtube":
        text = fetch(f"https://www.youtube.com/@{handle}/about")
        if text is None:
            return {"platform": platform, "handle": handle, "error": "fetch failed"}
        out = parse_youtube(text, handle)
        if with_videos:
            vt = fetch(f"https://www.youtube.com/@{handle}/videos")
            out["recent_videos"] = parse_youtube_videos(vt) if vt else []
            st = fetch(f"https://www.youtube.com/@{handle}/shorts")
            out["recent_shorts"] = parse_youtube_shorts(st) if st else []
        return out
    templates = {
        "tiktok": ("https://www.tiktok.com/@{}", parse_tiktok),
        "facebook": ("https://www.facebook.com/{}", parse_facebook),
        "shopee": ("https://shopee.co.th/{}", parse_shopee),
    }
    if platform not in templates:
        return {"platform": platform, "handle": handle, "error": "unsupported platform"}
    tpl, parser = templates[platform]
    text = fetch(tpl.format(handle))
    if text is None:
        return {"platform": platform, "handle": handle, "error": "fetch failed"}
    out = parser(text, handle)
    out.setdefault("url", tpl.format(handle))
    return out


def summary(rows):
    lines = []
    for r in rows:
        if r.get("error"):
            lines.append(f"❌ {r.get('platform')} {r.get('handle') or r.get('ref')}: {r['error']}")
            continue
        p = r["platform"]
        if p == "youtube":
            lines.append(f"📺 {r['name']}")
            lines.append(f"   @{r['handle']} | sub {r['subscribers']} | คลิปสาธารณะ {r['videos_public']} "
                         f"| ดูรวม {r['total_views']:,} ครั้ง" if isinstance(r['total_views'], int)
                         else f"   @{r['handle']} | sub {r['subscribers']}")
            for v in r.get("recent_videos", [])[:3]:
                lines.append(f"     • {v['views']:>7} วิว | {v['title'][:60]}")
        elif p == "tiktok":
            lines.append(f"🎵 TikTok @{r['handle']}: {r['name']} — ผู้ติดตาม {r['followers']}, คลิป {r['videos']}, ใจ {r['likes']}")
        elif p == "facebook":
            lines.append(f"📘 Facebook {r['ref']}: {r['name']} — ผู้ติดตาม {r['followers']}, กำลังพูดถึง {r['talking_about']}")
        elif p == "shopee":
            lines.append(f"🛒 Shopee {r['ref']}: {r['name']} — ผู้ติดตาม {r['followers']}, คะแนน {r['rating']}, สินค้า {r['item_count']}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="วัดบัญชีโซเชียลจากข้อมูลสาธารณะ")
    p.add_argument("targets", nargs="*", help="platform:handle เช่น youtube:tatagenxgeny")
    p.add_argument("--json", action="store_true")
    p.add_argument("--videos", action="store_true", help="ดึงคลิปล่าสุดด้วย (YouTube)")
    a = p.parse_args(argv)
    parsed = []
    for t in a.targets:
        if ":" not in t:
            print(f"รูปแบบต้องเป็น platform:handle -> {t}", file=sys.stderr)
            return 2
        plat, _, h = t.partition(":")
        parsed.append((plat, h))
    if not parsed:
        print("ต้องระบุอย่างน้อย 1 เป้าหมาย", file=sys.stderr)
        return 2
    rows = [measure(p_, h, a.videos) for p_, h in parsed]
    print(json.dumps(rows, ensure_ascii=False, indent=2) if a.json else summary(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
