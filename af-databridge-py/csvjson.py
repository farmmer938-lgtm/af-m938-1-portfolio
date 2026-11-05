#!/usr/bin/env python3
"""stdlib-only CSV <-> JSON converter with delimiter sniffing and robust row handling."""
import argparse, csv, io, json, sys

CANDIDATES = [",", ";", "\t", "|"]

def decode(data: bytes):
    """Decode bytes, falling back through common encodings (incl. cp1252)."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace"), "utf-8(replace)"

def sniff(text: str) -> str:
    """Pick the delimiter that yields the most consistent column count."""
    lines = [l for l in text.splitlines() if l.strip()][:20]
    if not lines:
        return ","
    best, best_score = ",", -1
    for d in CANDIDATES:
        counts = [len(next(csv.reader([l], delimiter=d))) for l in lines]
        if not counts:
            continue
        modal = max(set(counts), key=counts.count)
        score = counts.count(modal) * modal
        if modal > 1 and score > best_score:
            best, best_score = d, score
    return best

def dedupe(headers):
    """Rename duplicate headers: name, name -> name, name_2."""
    seen, out = {}, []
    for h in headers:
        h = h.strip() or "column"
        if h in seen:
            seen[h] += 1
            out.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 1
            out.append(h)
    return out

def coerce(v: str):
    s = v.strip()
    if s == "":
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s

def csv_to_json(text: str, delimiter=None):
    delim = delimiter or sniff(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = list(reader)
    if not rows:
        return [], {"delimiter": delim, "rows": 0, "ragged": []}
    headers = dedupe(rows[0])
    out, ragged = [], []
    for i, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        if len(row) != len(headers):
            ragged.append({"line": i, "expected": len(headers), "got": len(row)})
            row = (row + [""] * len(headers))[: len(headers)]
        out.append({h: coerce(v) for h, v in zip(headers, row)})
    return out, {"delimiter": delim, "rows": len(out), "ragged": ragged}

def json_to_csv(records, delimiter=","):
    if not records:
        return ""
    headers = list(dict.fromkeys(k for r in records for k in r))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=headers, delimiter=delimiter, lineterminator="\n")
    w.writeheader()
    for r in records:
        w.writerow({h: ("" if r.get(h) is None else r.get(h)) for h in headers})
    return buf.getvalue()

def main(argv=None):
    p = argparse.ArgumentParser(description="Convert between CSV and JSON (stdlib only).")
    p.add_argument("path", nargs="?", help="input file; omit to read stdin")
    p.add_argument("--to", choices=["json", "csv"], default="json")
    p.add_argument("--delimiter", default=None)
    p.add_argument("--report", action="store_true", help="print a ragged-row report to stderr")
    a = p.parse_args(argv)
    raw = open(a.path, "rb").read() if a.path else sys.stdin.buffer.read()
    text, _enc = decode(raw)
    if a.to == "json":
        records, meta = csv_to_json(text, a.delimiter)
        if a.report and meta["ragged"]:
            print(f"ragged rows: {json.dumps(meta['ragged'])}", file=sys.stderr)
        print(json.dumps(records, indent=2, ensure_ascii=False))
    else:
        print(json_to_csv(json.loads(text), a.delimiter or ","), end="")
    return 0

if __name__ == "__main__":
    sys.exit(main())
