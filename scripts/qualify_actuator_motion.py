# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Verify all three admitted example classes against forced oscillator motion."""
import json
import math
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from python.spike_core.actuator_motion import simulate_actuator_motion


def qualification_report():
    template = json.loads((ROOT / "examples/actuator/voice-coil-motion.json").read_text())
    m, c, k, t = .05, 1., 100., .02
    alpha = c / (2*m)
    omega = math.sqrt(k/m-alpha**2)
    # Independently derived step-force response, zero initial displacement/velocity.
    scale = (1-math.exp(-alpha*t)*(math.cos(omega*t)+alpha/omega*math.sin(omega*t))) / k
    cases = []
    for path in sorted((ROOT / "examples/actuator").glob("*-force-map.json")):
        request = dict(template, force_map=json.loads(path.read_text()))
        result = simulate_actuator_motion(request)
        expected = request["force_map"]["force_n"][0] * scale
        error = abs(result["position_m"][-1] - expected)
        balance = abs(result["energy_balance_residual_j"])
        relative_error = error / abs(expected)
        energy_scale = max(abs(result[key]) for key in ("initial_mechanical_energy_j",
            "final_mechanical_energy_j", "midpoint_actuator_work_j", "damping_dissipation_j"))
        relative_balance = balance / energy_scale
        passed = (result["termination"] == "duration_reached" and error < 1e-8 and balance < 1e-12
                  and relative_error < 1e-4 and relative_balance < 1e-8)
        cases.append({"kind": request["force_map"]["kind"], "pass": passed,
                      "expected_displacement_m": expected, "absolute_error_m": error,
                      "displacement_limit_m": 1e-8, "energy_balance_limit_j": 1e-12,
                      "relative_displacement_error": relative_error, "relative_displacement_limit": 1e-4,
                      "relative_energy_residual": relative_balance, "relative_energy_limit": 1e-8,
                      "request": request, "result": result})
    return {"contract": "spike/actuator-motion-verification/v1",
            "status": "pass" if len(cases) == 3 and all(c["pass"] for c in cases) else "fail",
            "runtime": {"python": platform.python_version()}, "cases": cases,
            "verified_scope": "Fixed-excitation supplied-map mechanics for the three constant-force examples",
            "production_qualified": False}


if __name__ == "__main__":
    report = qualification_report()
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    raise SystemExit(0 if report["status"] == "pass" else 1)
