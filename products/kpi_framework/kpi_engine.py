#!/usr/bin/env python3
"""Zero Bureaucracy KPI scoring engine.

Reads the KPI library, normalizes each measured KPI to 0-100, and aggregates a
weighted score per dimension and overall. Platform-ready: the library and the
weights are data, not code.
"""
from __future__ import annotations

import json
import os
from typing import Any

LIBRARY = os.path.join(os.path.dirname(__file__), "kpi_library.json")


def load_library(path: str = LIBRARY) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def normalize(kpi: dict[str, Any], value: float) -> float:
    """Map a raw measurement to 0-100 where 100 is best, clamped."""
    best = kpi["benchmark"]["best"]
    worst = kpi["benchmark"]["worst"]
    if best == worst:
        return 100.0
    if kpi["direction"] == "higher_better":
        score = (value - worst) / (best - worst) * 100
    else:
        score = (worst - value) / (worst - best) * 100
    return max(0.0, min(100.0, score))


def score(measurements: dict[str, float], library: dict[str, Any] | None = None,
          weights: dict[str, float] | None = None) -> dict[str, Any]:
    lib = library or load_library()
    kpis = {k["id"]: k for k in lib["kpis"]}
    weights = weights or {}
    per_kpi = {}
    for kid, value in measurements.items():
        if kid not in kpis:
            raise KeyError(f"unknown KPI id: {kid}")
        per_kpi[kid] = {
            "value": value,
            "normalized": round(normalize(kpis[kid], value), 2),
            "dimension": kpis[kid]["dimension"],
        }

    by_dim: dict[str, list[float]] = {}
    for item in per_kpi.values():
        by_dim.setdefault(item["dimension"], []).append(item["normalized"])
    dimensions = {d: round(sum(v) / len(v), 2) for d, v in by_dim.items()}

    if weights:
        num = sum(dimensions[d] * weights.get(d, 0) for d in dimensions)
        den = sum(weights.get(d, 0) for d in dimensions) or 1
        overall = round(num / den, 2)
    else:
        overall = round(sum(dimensions.values()) / len(dimensions), 2) if dimensions else 0.0

    return {"overall_score": overall, "dimensions": dimensions, "kpis": per_kpi}


def main() -> None:
    import sys

    payload = json.load(sys.stdin)
    print(json.dumps(score(payload.get("measurements", {}),
                           weights=payload.get("weights")), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
