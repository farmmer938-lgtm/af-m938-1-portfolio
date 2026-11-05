"""Zero-Bureaucracy KPI engine.

Scores measurements against a configurable KPI library and aggregates to a
single 0-100 score. Weights, directions and benchmark ranges come from the
library (data, not code), so the same engine scores any organisation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def load_library(path: str | Path | None = None) -> dict[str, Any]:
    with open(path or HERE / "kpi_library.json", encoding="utf-8") as fh:
        return json.load(fh)


def normalise(value: float, best: float, worst: float, direction: str) -> float:
    """Map a raw measurement to 0..1 where 1 is best.

    ``best``/``worst`` are the ideal and anti-ideal values. Values beyond the
    range clamp to 0 or 1; a flat range (best == worst) scores 1.0.
    """
    if best == worst:
        return 1.0
    if direction == "higher":
        return max(0.0, min(1.0, (value - worst) / (best - worst)))
    return max(0.0, min(1.0, (worst - value) / (worst - best)))


def score(measurements: dict[str, float], library: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score ``measurements`` (kpi id -> raw value) to 0..100 plus a breakdown.

    Unknown KPI ids raise ``KeyError`` so typos never silently vanish.
    """
    lib = library or load_library()
    kpis = {k["id"]: k for k in lib["kpis"]}
    dim_weights = lib.get("dimension_weights", {})

    rows = []
    for kpi_id, value in measurements.items():
        if kpi_id not in kpis:
            raise KeyError(f"unknown KPI: {kpi_id}")
        kpi = kpis[kpi_id]
        n = normalise(value, kpi["benchmark"]["best"], kpi["benchmark"]["worst"], kpi["direction"])
        rows.append({"id": kpi_id, "dimension": kpi["dimension"], "value": value,
                     "normalised": round(n, 4), "weight": kpi["weight"]})

    dims: dict[str, list[float]] = {}
    for r in rows:
        w = r["weight"] * dim_weights.get(r["dimension"], 1.0)
        dims.setdefault(r["dimension"], []).append((r["normalised"], w))

    dim_scores = {}
    for dim, pairs in dims.items():
        tw = sum(w for _, w in pairs) or 1.0
        dim_scores[dim] = sum(n * w for n, w in pairs) / tw

    overall = (sum(dim_scores.values()) / len(dim_scores)) if dim_scores else 0.0
    return {"score": round(overall * 100, 2), "dimensions": {k: round(v * 100, 2) for k, v in dim_scores.items()},
            "breakdown": rows}


if __name__ == "__main__":
    import sys

    data = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {"cycle_time": 6, "automation_ratio": 0.7}
    print(json.dumps(score(data), indent=2))
