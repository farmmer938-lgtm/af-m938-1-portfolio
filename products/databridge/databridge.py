"""databridge — CSV <-> JSON conversion with delimiter sniffing and type inference.

Zero third-party dependencies. Handles quoted fields with embedded delimiters
and newlines, key union across JSON records, RFC 4180 escaping, and unicode.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

DELIMS = [",", ";", "\t", "|"]


def sniff_delimiter(text: str) -> str:
    """Pick the delimiter with the highest count on the first non-empty line."""
    line = next((ln for ln in text.splitlines() if ln.strip()), "")
    best, best_n = ",", -1
    for d in DELIMS:
        n = line.count(d)
        if n > best_n:
            best, best_n = d, n
    return best


def infer(value: Any) -> Any:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return ""
    if s.lower() in {"true", "false"}:
        return s.lower() == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def csv_to_json(text: str, delimiter: str | None = None) -> list[dict[str, Any]]:
    delim = delimiter or sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []
    headers = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        out.append({headers[i]: infer(r[i]) if i < len(r) else "" for i in range(len(headers))})
    return out


def json_to_csv(records: list[dict[str, Any]], delimiter: str = ",") -> str:
    if not records:
        return ""
    headers: list[str] = []
    for rec in records:
        for k in rec:
            if k not in headers:
                headers.append(k)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for rec in records:
        writer.writerow(["" if rec.get(h) is None else rec.get(h, "") for h in headers])
    return buf.getvalue()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "to-json":
        print(json.dumps(csv_to_json(sys.stdin.read()), indent=2))
    else:
        print(json_to_csv(json.load(sys.stdin)), end="")
