"""Test suite for csvjson — 8 cases covering both directions and the edge cases in the brief."""
import json
import pytest
import csvjson


def test_sniff_semicolon_and_comma():
    assert csvjson.sniff("a;b;c\n1;2;3\n4;5;6") == ";"
    assert csvjson.sniff("a,b,c\n1,2,3\n4,5,6") == ","
    assert csvjson.sniff("a\tb\tc\n1\t2\t3") == "\t"


def test_sniff_ignores_delimiter_inside_quotes():
    text = 'a,b\n"x;y",2\n"p;q",3'
    assert csvjson.sniff(text) == ","


def test_cp1252_fallback_decodes_bytes():
    raw = "name,city\nAndr\xe9,Z\xfcrich".encode("cp1252")
    text, enc = csvjson.decode(raw)
    assert enc == "cp1252"
    records, _ = csvjson.csv_to_json(text)
    assert records == [{"name": "André", "city": "Zürich"}]


def test_duplicate_headers_are_renamed():
    text = "id,name,name,name\n1,a,b,c"
    records, _ = csvjson.csv_to_json(text)
    assert list(records[0].keys()) == ["id", "name", "name_2", "name_3"]
    assert records[0]["name_2"] == "b"


def test_ragged_rows_are_reported_and_padded():
    text = "a,b,c\n1,2,3\n4,5\n6,7,8,9"
    records, meta = csvjson.csv_to_json(text)
    assert [r["line"] for r in meta["ragged"]] == [3, 4]
    assert records[1] == {"a": 4, "b": 5, "c": None}
    assert records[2] == {"a": 6, "b": 7, "c": 8}


def test_type_coercion_and_empty_cells():
    text = "sku;price;in_stock\nA1;4.50;true\nB2;;false"
    records, _ = csvjson.csv_to_json(text)
    assert records[0]["price"] == 4.5
    assert records[1]["price"] is None
    assert records[0]["sku"] == "A1"


def test_json_to_csv_both_directions_roundtrip():
    original = [{"sku": "A1", "name": "Widget, small", "price": 4.5},
                {"sku": "B2", "name": "Gadget", "price": 12}]
    text = csvjson.json_to_csv(original, ";")
    assert text.splitlines()[0] == "sku;name;price"
    back, _ = csvjson.csv_to_json(text)
    assert back == original


def test_cli_exit_zero_and_valid_json(tmp_path, capsys):
    f = tmp_path / "in.csv"
    f.write_text("a;b\n1;2\n3;4", encoding="utf-8")
    rc = csvjson.main([str(f)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
