# SPDX-License-Identifier: Apache-2.0
"""Emit source-bound SI01-S02 reviewed constraint-export evidence."""
from __future__ import annotations

import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCES = (
    "python/spike_core/solvers/signal_integrity/networks/si_candidate_constraints.py",
    "python/spike_core/solvers/signal_integrity/networks/si_candidate_study.py",
    "tests/python/test_si_candidate_constraints.py",
    "tests/python/test_si_candidate_constraint_evidence.py",
    "scripts/verify_si_candidate_constraints.py",
    "docs/SI_CANDIDATE_CONSTRAINT_EXPORT.md",
    "docs/SI_CANDIDATE_STUDY.md",
    "examples/si_candidate_constraints/run_export.py",
    "schemas/si-candidate-study-request-v1.schema.json",
    "schemas/si-candidate-study-result-v1.schema.json",
)
FLAGS = ("native_layout_applied", "continuous_band_qualified", "physical_qualified",
         "production_qualified", "family_complete")
EXPECTED_TEST_COUNT = 6


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def suite():
    return unittest.defaultTestLoader.loadTestsFromName("tests.python.test_si_candidate_constraints")


def names(value):
    output = []
    for item in value:
        output.extend(names(item) if isinstance(item, unittest.TestSuite) else [item.id()])
    return output


def retained(root, binding):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("Evidence binding must contain path and SHA-256")
    path = (root / str(binding["path"])).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Evidence path must be a retained project file")
    if binding["sha256"] != digest(path):
        raise ValueError("Evidence digest differs")
    return path


def validate_receipt(receipt, root=ROOT):
    required = {"contract", "stage_id", "status", "stage_complete", "workflow",
                "sources_before", "sources_after", "tests", "log", *FLAGS}
    if (not isinstance(receipt, dict) or set(receipt) != required
            or receipt.get("contract") != "spike/si-candidate-constraint-evidence/v1"
            or receipt.get("stage_id") != "SI01-S02" or receipt.get("status") != "passed"
            or receipt.get("stage_complete") is not True
            or receipt.get("workflow") != "offline_reviewed_export"
            or any(receipt.get(flag) is not False for flag in FLAGS)):
        raise ValueError("Unsupported SI01-S02 evidence identity or scope")
    expected = names(suite())
    if len(expected) != EXPECTED_TEST_COUNT or any("_FailedTest" in name for name in expected):
        raise ValueError("SI01-S02 test inventory differs")
    before, after = receipt.get("sources_before"), receipt.get("sources_after")
    if (not isinstance(before, dict) or not isinstance(after, dict)
            or set(before) != set(SOURCES) or set(after) != set(SOURCES) or before != after):
        raise ValueError("SI01-S02 source coverage or stability differs")
    for name, expected_digest in before.items():
        path = (root / name).resolve()
        if (not path.is_relative_to(root.resolve()) or not path.is_file()
                or digest(path) != expected_digest):
            raise ValueError("SI01-S02 retained source differs")
    tests = receipt.get("tests")
    outcomes = ("failures", "errors", "skipped", "expected_failures", "unexpected_successes")
    if (not isinstance(tests, dict)
            or set(tests) != {"names", "run", *outcomes}
            or tests.get("names") != expected or tests.get("run") != len(expected)
            or any(tests.get(key) != [] for key in outcomes)):
        raise ValueError("SI01-S02 execution is incomplete")
    log = retained(root, receipt.get("log")).read_text(encoding="utf-8")
    if (f"Ran {len(expected)} tests" not in log or not log.rstrip().endswith("OK")
            or any(name.rsplit(".", 1)[-1] not in log for name in expected)):
        raise ValueError("SI01-S02 execution log is incomplete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.log):
        resolved = path.resolve()
        if not resolved.is_relative_to(ROOT) or path.exists():
            parser.error("Outputs must be new project paths")
        path.parent.mkdir(parents=True, exist_ok=True)
    before = {name: digest(ROOT / name) for name in SOURCES}
    tests = suite(); expected = names(tests)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding="utf-8")
    after = {name: digest(ROOT / name) for name in SOURCES}
    passed = (before == after and result.wasSuccessful() and not result.skipped
              and not result.expectedFailures and not result.unexpectedSuccesses
              and result.testsRun == len(expected) == EXPECTED_TEST_COUNT)
    receipt = {"contract": "spike/si-candidate-constraint-evidence/v1", "stage_id": "SI01-S02",
        "status": "passed" if passed else "failed", "stage_complete": passed,
        "workflow": "offline_reviewed_export", "sources_before": before, "sources_after": after,
        "tests": {"names": expected, "run": result.testsRun,
            "failures": [test.id() for test, _ in result.failures],
            "errors": [test.id() for test, _ in result.errors],
            "skipped": [test.id() for test, _ in result.skipped],
            "expected_failures": [test.id() for test, _ in result.expectedFailures],
            "unexpected_successes": [test.id() for test in result.unexpectedSuccesses]},
        "log": {"path": args.log.resolve().relative_to(ROOT).as_posix(), "sha256": digest(args.log)},
        **{flag: False for flag in FLAGS}}
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if passed:
        validate_receipt(receipt)
    print(json.dumps({"stage_id": "SI01-S02", "status": receipt["status"],
                      "tests": result.testsRun, "stage_complete": passed,
                      "family_complete": False}))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
