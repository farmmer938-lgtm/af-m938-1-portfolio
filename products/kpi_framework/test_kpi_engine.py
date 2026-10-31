"""Tests for the Zero Bureaucracy KPI engine."""
import json

from kpi_engine import load_library, normalize, score

LIB = load_library()


def test_library_has_12_kpis():
    assert len(LIB["kpis"]) == 12


def test_library_has_5_dimensions():
    assert set(LIB["dimensions"]) == {"Speed", "Effort", "Automation", "Duplication", "Friction"}


def test_every_kpi_has_definition_formula_unit_benchmark():
    for k in LIB["kpis"]:
        assert k["definition"] and k["formula"] and k["unit"]
        assert "best" in k["benchmark"] and "worst" in k["benchmark"]


def test_normalize_lower_better_best_is_100():
    kpi = next(k for k in LIB["kpis"] if k["id"] == "SP1")
    assert normalize(kpi, 4) == 100.0
    assert normalize(kpi, 120) == 0.0


def test_normalize_higher_better_best_is_100():
    kpi = next(k for k in LIB["kpis"] if k["id"] == "AU1")
    assert normalize(kpi, 95) == 100.0
    assert normalize(kpi, 0) == 0.0


def test_normalize_clamps_out_of_range():
    kpi = next(k for k in LIB["kpis"] if k["id"] == "SP1")
    assert normalize(kpi, 1000) == 0.0
    assert normalize(kpi, -5) == 100.0


def test_normalize_midpoint():
    kpi = next(k for k in LIB["kpis"] if k["id"] == "SP1")
    assert normalize(kpi, 62) == 50.0


def test_score_all_best_is_100():
    best = {k["id"]: k["benchmark"]["best"] for k in LIB["kpis"]}
    result = score(best, LIB)
    assert result["overall_score"] == 100.0


def test_score_all_worst_is_0():
    worst = {k["id"]: k["benchmark"]["worst"] for k in LIB["kpis"]}
    result = score(worst, LIB)
    assert result["overall_score"] == 0.0


def test_score_reports_per_dimension():
    result = score({"SP1": 4, "AU1": 95}, LIB)
    assert result["dimensions"]["Speed"] == 100.0
    assert result["dimensions"]["Automation"] == 100.0


def test_score_weighting_changes_overall():
    m = {"SP1": 62, "AU1": 95}  # Speed 50, Automation 100
    unweighted = score(m, LIB)
    weighted = score(m, LIB, weights={"Speed": 3, "Automation": 1})
    assert unweighted["overall_score"] == 75.0
    assert weighted["overall_score"] == 62.5


def test_score_unknown_kpi_raises():
    import pytest

    with pytest.raises(KeyError):
        score({"NOPE": 1}, LIB)


def test_engine_cli_reads_stdin():
    import subprocess
    import sys

    payload = json.dumps({"measurements": {"SP1": 4, "AU1": 95}})
    out = subprocess.run([sys.executable, "kpi_engine.py"], input=payload,
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out)["overall_score"] == 100.0
