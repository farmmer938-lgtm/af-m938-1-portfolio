#!/usr/bin/env python3
"""JSON -> CSV converter for arrays of flat objects.

Spec points from the brief: Python 3.10+, reads a JSON file that is an array of
flat objects, writes CSV, and handles missing keys gracefully (empty string).

Extra care taken beyond the brief:
  * union of keys across all objects, in first-seen order (stable columns)
  * nested values are JSON-encoded into the cell rather than dropped
  * values containing delimiter, quote, or newline are quoted per RFC 4180
  * optional --columns to pin/order the header, with missing keys as empty cells

Usage:
  python3 json_to_csv.py input.json -o out.csv
  python3 json_to_csv.py input.json --columns id,name,email
  cat in.json | python3 json_to_csv.py -
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def convert(data, columns: list[str] | None = None) -> str:
    if not isinstance(data, list):
        raise ValueError("top-level JSON must be an array of objects")
    keys: list[str] = []
    if columns:
        keys = list(columns)
    else:
        for obj in data:
            if isinstance(obj, dict):
                for k in obj:
                    if k not in keys:
                        keys.append(k)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(keys)
    for obj in data:
        if not isinstance(obj, dict):
            raise ValueError("every array item must be an object")
        writer.writerow([_cell(obj.get(k, "")) for k in keys])
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convert JSON (array of objects) to CSV.")
    ap.add_argument("input", help="JSON path, or - for stdin")
    ap.add_argument("-o", "--output", help="write CSV here (default stdout)")
    ap.add_argument("--columns", help="comma-separated header to pin and order")
    a = ap.parse_args(argv)

    raw = sys.stdin.read() if a.input == "-" else open(a.input, encoding="utf-8").read()
    data = json.loads(raw)
    cols = [c.strip() for c in a.columns.split(",")] if a.columns else None
    out = convert(data, cols)
    if a.output:
        with open(a.output, "w", encoding="utf-8", newline="") as f:
            f.write(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
