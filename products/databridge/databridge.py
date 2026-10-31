#!/usr/bin/env python3
"""databridge: convert between CSV and JSON, in both directions.

CLI:
    python -m databridge csv2json in.csv out.json [--indent 2] [--delimiter ,]
    python -m databridge json2csv in.json out.csv [--delimiter ,]

Library:
    from databridge import csv_to_json, json_to_csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from typing import Any


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def csv_to_json(text: str, delimiter: str | None = None) -> str:
    """Parse CSV text into a JSON array of objects.

    A header row is required. Missing/extra columns are tolerated by csv.DictReader.
    """
    if not text.strip():
        return "[]"
    if delimiter is None:
        delimiter = _sniff_delimiter(text[:2048])
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = [dict(row) for row in reader]
    return json.dumps(rows, ensure_ascii=False, indent=2)


def json_to_csv(text: str, delimiter: str = ",") -> str:
    """Convert a JSON array of flat objects into CSV text.

    Keys are unioned across records; missing values become an empty string.
    """
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("JSON root must be an array of objects")
    fieldnames: list[str] = []
    for record in data:
        if not isinstance(record, dict):
            raise ValueError("every JSON array element must be an object")
        for key in record:
            if key not in fieldnames:
                fieldnames.append(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, delimiter=delimiter,
                            quoting=csv.QUOTE_MINIMAL, extrasaction="ignore")
    writer.writeheader()
    for record in data:
        writer.writerow({k: ("" if record.get(k) is None else record.get(k)) for k in fieldnames})
    return buf.getvalue()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="databridge")
    sub = parser.add_subparsers(dest="command", required=True)

    c2j = sub.add_parser("csv2json", help="convert CSV to JSON")
    c2j.add_argument("input")
    c2j.add_argument("output")
    c2j.add_argument("--delimiter", default=None)
    c2j.add_argument("--indent", type=int, default=2)

    j2c = sub.add_parser("json2csv", help="convert JSON to CSV")
    j2c.add_argument("input")
    j2c.add_argument("output")
    j2c.add_argument("--delimiter", default=",")

    args = parser.parse_args(argv)

    if args.command == "csv2json":
        text = open(args.input, encoding="utf-8").read()
        out = csv_to_json(text, args.delimiter)
        parsed = json.loads(out)
        out = json.dumps(parsed, ensure_ascii=False, indent=args.indent)
        open(args.output, "w", encoding="utf-8").write(out)
    else:
        text = open(args.input, encoding="utf-8").read()
        open(args.output, "w", encoding="utf-8", newline="").write(json_to_csv(text, args.delimiter))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
