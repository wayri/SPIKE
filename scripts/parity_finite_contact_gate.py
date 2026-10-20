# SPDX-License-Identifier: Apache-2.0
"""Source-bound PI01-S02A analytical finite-contact DC acceptance."""
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
from scripts.benchmark_pi_finite_contact import run_benchmark, validate_report

STAGE = "PI01-S02A"
MODULES = ("tests.python.test_pi_finite_contact_benchmark", "tests.python.test_dc_precision_partition")
SOURCES = (
    "scripts/parity_finite_contact_gate.py", "scripts/benchmark_pi_finite_contact.py",
    "scripts/parity_pisi_gate.py", "tests/python/test_pi_finite_contact_benchmark.py",
    "tests/python/test_finite_contact_stage_evidence.py", "docs/PI_FINITE_CONTACT_BENCHMARK.md",
    "python/spike_core/peec_conforming_dc.py", "python/spike_core/dc_rt0_density.py",
    "python/spike_core/dc_triangle_partition.py", "python/spike_core/hybrid_mesh.py",
    "python/spike_core/contracts.py", "python/spike_core/dc_result_utils.py",
    "python/spike_core/layers.py", "python/spike_core/local_mesh_controls.py",
    "python/spike_core/planar_polygon_topology.py", "python/spike_core/filled_copper_path.py",
    "python/spike_core/source_filled_boundary.py", "python/spike_core/boundary_spatial_index.py",
    "python/spike_core/dc_precision_partition.py", "tests/python/test_dc_precision_partition.py",
    "docs/DC_PRECISION_PARTITION.md",
)


def suite():
    return unittest.defaultTestLoader.loadTestsFromNames(MODULES)


def validate_receipt(receipt, root=ROOT):
    if (receipt.get("contract") != "spike/finite-contact-stage/v1" or receipt.get("stage_id") != STAGE
            or receipt.get("status") != "passed" or receipt.get("production_qualified") is not False):
        raise ValueError("Finite-contact stage identity/status/scope differs")
    before = receipt.get("sources_before", {})
    if set(before) != set(SOURCES) or receipt.get("sources_after") != before:
        raise ValueError("Finite-contact source coverage differs or drifted")
    for name, sha in before.items():
        bound(root, name, sha)
    expected, result = names(suite()), receipt.get("tests", {})
    if (not expected or any("_FailedTest" in name for name in expected)
            or result.get("names") != expected or result.get("run") != len(expected)
            or any(result.get(key) != [] for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes"))):
        raise ValueError("Finite-contact execution incomplete or failed")
    log = bound(root, receipt.get("log"), receipt.get("log_sha256")).read_text(encoding="utf-8")
    if f"Ran {len(expected)} tests" not in log or not log.rstrip().endswith("OK"):
        raise ValueError("Finite-contact log incomplete")
    report = bound(root, receipt.get("report"), receipt.get("report_sha256"))
    validate_report(json.loads(report.read_text(encoding="utf-8")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "log", "report"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    paths = (args.output, args.log, args.report)
    if len({path.resolve() for path in paths}) != 3:
        parser.error("Evidence outputs must be distinct")
    for path in paths:
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error("Choose fresh repository output paths")
        path.parent.mkdir(parents=True, exist_ok=True)
    before = {name: digest(ROOT/name) for name in SOURCES}
    tests = suite(); expected = names(tests); stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding="utf-8")
    report = run_benchmark()
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    after = {name: digest(ROOT/name) for name in SOURCES}
    receipt = {"contract": "spike/finite-contact-stage/v1", "stage_id": STAGE,
        "status": "passed" if before == after and result.wasSuccessful() and not result.skipped and report["status"] == "passed" else "failed",
        "production_qualified": False, "sources_before": before, "sources_after": after,
        "tests": {"names": expected, "run": result.testsRun,
            **{key: [test.id() for test, _ in getattr(result, attribute)] for key, attribute in
               (("failures", "failures"), ("errors", "errors"), ("skipped", "skipped"), ("expected_failures", "expectedFailures"))},
            "unexpected_successes": [test.id() for test in result.unexpectedSuccesses]},
        "log": args.log.resolve().relative_to(ROOT).as_posix(), "log_sha256": digest(args.log),
        "report": args.report.resolve().relative_to(ROOT).as_posix(), "report_sha256": digest(args.report)}
    args.output.write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    validate_receipt(receipt)
    print(json.dumps({"stage_id": STAGE, "tests": result.testsRun, "status": "passed"}))


if __name__ == "__main__":
    main()
