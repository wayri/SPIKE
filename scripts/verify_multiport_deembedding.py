# SPDX-License-Identifier: Apache-2.0
"""Retain source-bound offline fixture-removal checks, without family promotion."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODULES = ("tests.python.test_sparameter_multiport_deembedding",
           "tests.python.test_multiport_deembedding_workflow")
SOURCES = ("scripts/verify_multiport_deembedding.py",
           "python/spike_core/solvers/signal_integrity/networks/sparameter_multiport_deembedding.py",
           "python/spike_core/solvers/signal_integrity/networks/sparameter_sampling.py",
           "tests/python/test_sparameter_multiport_deembedding.py",
           "tests/python/test_multiport_deembedding_workflow.py",
           "examples/multiport_deembedding/run_fixture.py",
           "docs/MULTIPORT_DEEMBEDDING.md",
           "docs/validation/MULTIPORT_DEEMBEDDING_ORACLES_20261024.md")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names(suite):
    return sorted(name for test in suite for name in
                  (names(test) if isinstance(test, unittest.TestSuite) else [test.id()]))


def validate_receipt(receipt, root=ROOT):
    expected = names(unittest.defaultTestLoader.loadTestsFromNames(MODULES))
    if (receipt.get("contract") != "spike/multiport-deembedding-evidence/v1"
            or receipt.get("status") != "passed" or receipt.get("family_complete") is not False
            or receipt.get("production_qualified") is not False
            or not expected or any("_FailedTest" in name for name in expected)):
        raise ValueError("Invalid or unsupported multiport evidence scope")
    hashes = receipt.get("sources_before", {})
    if set(hashes) != set(SOURCES) or hashes != receipt.get("sources_after"):
        raise ValueError("Multiport source coverage/drift")
    for name, value in hashes.items():
        if digest(root/name) != value:
            raise ValueError("Stale multiport source")
    tests = receipt.get("tests", {})
    if tests.get("names") != expected or tests.get("run") != len(expected) or any(
            tests.get(key) != [] for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes")):
        raise ValueError("Incomplete multiport execution")
    log = (root/receipt["log"]).resolve()
    if not log.is_relative_to(root.resolve()) or digest(log) != receipt["log_sha256"]:
        raise ValueError("Multiport log identity differs")
    content = log.read_text(encoding="utf-8")
    if f"Ran {len(expected)} tests" not in content or not content.rstrip().endswith("OK"):
        raise ValueError("Multiport log incomplete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.log.resolve():
        parser.error("Receipt and log must be distinct")
    for path in (args.output, args.log):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error("Choose fresh repository paths")
        path.parent.mkdir(parents=True, exist_ok=True)
    before = {name: digest(ROOT/name) for name in SOURCES}
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    expected = names(suite)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    args.log.write_text(stream.getvalue(), encoding="utf-8")
    after = {name: digest(ROOT/name) for name in SOURCES}
    receipt = {"contract": "spike/multiport-deembedding-evidence/v1",
               "status": "passed" if before == after and result.wasSuccessful() and not result.skipped else "failed",
               "family_complete": False, "production_qualified": False,
               "sources_before": before, "sources_after": after,
               "tests": {"names": expected, "run": result.testsRun,
                         **{key: [test.id() for test, _ in getattr(result, attribute)] for key, attribute in
                            (("failures", "failures"), ("errors", "errors"), ("skipped", "skipped"),
                             ("expected_failures", "expectedFailures"))},
                         "unexpected_successes": [test.id() for test in result.unexpectedSuccesses]},
               "log": args.log.resolve().relative_to(ROOT).as_posix(), "log_sha256": digest(args.log)}
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    validate_receipt(receipt)
    print(json.dumps({"status": "passed", "tests": result.testsRun, "family_complete": False}))


if __name__ == "__main__":
    main()
