# CSV ↔ JSON Toolkit

Two small, dependency-free Python 3.10+ scripts for converting between CSV and
JSON, built to survive the messy files that real exports produce.

## Files

| File | Purpose |
|---|---|
| `csv_to_json.py` | Read CSV, write JSON (array or NDJSON) |
| `json_to_csv.py` | Read JSON (array of objects), write CSV |
| `tests/test_toolkit.py` | 11 pytest cases covering the edge cases below |

No third-party runtime dependencies. Tests need only `pytest`.

## Why not `csv.DictReader` + `json.dump`?

The naive approach breaks on the files people actually send. This toolkit handles:

* **Delimiter sniffing** — comma, semicolon, tab, pipe (override with `--delimiter`).
* **Encodings** — UTF-8 with/without BOM, UTF-16, cp1252, latin-1 fallback.
* **Quoted fields** containing the delimiter or embedded newlines (RFC 4180).
* **Duplicate header names** — suffixed `id`, `id_2`, `id_3` so no column is dropped.
* **Ragged and blank rows** — short rows padded, blank rows skipped, extra cells ignored.
* **Opt-in type inference** (`--types`) — `int`/`float`/`bool`/`null`, conservative:
  `"007"` stays a string, empty stays `""`.
* **Missing keys on the JSON→CSV side** — filled with empty string, never a crash.
* **Nested values on the JSON→CSV side** — JSON-encoded into the cell, not dropped.
* **Stable column order** — first-seen key order across all objects, or pin with `--columns`.

## Usage

```bash
# CSV -> JSON (array)
python3 csv_to_json.py data.csv -o data.json

# CSV -> NDJSON, force semicolon, infer types
python3 csv_to_json.py data.csv --delimiter ';' --types --ndjson

# stdin
cat data.csv | python3 csv_to_json.py -

# JSON -> CSV
python3 json_to_csv.py data.json -o data.csv

# pin and order the header
python3 json_to_csv.py data.json --columns id,name,email
```

## Tests

```bash
pip install pytest
python3 -m pytest tests/ -q
# 11 passed
```

## License

MIT.
