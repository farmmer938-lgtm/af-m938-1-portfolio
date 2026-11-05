from kpi_engine import load_library, normalise, score

LIB = load_library()


def test_library_shape():
    assert len(LIB["kpis"]) == 12
    assert set(LIB["dimensions"]) == {"speed", "effort", "automation", "duplication", "friction"}
    for k in LIB["kpis"]:
        assert {"id", "name", "dimension", "unit", "formula", "direction", "weight", "benchmark"} <= set(k)
        assert k["direction"] in {"higher", "lower"}
        assert k["benchmark"]["best"] != k["benchmark"]["worst"]


def test_normalise_higher():
    assert normalise(10, best=10, worst=0, direction="higher") == 1.0
    assert normalise(0, best=10, worst=0, direction="higher") == 0.0
    assert normalise(5, best=10, worst=0, direction="higher") == 0.5


def test_normalise_lower():
    assert normalise(1, best=1, worst=72, direction="lower") == 1.0
    assert normalise(72, best=1, worst=72, direction="lower") == 0.0


def test_normalise_clamps():
    assert normalise(999, best=10, worst=0, direction="higher") == 1.0
    assert normalise(-5, best=10, worst=0, direction="higher") == 0.0
    assert normalise(1, best=5, worst=5, direction="lower") == 1.0


def test_best_all_scores_100():
    best = {k["id"]: k["benchmark"]["best"] for k in LIB["kpis"]}
    assert score(best)["score"] == 100.0


def test_worst_all_scores_0():
    worst = {k["id"]: k["benchmark"]["worst"] for k in LIB["kpis"]}
    assert score(worst)["score"] == 0.0


def test_weighting_shifts_score():
    low_w = score({"cycle_time": 72, "automation_ratio": 0.95})["score"]
    # automation_ratio has weight 1.0; cycle_time also 1.0 -> equal pull
    assert 0 < low_w < 100


def test_dimension_breakdown():
    res = score({"cycle_time": 1, "steps_per_task": 1})
    assert set(res["dimensions"]) == {"speed", "effort"}
    assert res["dimensions"]["speed"] == 100.0


def test_unknown_kpi_rejected():
    try:
        score({"not_a_kpi": 1})
    except KeyError as e:
        assert "not_a_kpi" in str(e)
    else:
        raise AssertionError("expected KeyError")


def test_partial_measurements_allowed():
    res = score({"cycle_time": 6})
    assert res["breakdown"][0]["id"] == "cycle_time"
    assert res["breakdown"][0]["normalised"] == round((72 - 6) / (72 - 1), 4)


def test_direction_respected():
    # higher-is-better: more automation -> higher normalised value
    a = score({"automation_ratio": 0.9})["score"]
    b = score({"automation_ratio": 0.2})["score"]
    assert a > b


def test_cli_smoke():
    import json
    import subprocess
    import sys

    out = subprocess.check_output([sys.executable, "kpi_engine.py", json.dumps({"cycle_time": 6})])
    assert json.loads(out)["score"] > 0


def test_library_is_configurable():
    lib = load_library()
    lib["kpis"][0]["weight"] = 0.0
    res = score({"cycle_time": 6, "steps_per_task": 1}, library=lib)
    assert res["dimensions"]["speed"] == 0.0
