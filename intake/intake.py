#!/usr/bin/env python3
"""Intake schema + validator for the AF / AI-team information request.

The other AI agents (AI1, AI2) fill a JSON report. This module validates it so
AF never builds on fabricated numbers. Anything the agent could not verify must
be the literal string "UNKNOWN" — that is allowed but flagged, so AF knows what
still needs a human to fetch.

Zero dependencies.
"""
import argparse
import json
import sys

UNKNOWN = "UNKNOWN"

CHANNEL_REQUIRED = ["channel_name", "niche", "biggest_problem"]
ACCOUNT_REQUIRED = ["account_label", "channels"]
FORMATS = {"shorts", "long", "mixed"}


def _is_unknown(v):
    return isinstance(v, str) and v.strip().upper() == UNKNOWN


def _missing(fields, obj):
    return [f for f in fields if f not in obj]


def validate_channel(ch, idx=0):
    """Return (errors, warnings) for one channel block."""
    errors, warnings = [], []
    if not isinstance(ch, dict):
        return [f"channels[{idx}] is not an object"], []
    for f in _missing(CHANNEL_REQUIRED, ch):
        errors.append(f"channels[{idx}].{f} missing")
    name = ch.get("channel_name", f"[{idx}]")
    if _is_unknown(ch.get("channel_name")):
        errors.append(f"channels[{idx}].channel_name cannot be UNKNOWN")
    fmt = ch.get("format")
    if fmt is not None and not _is_unknown(fmt) and fmt not in FORMATS:
        errors.append(f"channels[{idx}].format must be one of {sorted(FORMATS)}")
    for numf in ("subscribers", "total_videos", "avg_views_last_10"):
        v = ch.get(numf)
        if v is None or _is_unknown(v):
            warnings.append(f"{name}: {numf} is UNKNOWN")
        elif not isinstance(v, int) or v < 0:
            errors.append(f"channels[{idx}].{numf} must be a non-negative integer")
    upw = ch.get("uploads_per_week")
    if upw is not None and not _is_unknown(upw) and not isinstance(upw, (int, float)):
        errors.append(f"channels[{idx}].uploads_per_week must be a number or UNKNOWN")
    tv = ch.get("top_videos")
    if tv is None or _is_unknown(tv):
        warnings.append(f"{name}: top_videos is UNKNOWN")
    elif not isinstance(tv, list) or not tv:
        errors.append(f"channels[{idx}].top_videos must be a non-empty list")
    else:
        for j, v in enumerate(tv):
            if not isinstance(v, dict) or "title" not in v:
                errors.append(f"channels[{idx}].top_videos[{j}] needs a title")
            elif v.get("views") is None:
                warnings.append(f"{name}: top_videos[{j}] has no view count")
    for f in ("monetized", "monthly_revenue_thb"):
        if f not in ch or _is_unknown(ch.get(f)):
            warnings.append(f"{name}: {f} is UNKNOWN")
    if not ch.get("needs_help_with") or _is_unknown(ch.get("needs_help_with")):
        warnings.append(f"{name}: needs_help_with empty — AF will not know what to build")
    return errors, warnings


def validate_report(obj):
    """Return a dict with errors, warnings, unknowns and a summary."""
    errors, warnings = [], []
    if not isinstance(obj, dict):
        return {"ok": False, "errors": ["report is not a JSON object"],
                "warnings": [], "unknown_count": 0, "channel_count": 0}
    for f in _missing(ACCOUNT_REQUIRED, obj):
        errors.append(f"{f} missing at top level")
    chs = obj.get("channels")
    if not isinstance(chs, list) or not chs:
        errors.append("channels must be a non-empty list")
        chs = []
    for i, ch in enumerate(chs):
        e, w = validate_channel(ch, i)
        errors += e
        warnings += w
    for extra in ("other_platforms", "shopee", "assets"):
        if extra not in obj:
            warnings.append(f"{extra} not provided")
    unknowns = json.dumps(obj, ensure_ascii=False).count(UNKNOWN)
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "unknown_count": unknowns,
        "channel_count": len(chs),
    }


def summarise(report):
    """Human-readable lines for chat output."""
    lines = [f"ช่อง: {report['channel_count']} | ค่าที่ยังไม่รู้: {report['unknown_count']}"]
    if report["errors"]:
        lines.append("❌ ต้องแก้:")
        lines += [f"   - {e}" for e in report["errors"]]
    if report["warnings"]:
        lines.append("⚠️  ควรเติม:")
        lines += [f"   - {w}" for w in report["warnings"]]
    if report["ok"] and not report["warnings"]:
        lines.append("✅ ครบถ้วน พร้อมให้ AF ผลิตงานต่อ")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="ตรวจแบบฟอร์มข้อมูลจาก AI ทีม")
    p.add_argument("path", nargs="?", help="ไฟล์ JSON ที่ AI ตอบกลับ")
    p.add_argument("--json", action="store_true", help="พิมพ์ผลเป็น JSON")
    a = p.parse_args(argv)
    raw = open(a.path, encoding="utf-8").read() if a.path else sys.stdin.read()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON ไม่ถูกต้อง: {e}", file=sys.stderr)
        return 2
    rep = validate_report(obj)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else summarise(rep))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
