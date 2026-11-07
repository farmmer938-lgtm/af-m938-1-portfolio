"""Tests for the CSV <-> JSON toolkit. Real files on disk, no mocks."""
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import csv_to_json as c2j  # noqa: E402
import json_to_csv as j2c  # noqa: E402


def test_basic_csv_to_json():
    rows = c2j.convert("a,b\n1,2\n3,4\n")
    assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


def test_delimiter_sniffed_semicolon():
    rows = c2j.convert("a;b\n1;2\n")
    assert rows == [{"a": "1", "b": "2"}]


def test_quoted_field_with_delimiter_and_newline():
    rows = c2j.convert('name,note\n"Smith, J","line1\nline2"\n')
    assert rows[0]["name"] == "Smith, J"
    assert rows[0]["note"] == "line1\nline2"


def test_duplicate_headers_are_kept():
    rows = c2j.convert("id,id,id\n1,2,3\n")
    assert rows[0] == {"id": "1", "id_2": "2", "id_3": "3"}


def test_ragged_and_blank_rows():
    rows = c2j.convert("a,b,c\n1,2\n\n3,4,5,6\n")
    assert rows[0] == {"a": "1", "b": "2", "c": ""}
    assert rows[1] == {"a": "3", "b": "4", "c": "5"}  # extra cell ignored


def test_bom_and_types():
    rows = c2j.convert(c2j.decode("\ufeffa,b\n1,x\n".encode("utf-8")), types=True)
    assert rows == [{"a": 1, "b": "x"}]


def test_type_inference_conservative():
    rows = c2j.convert("n,f,flag,empty\n42,3.5,true,\n", types=True)
    assert rows[0]["n"] == 42 and isinstance(rows[0]["n"], int)
    assert rows[0]["f"] == 3.5
    assert rows[0]["flag"] is True
    assert rows[0]["empty"] == ""


def test_json_to_csv_missing_keys():
    out = j2c.convert([{"a": 1, "b": 2}, {"a": 3}])
    lines = out.strip().splitlines()
    assert lines[0] == "a,b"
    assert lines[1] == "1,2"
    assert lines[2] == "3,"


def test_json_to_csv_nested_and_quoting():
    out = j2c.convert([{"a": "x,y", "meta": {"k": 1}}])
    parsed = list(csv.DictReader(io.StringIO(out)))
    assert parsed[0]["a"] == "x,y"
    assert json.loads(parsed[0]["meta"]) == {"k": 1}


def test_json_to_csv_pinned_columns():
    out = j2c.convert([{"a": 1, "b": 2}], columns=["b", "a", "c"])
    assert out.splitlines()[0] == "b,a,c"
    assert out.splitlines()[1] == "2,1,"


def test_cli_roundtrip(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("id,name\n1,Ann\n2,Bo\n", encoding="utf-8")
    mid = tmp_path / "mid.json"
    subprocess.run([sys.executable, str(HERE / "csv_to_json.py"), str(src), "-o", str(mid)], check=True)
    data = json.loads(mid.read_text(encoding="utf-8"))
    assert data == [{"id": "1", "name": "Ann"}, {"id": "2", "name": "Bo"}]
    back = tmp_path / "back.csv"
    subprocess.run([sys.executable, str(HERE / "json_to_csv.py"), str(mid), "-o", str(back)], check=True)
    assert back.read_text(encoding="utf-8").strip().splitlines()[0] == "id,name"
