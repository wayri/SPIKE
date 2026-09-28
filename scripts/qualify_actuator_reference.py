# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Run and retain actuator map analytical verification and refinement evidence."""
from __future__ import annotations
import json
from pathlib import Path
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from python.spike_core.actuator_force_map import CONTRACT, analyze_force_map


def qualification_report():
    records = []
    criteria = []
    for kind in ("reluctance", "electrostatic"):
        errors = []
        for count in (17, 33, 65, 129):
            x = np.linspace(0, .001, count)
            gap = .004 - x
            if kind == "reluctance":
                # Independently evaluated air-gap stress B^2/(2*mu0).
                permeability = 4e-7 * np.pi
                field = permeability * 100 * 2 / gap
                pressure = field**2 / (2 * permeability)
                coenergy = .5 * permeability * 1e-4 * (100 * 2)**2 / gap
                excitation = {"current_a": 2}
            else:
                # Independent electric stress eps*E^2/2 at fixed 100 V.
                permittivity = 8.8541878128e-12
                field = 100 / gap
                pressure = permittivity * field**2 / 2
                coenergy = .5 * permittivity * 1e-4 * 100**2 / gap
                excitation = {"voltage_v": 100}
            request = {"contract": CONTRACT, "kind": kind, "position_m": x.tolist(),
                       "force_n": (pressure * 1e-4).tolist(), "coenergy_j": coenergy.tolist(),
                       "fixed_excitation": excitation, "relative_tolerance": .001,
                       "absolute_force_tolerance_n": 1e-12,
                       "provenance": "Original uniform air-gap stress vs coenergy oracle; no measured data"}
            result = analyze_force_map(request)
            error = result["checks"]["coenergy_gradient"]["maximum_error_n"]
            errors.append(error)
            records.append({"kind": kind, "samples": count, "result": result})
        ratios = [a/b for a, b in zip(errors, errors[1:])]
        criteria.append({"id": kind + "_stroke_refinement", "pass": all(r >= 3.8 for r in ratios),
                         "error_ratios": ratios, "minimum_ratio": 3.8,
                         "derivative_errors_n": errors})
    for file in sorted((ROOT / "examples/actuator").glob("*-force-map.json")):
        request = json.loads(file.read_text(encoding="utf-8"))
        result = analyze_force_map(request)
        records.append({"example": file.name, "result": result})
        criteria.append({"id": file.stem, "pass": result["status"] == "consistent"})
        bad = dict(request, force_n=[-v for v in request["force_n"]])
        rejected = analyze_force_map(bad)
        criteria.append({"id": file.stem + "_wrong_sign_rejected",
                         "pass": rejected["status"] == "inconsistent",
                         "result": rejected})
    criteria.append({"id": "all_refined_maps_consistent",
                     "pass": all(r["result"]["status"] == "consistent" for r in records)})
    return {"contract": "spike/actuator-reference-verification/v1",
            "status": "pass" if all(c["pass"] for c in criteria) else "fail",
            "runtime": {"python": platform.python_version(), "numpy": np.__version__},
            "verified_scope": "Supplied conservative force/coenergy map numerical review only",
            "production_qualified": False, "criteria": criteria, "runs": records,
            "limitations": ["Uniform-field oracles do not test a geometry-to-field implementation.",
                            "Stroke-grid convergence is not finite-element mesh convergence.",
                            "No hysteresis, motion, PM demagnetization, pull-in or measured correlation."]}


if __name__ == "__main__":
    report = qualification_report()
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    raise SystemExit(0 if report["status"] == "pass" else 1)
