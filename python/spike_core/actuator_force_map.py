# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded actuator force/coenergy review, not a geometry-to-field solver.

At fixed current (magnetic) or voltage (electrostatic), F = dW'/dx.
Positive force acts toward increasing declared displacement. See
docs/ACTUATOR_FORCE_MAP.md for derivation, evidence and validity boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

CONTRACT = "spike/actuator-force-map/v1"
KINDS = {"reluctance", "permanent_magnet", "electrostatic"}


def analyze_force_map(request: dict) -> dict:
    required = {"contract", "kind", "position_m", "force_n", "coenergy_j",
                "fixed_excitation", "provenance", "relative_tolerance", "absolute_force_tolerance_n"}
    optional = {"moving_mass_kg"}
    if not isinstance(request, dict) or set(request) - required - optional or required - set(request):
        raise ValueError("Force map has missing or unknown fields.")
    if request["contract"] != CONTRACT or not isinstance(request["kind"], str) or request["kind"] not in KINDS:
        raise ValueError("Unsupported force-map contract or actuator kind.")
    excitation = request["fixed_excitation"]
    units = "voltage_v" if request["kind"] == "electrostatic" else "current_a"
    if not isinstance(excitation, dict) or set(excitation) != {units}:
        raise ValueError(f"Fixed excitation requires only {units}.")
    def number(value, label, minimum=None, maximum=None):
        if type(value) not in (int, float):
            raise ValueError(f"{label} must be a finite number.")
        try:
            value = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be a finite number.") from exc
        if not np.isfinite(value):
            raise ValueError(f"{label} must be a finite number.")
        if minimum is not None and value < minimum or maximum is not None and value > maximum:
            raise ValueError(f"{label} outside bounds.")
        return float(value)
    number(excitation[units], units)
    tolerance = number(request["relative_tolerance"], "relative_tolerance", 0, 0.1)
    absolute = number(request["absolute_force_tolerance_n"], "absolute_force_tolerance_n", 0)
    provenance = request["provenance"]
    if not isinstance(provenance, str) or not provenance.strip() or len(provenance) > 2048:
        raise ValueError("Nonempty bounded provenance is required.")
    arrays = []
    for field in ("position_m", "force_n", "coenergy_j"):
        raw = request[field]
        if not isinstance(raw, list) or not 5 <= len(raw) <= 4097:
            raise ValueError(f"{field} needs 5..4097 samples.")
        arrays.append(np.array([number(v, field) for v in raw]))
    x, force, coenergy = arrays
    if len(x) != len(force) or len(x) != len(coenergy):
        raise ValueError("Force-map arrays must have equal lengths.")
    if np.any(x[1:] <= x[:-1]):
        raise ValueError("Positions must be strictly increasing.")
    mass = None
    if "moving_mass_kg" in request:
        mass = number(request["moving_mass_kg"], "moving_mass_kg", 1e-12)
    # Quadratic three-point differentiation on nonuniform grids. Endpoints
    # have one-sided truncation error and are reported, not silently omitted.
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            derivative = np.gradient(coenergy, x, edge_order=2)
            error = np.abs(force - derivative)
            scale = max(float(np.max(np.abs(force))), float(np.max(np.abs(derivative))))
            force_limit = absolute + tolerance * scale
            work = float(np.sum(0.5 * (force[1:] + force[:-1]) * np.diff(x)))
            change = float(coenergy[-1] - coenergy[0])
            work_limit = absolute * float(x[-1] - x[0]) + tolerance * max(abs(work), abs(change))
            stroke = float(x[-1] - x[0])
            ripple = float(np.ptp(force))
            force_per_mass = None if mass is None else float(np.max(np.abs(force))) / mass
            values = np.r_[derivative, error, scale, force_limit, work, change, work_limit,
                           stroke, ripple, 0 if force_per_mass is None else force_per_mass]
            if not np.all(np.isfinite(values)):
                raise FloatingPointError()
        except FloatingPointError as exc:
            raise ValueError("Force map exceeds numerical range or has ill-scaled spacing.") from exc
    checks = {
        "coenergy_gradient": {"passed": bool(np.max(error) <= force_limit),
                              "maximum_error_n": float(np.max(error)), "limit_n": force_limit},
        "virtual_work": {"passed": bool(abs(work - change) <= work_limit),
                         "integrated_force_j": work, "coenergy_change_j": change,
                         "error_j": abs(work - change), "limit_j": work_limit},
    }
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()
    return {"contract": "spike/actuator-force-map-result/v1", "request_sha256": digest,
            "status": "consistent" if all(c["passed"] for c in checks.values()) else "inconsistent",
            "production_qualified": False, "kind": request["kind"], "checks": checks,
            "stroke_m": stroke, "minimum_force_n": float(np.min(force)),
            "maximum_force_n": float(np.max(force)), "peak_to_peak_force_n": ripple,
            "peak_force_per_moving_mass_n_per_kg": force_per_mass,
            "coenergy_gradient_n": derivative.tolist(), "provenance": provenance,
            "limitations": ["Input force/coenergy maps are not generated or independently authenticated here.",
                            "Fixed-excitation, conservative quasi-static virtual work only; no hysteresis, eddy loss or motion dynamics.",
                            "Map differentiation/trapezoidal integration errors require stroke-grid convergence.",
                            "Agreement is consistency, not independent field or measured validation.",
                            "Force ripple is cogging only for an explicitly zero-current permanent-magnet map."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    with args.request.open("rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        parser.error("Request exceeds 8 MiB.")
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"Duplicate key: {key}")
            value[key] = item
        return value
    result = analyze_force_map(json.loads(raw, object_pairs_hook=pairs))
    args.result.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0 if result["status"] == "consistent" else 1


if __name__ == "__main__":
    raise SystemExit(main())
