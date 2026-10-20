# SPDX-License-Identifier: Apache-2.0
"""Partial PI01-S02 geometry/ownership evidence; never marks the stage done."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.parity_pisi_gate import bound, digest, names
from scripts.parity_finite_contact_gate import SOURCES as FINITE_SOURCES, validate_receipt as validate_finite
from python.spike_core.dc_axial_ownership import compile_axial_ownership
from python.spike_core.dc_land_transition import solve_land_transition
from python.spike_core.dc_land_transition_evidence import validate_land_result

MODULES = ("tests.python.test_dc_axial_ownership", "tests.python.test_dc_axial_resolve",
           "tests.python.test_dc_land_transition", "tests.python.test_dc_land_transition_oracle")
SOURCES = (*FINITE_SOURCES, "scripts/parity_pi01_blockers_gate.py",
    "python/spike_core/dc_axial_ownership.py", "tests/python/test_dc_axial_ownership.py",
    "tests/python/test_dc_axial_resolve.py", "tests/python/test_pi01_blockers_evidence.py",
    "docs/DC_AXIAL_OWNERSHIP.md", "python/spike_core/dc_land_transition.py",
    "python/spike_core/dc_land_transition_input.py", "python/spike_core/dc_land_transition_evidence.py",
    "tests/python/test_dc_land_transition.py", "tests/python/test_dc_land_transition_oracle.py",
    "docs/DC_LAND_TRANSITION.md", "docs/adr/0126-conservative-land-transition-face-patches.md",
    "examples/dc_land_transition/run_land.py", "examples/dc_land_transition/three-patch.request.json")


def suite():
    return unittest.defaultTestLoader.loadTestsFromNames(MODULES)


def validate_receipt(receipt, root=ROOT):
    if (receipt.get("contract") != "spike/pi01-s02-blocker-evidence/v1"
            or receipt.get("stage_id") != "PI01-S02" or receipt.get("status") != "passed"
            or receipt.get("stage_complete") is not False or receipt.get("production_qualified") is not False):
        raise ValueError("PI01 blocker evidence cannot complete or qualify the stage")
    before = receipt.get("sources_before", {})
    if set(before) != set(SOURCES) or before != receipt.get("sources_after"):
        raise ValueError("PI01 blocker source coverage differs or drifted")
    for name, sha in before.items():
        bound(root, name, sha)
    finite = bound(root, receipt.get("finite_evidence"), receipt.get("finite_sha256"))
    validate_finite(json.loads(finite.read_text(encoding="utf-8")), root)
    expected, result = names(suite()), receipt.get("tests", {})
    if (not expected or any("_FailedTest" in name for name in expected)
            or result.get("names") != expected or result.get("run") != len(expected)
            or any(result.get(key) != [] for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes"))):
        raise ValueError("PI01 ownership execution incomplete or failed")
    log = bound(root, receipt.get("log"), receipt.get("log_sha256")).read_text(encoding="utf-8")
    if f"Ran {len(expected)} tests" not in log or not log.rstrip().endswith("OK"):
        raise ValueError("PI01 ownership log incomplete")
    raw = json.loads(bound(root, receipt.get("report"), receipt.get("report_sha256")).read_text(encoding="utf-8"))
    for key in ("imposed_ownership", "fresh_ownership"):
        if raw[key] != compile_axial_ownership(raw[key]["source_request"]):
            raise ValueError("PI01 ownership report is not bound to its supplied geometry")
    for key, reference_key in (("fresh_result", "gap_resistance_ohm"),
                               ("center_span_result", "original_center_span_resistance_ohm")):
        result = raw[key]
        expected_r = sum(row[reference_key] for row in raw["fresh_ownership"]["segments"])
        if (result["production_qualified"] is not False or result["model_status"] != "experimental"
                or result["current_density_observable"]["complete_physical_volume"] is not False
                or not abs(result["resistance_ohm"]/expected_r-1) < 1e-9
                or not abs(result["dissipation_w_at_one_ampere"]/expected_r-1) < 1e-9):
            raise ValueError("PI01 fresh solve resistance/work/scope differs")
    validate_land_report(raw)


def validate_land_report(raw):
    from tests.python.test_dc_land_transition_oracle import same_face_request, same_face_series_reference
    demo = json.loads((ROOT/"examples/dc_land_transition/three-patch.request.json").read_text())
    require_demo = raw["land_transition"]["source_request"] == demo
    if not require_demo:
        raise ValueError("Land example input differs")
    validate_land_result(raw["land_transition"])
    levels = raw["land_refinement"]
    if len(levels) != 3:
        raise ValueError("Land refinement is incomplete")
    partial, tail = same_face_series_reference()
    errors = []
    for n, result in zip((4, 8, 16), levels):
        if result["source_request"] != same_face_request(n):
            raise ValueError("Land refinement order/support differs")
        validate_land_result(result)
        errors.append(max(abs(result["joule_heat_w"]/reference-1) for reference in (partial, partial+tail)))
    if not errors[-1] < .02 or not errors[-1] < errors[0]:
        raise ValueError("Independent continuum land refinement failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "log", "report", "finite-evidence"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    validate_finite(json.loads(args.finite_evidence.read_text(encoding="utf-8")))
    paths = (args.output, args.log, args.report)
    if len({p.resolve() for p in paths}) != 3:
        parser.error("Evidence outputs must be distinct")
    for path in paths:
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error("Choose fresh repository output paths")
        path.parent.mkdir(parents=True, exist_ok=True)
    before = {name: digest(ROOT/name) for name in SOURCES}
    tests = suite(); expected = names(tests); stream = io.StringIO()
    executed = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding="utf-8")
    from tests.python.test_dc_axial_ownership import explicit_stack
    from tests.python.test_dc_axial_resolve import solve_stack
    from tests.python.test_dc_land_transition_oracle import same_face_request
    ownership, result, approximation = solve_stack()
    _, old_result, _ = solve_stack(use_center_spans=True)
    report = {"imposed_ownership": compile_axial_ownership(explicit_stack()),
              "fresh_ownership": ownership, "fresh_result": result, "center_span_result": old_result,
              "contact_polygon_approximation": approximation,
              "land_transition": solve_land_transition(json.loads((ROOT/"examples/dc_land_transition/three-patch.request.json").read_text())),
              "land_refinement": [solve_land_transition(same_face_request(n)) for n in (4, 8, 16)]}
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    after = {name: digest(ROOT/name) for name in SOURCES}
    receipt = {"contract": "spike/pi01-s02-blocker-evidence/v1", "stage_id": "PI01-S02",
        "status": "passed" if before == after and executed.wasSuccessful() and not executed.skipped else "failed",
        "stage_complete": False, "production_qualified": False, "sources_before": before, "sources_after": after,
        "tests": {"names": expected, "run": executed.testsRun,
            **{key: [test.id() for test, _ in getattr(executed, attribute)] for key, attribute in
               (("failures", "failures"), ("errors", "errors"), ("skipped", "skipped"), ("expected_failures", "expectedFailures"))},
            "unexpected_successes": [test.id() for test in executed.unexpectedSuccesses]},
        "log": args.log.resolve().relative_to(ROOT).as_posix(), "log_sha256": digest(args.log),
        "report": args.report.resolve().relative_to(ROOT).as_posix(), "report_sha256": digest(args.report),
        "finite_evidence": args.finite_evidence.resolve().relative_to(ROOT).as_posix(),
        "finite_sha256": digest(args.finite_evidence)}
    args.output.write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    validate_receipt(receipt)
    print(json.dumps({"status": "passed", "tests": executed.testsRun, "stage_complete": False}))


if __name__ == "__main__":
    main()
