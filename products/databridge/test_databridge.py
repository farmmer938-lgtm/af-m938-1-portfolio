"""Tests for databridge CSV<->JSON conversion (>=14 cases)."""
import json

import pytest

from databridge import csv_to_json, json_to_csv


def test_basic_csv_to_json():
    rows = json.loads(csv_to_json("a,b\n1,2\n3,4\n"))
    assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


def test_empty_csv_returns_empty_array():
    assert csv_to_json("") == "[]"
    assert csv_to_json("   \n") == "[]"


def test_semicolon_delimiter_sniffed():
    rows = json.loads(csv_to_json("a;b\n1;2\n"))
    assert rows == [{"a": "1", "b": "2"}]


def test_tab_delimiter_sniffed():
    rows = json.loads(csv_to_json("a\tb\n1\t2\n"))
    assert rows == [{"a": "1", "b": "2"}]


def test_explicit_delimiter_overrides_sniff():
    rows = json.loads(csv_to_json("a|b\n1|2\n", delimiter="|"))
    assert rows == [{"a": "1", "b": "2"}]


def test_quoted_field_with_delimiter():
    rows = json.loads(csv_to_json('name,note\n"a,b",ok\n'))
    assert rows == [{"name": "a,b", "note": "ok"}]


def test_embedded_newline_in_quotes():
    rows = json.loads(csv_to_json('name,note\n"line1\nline2",ok\n'))
    assert rows[0]["note"] == "ok"
    assert rows[0]["name"] == "line1\nline2"


def test_missing_trailing_column_becomes_none():
    rows = json.loads(csv_to_json("a,b\n1\n"))
    assert rows == [{"a": "1", "b": None}]


def test_unicode_preserved():
    rows = json.loads(csv_to_json("ชื่อ,ค่า\nทดสอบ,๑๒๓\n"))
    assert rows == [{"ชื่อ": "ทดสอบ", "ค่า": "๑๒๓"}]


def test_basic_json_to_csv():
    out = json_to_csv(json.dumps([{"a": 1, "b": 2}]))
    assert out.splitlines() == ["a,b", "1,2"]


def test_json_to_csv_unions_keys_and_fills_missing():
    out = json_to_csv(json.dumps([{"a": 1}, {"a": 2, "b": 3}]))
    lines = out.splitlines()
    assert lines[0] == "a,b"
    assert lines[1] == "1,"
    assert lines[2] == "2,3"


def test_json_to_csv_escapes_special_characters():
    out = json_to_csv(json.dumps([{"a": "x,y", "b": 'quote "q"'}]))
    lines = out.splitlines()
    assert '"x,y"' in lines[1]
    assert '"quote ""q"""' in lines[1]


def test_json_to_csv_none_becomes_empty():
    out = json_to_csv(json.dumps([{"a": None, "b": "v"}]))
    assert out.splitlines()[1] == ",v"


def test_json_to_csv_rejects_non_array():
    with pytest.raises(ValueError):
        json_to_csv(json.dumps({"a": 1}))


def test_json_to_csv_rejects_non_object_element():
    with pytest.raises(ValueError):
        json_to_csv(json.dumps([1, 2, 3]))


def test_round_trip_preserves_values():
    original = [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
    csv_text = json_to_csv(json.dumps(original))
    back = json.loads(csv_to_json(csv_text))
    assert back == original


def test_json_to_csv_custom_delimiter():
    out = json_to_csv(json.dumps([{"a": 1, "b": 2}]), delimiter=";")
    assert out.splitlines()[0] == "a;b"
