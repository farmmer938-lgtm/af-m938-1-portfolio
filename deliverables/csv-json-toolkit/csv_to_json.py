#!/usr/bin/env python3
"""CSV -> JSON converter that copes with the messy real world.

Handles the things a naive csv.DictReader does not:
  * delimiter sniffing (comma, semicolon, tab, pipe)
  * BOM and non-UTF-8 encodings (utf-8-sig, utf-16, cp1252, latin-1 fallback)
  * quoted fields containing the delimiter or newlines
  * duplicate header names (suffixed _2, _3 ... so no column is silently dropped)
  * blank/ragged rows (padded to the header width)
  * type inference that is opt-in and conservative

Usage:
  python3 csv_to_json.py input.csv                 # JSON array to stdout
  python3 csv_to_json.py input.csv -o out.json
  python3 csv_to_json.py input.csv --ndjson        # one object per line
  python3 csv_to_json.py input.csv --types         # infer int/float/bool/null
  python3 csv_to_json.py - --delimiter ';'         # read stdin
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys

_ENCODINGS = ("utf-8-sig", "utf-16", "cp1252", "latin-1")
_DELIMS = ",;\t|"


def decode(raw: bytes) -> str:
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def sniff_delimiter(sample: str, override: str | None = None) -> str:
    if override:
        return override
    try:
        return csv.Sniffer().sniff(sample, delimiters=_DELIMS).delimiter
    except csv.Error:
        header = sample.splitlines()[0] if sample.splitlines() else sample
        return max(_DELIMS, key=header.count) if header else ","


def dedupe_header(fields: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for i, name in enumerate(fields):
        name = (name or "").strip() or f"column_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        out.append(name)
    return out


def coerce(value: str):
    """Conservative type inference: only clear-cut cases convert."""
    v = value.strip()
    if v == "":
        return ""
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "n/a", "na"):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        f = float(v)
        return f if any(c in v for c in ".eE") else v
    except ValueError:
        return value


def convert(text: str, delimiter: str | None = None, types: bool = False) -> list[dict]:
    delim = sniff_delimiter(text, delimiter)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        header = dedupe_header(next(reader))
    except StopIteration:
        return []
    rows: list[dict] = []
    for raw in reader:
        if not raw or all(c.strip() == "" for c in raw):
            continue
        cells = raw + [""] * (len(header) - len(raw))
        row = {}
        for key, val in zip(header, cells):
            row[key] = coerce(val) if types else val
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convert CSV to JSON.")
    ap.add_argument("input", help="CSV path, or - for stdin")
    ap.add_argument("-o", "--output", help="write JSON here (default stdout)")
    ap.add_argument("--delimiter", help="force a delimiter instead of sniffing")
    ap.add_argument("--types", action="store_true", help="infer int/float/bool/null")
    ap.add_argument("--ndjson", action="store_true", help="one JSON object per line")
    a = ap.parse_args(argv)

    raw = sys.stdin.buffer.read() if a.input == "-" else open(a.input, "rb").read()
    rows = convert(decode(raw), a.delimiter, a.types)
    if a.ndjson:
        out = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    else:
        out = json.dumps(rows, ensure_ascii=False, indent=2)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(out)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
