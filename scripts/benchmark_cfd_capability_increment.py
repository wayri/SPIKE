#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Retain actual coupled-equation and reconstructed-flow benchmark evidence.

Synthetic equation verification only: this does not qualify CAD aerodynamics,
engineering turbulence, CHT feedback, a propeller or a graphical viewer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import unittest

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODULES = ("test_enclosure_rans_research", "test_enclosure_rans_independent",
           "test_enclosure_flow_analysis")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    paths = list((ROOT / "python/spike_core").glob("enclosure*.py"))
    paths += list((ROOT / "tests/python").glob("test_enclosure*.py"))
    paths.append(Path(__file__))
    return {path.relative_to(ROOT).as_posix(): digest(path)
            for path in sorted(set(paths))}


def numeric_json(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Unsupported benchmark value {type(value).__name__}")


def retain(output, name, value):
    path = output / f"{name}.json"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False, default=numeric_json)
        stream.write("\n")
    return {"file": path.name, "sha256": digest(path)}


def coupled_and_trace(output):
    from python.spike_core.enclosure_flow_analysis import analyze_enclosure_flow
    from python.spike_core.enclosure_rans_research import solve_enclosure_rans_research
    from tests.python.test_enclosure_rans_research import fixture, velocity_error

    request, exact_q = fixture(12)
    artifacts = {"coupled_request": retain(output, "coupled-request", request)}
    replay_request = json.loads((output / artifacts["coupled_request"]["file"]).read_text(encoding="utf-8"))
    result = solve_enclosure_rans_research(replay_request)
    artifacts["coupled_result"] = retain(output, "coupled-result", result)
    if result["status"] != "completed":
        raise AssertionError("Retained coupled research case failed")
    diagnostics = result["diagnostics"]
    if diagnostics["joint_relative_residual"] > 1e-9:
        raise AssertionError("Retained joint residual exceeds unchanged gate")
    tracing = {
        "contract": "spike/enclosure-flow-analysis/v1",
        "grid": request["grid"], "fluid_mask": np.ones((12, 12, 12), bool),
        "face_velocity_m_s": result["fields"]["face_velocity_m_s"],
        "velocity_reference_frame": "stationary",
        "probes_m": [[.4375, .4375, .4375], [.5625, .5625, .5625]],
        "seed_points_m": [[.4375, .4375, .4375], [.5625, .5625, .5625]],
        "controls": {"max_time_s": 100., "max_step_s": 1.,
                     "max_points_per_streamline": 300, "max_cell_events": 500,
                     "max_total_points": 600, "max_output_bytes": 1024*1024,
                     "max_runtime_s": 10.},
    }
    artifacts["trace_request"] = retain(output, "trace-request", tracing)
    replay_trace = json.loads((output / artifacts["trace_request"]["file"]).read_text(encoding="utf-8"))
    trace = analyze_enclosure_flow(replay_trace)
    artifacts["trace_result"] = retain(output, "trace-result", trace)
    if trace["status"] != "completed":
        raise AssertionError("Retained reconstructed-flow case failed")
    for path in trace["streamlines"]:
        if (len(path["points"]) < 10 or path["cell_events"] < 1
                or path["arclength_m"] <= .05
                or path["termination_reason"] != "time_limit"):
            raise AssertionError("Retained trace did not meet predeclared traversal budget")
    return {"artifacts": artifacts,
            "coupled_mean_velocity_relative_l2": velocity_error(request, result),
            "coupled_q_relative_l2": float(np.linalg.norm(
                np.asarray(result["fields"]["nu_tilde_m2_s"])-exact_q)/np.linalg.norm(exact_q)),
            "coupled_diagnostics": diagnostics,
            "trace_status": trace["status"],
            "trace_summary": [{"points": len(path["points"]),
                               "cell_events": path["cell_events"],
                               "arclength_m": path["arclength_m"],
                               "termination_reason": path["termination_reason"]}
                              for path in trace["streamlines"]],
            "interpretation": "Steady reconstructed trace parameter is not measured fluid age"}


def run(output):
    output = output.resolve()
    output.mkdir(parents=True)
    before = sources()
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        [f"tests.python.{name}" for name in MODULES])
    with (output / "assertions.log").open("x", encoding="utf-8") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    passed = bool(result.testsRun and result.wasSuccessful() and not result.skipped
                  and not result.expectedFailures and not result.unexpectedSuccesses)
    case, issue = None, None
    if passed:
        try:
            case = coupled_and_trace(output)
        except (AssertionError, ValueError, TypeError, ArithmeticError) as exc:
            passed, issue = False, str(exc)
    unchanged = before == sources()
    receipt = {"contract": "spike/cfd-capability-increment-benchmark/v1",
               "passed": passed and unchanged, "production_qualified": False,
               "environment": {"python": sys.version, "platform": platform.platform(),
                               "numpy": np.__version__, "scipy": scipy.__version__},
               "source_sha256": before, "sources_unchanged": unchanged,
               "tests_run": result.testsRun,
               "failures": [str(test) for test, _ in result.failures],
               "errors": [str(test) for test, _ in result.errors],
               "skipped": [str(test) for test, _ in result.skipped],
               "expected_failures": [str(test) for test, _ in result.expectedFailures],
               "unexpected_successes": [str(test) for test in result.unexpectedSuccesses],
               "assertions_sha256": digest(output / "assertions.log"),
               "elapsed_seconds": time.perf_counter()-started, "case": case, "issue": issue,
               "limitations": ["Manufactured closed-box equations, original molecular Re<=20",
                               "Reconstructed supplied fields, not independent PDE validation",
                               "No engineering turbulence, curved CAD, propellers or new UI"]}
    retain(output, "receipt", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh evidence directory")
    receipt = run(parser.parse_args().output)
    print(json.dumps({key: receipt[key] for key in
                      ("passed", "tests_run", "sources_unchanged", "elapsed_seconds", "issue")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
