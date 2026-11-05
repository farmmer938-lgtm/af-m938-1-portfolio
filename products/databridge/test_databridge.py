import json

from databridge import csv_to_json, infer, json_to_csv, sniff_delimiter


def test_sniff_comma():
    assert sniff_delimiter("a,b,c\n1,2,3") == ","


def test_sniff_semicolon():
    assert sniff_delimiter("a;b;c\n1;2;3") == ";"


def test_sniff_tab():
    assert sniff_delimiter("a\tb\tc\n1\t2\t3") == "\t"


def test_sniff_pipe():
    assert sniff_delimiter("a|b|c\n1|2|3") == "|"


def test_infer_types():
    assert infer("42") == 42
    assert infer("3.14") == 3.14
    assert infer("true") is True
    assert infer("False") is False
    assert infer("hello") == "hello"
    assert infer("") == ""


def test_basic_csv_to_json():
    rows = csv_to_json("name,age\nAnn,30\nBob,25")
    assert rows == [{"name": "Ann", "age": 30}, {"name": "Bob", "age": 25}]


def test_explicit_delimiter_override():
    rows = csv_to_json("a;b\n1;2", delimiter=";")
    assert rows == [{"a": 1, "b": 2}]


def test_quoted_embedded_comma():
    rows = csv_to_json('name,note\nAnn,"a,b"')
    assert rows[0]["note"] == "a,b"


def test_quoted_embedded_newline():
    rows = csv_to_json('name,note\nAnn,"line1\nline2"')
    assert rows[0]["note"] == "line1\nline2"


def test_rfc4180_escaping_roundtrip():
    data = [{"a": 'he said "hi", ok', "b": "x,y"}]
    out = json_to_csv(data)
    assert csv_to_json(out) == data


def test_json_to_csv_key_union():
    out = json_to_csv([{"a": 1}, {"b": 2}])
    lines = out.strip().split("\n")
    assert lines[0] == "a,b"
    assert lines[1] == "1,"
    assert lines[2] == ",2"


def test_missing_columns_filled():
    rows = csv_to_json("a,b,c\n1,2")
    assert rows[0]["c"] == ""


def test_unicode_roundtrip():
    data = [{"ชื่อ": "มานะ", "ราคา": 271}]
    assert csv_to_json(json_to_csv(data)) == data


def test_blank_rows_skipped():
    rows = csv_to_json("a,b\n1,2\n\n3,4\n")
    assert len(rows) == 2


def test_empty_input():
    assert csv_to_json("") == []
    assert json_to_csv([]) == ""


def test_none_becomes_empty_cell():
    out = json_to_csv([{"a": None, "b": 1}])
    assert out.strip().split("\n")[1] == ",1"


def test_headers_are_trimmed():
    rows = csv_to_json(" a , b \n1,2")
    assert rows == [{"a": 1, "b": 2}]
