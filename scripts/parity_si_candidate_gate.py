# SPDX-License-Identifier: Apache-2.0
"""Source-bound SI01-S01 numerical and actual public-boundary evidence."""
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

STAGE = "SI01-S01"
MODULES = ("tests.python.test_si_candidate_study", "tests.python.test_si_candidate_study_contract")
SOURCES = (
    "scripts/parity_si_candidate_gate.py", "scripts/parity_pisi_gate.py",
    "python/spike_core/si_candidate_study.py", "python/spike_core/si_workflow.py",
    "python/spike_core/si_network_workflow.py", "python/spike_core/si_passives.py",
    "python/spike_core/si_ibis.py", "python/spike_core/si_workflow_resonance.py",
    "python/spike_core/si_symbol_clock.py", "python/spike_core/si_clock_recovery.py",
    "python/spike_core/si_channel.py", "python/spike_core/sparameters.py", "python/spike_core/si_impedance.py",
    "python/spike_core/cli.py", "python/spike_core/service.py",
    "python/spike_core/service_simulation_handlers.py", "python/spike_core/service_sparameter_processing.py",
    "tests/python/test_si_candidate_study.py", "tests/python/test_si_candidate_study_contract.py",
    "examples/si_candidate_study/run_study.py", "examples/si_candidate_study/candidates.request.json",
    "schemas/si-candidate-study-request-v1.schema.json", "schemas/si-candidate-study-result-v1.schema.json",
    "schemas/si-workflow-request-v1.schema.json", "schemas/si-workflow-result-v1.schema.json",
    "schemas/manifest.json", "docs/SI_CANDIDATE_STUDY.md",
    "tests/python/test_si_candidate_stage_evidence.py",
)


def suite():
    return unittest.defaultTestLoader.loadTestsFromNames(MODULES)


def validate_receipt(receipt, root=ROOT):
    if (receipt.get("contract") != "spike/si-candidate-stage/v1" or receipt.get("stage_id") != STAGE
            or receipt.get("status") != "passed" or receipt.get("production_qualified") is not False):
        raise ValueError("SI candidate stage identity/status/scope differs")
    if set(receipt.get("sources", {})) != set(SOURCES):
        raise ValueError("SI candidate stage source coverage differs")
    for name, sha in receipt["sources"].items():
        bound(root, name, sha)
    expected = names(suite())
    result = receipt.get("tests", {})
    if (not expected or any("_FailedTest" in name for name in expected)
            or result.get("names") != expected or result.get("run") != len(expected)
            or any(result.get(key) != [] for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes"))):
        raise ValueError("SI candidate stage execution incomplete or failed")
    log = bound(root, receipt.get("log"), receipt.get("log_sha256")).read_text(encoding="utf-8")
    if f"Ran {len(expected)} tests" not in log or not log.rstrip().endswith("OK"):
        raise ValueError("SI candidate test log incomplete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.log):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error("Outputs must be new project paths")
        path.parent.mkdir(parents=True, exist_ok=True)
    hashes = {name: digest(ROOT/name) for name in SOURCES}
    tests = suite(); expected = names(tests)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding="utf-8")
    stable = hashes == {name: digest(ROOT/name) for name in SOURCES}
    receipt = {"contract": "spike/si-candidate-stage/v1", "stage_id": STAGE,
        "status": "passed" if stable and result.wasSuccessful() and not result.skipped else "failed",
        "production_qualified": False, "sources": hashes,
        "tests": {"names": expected, "run": result.testsRun,
            **{key: [test.id() for test, _ in getattr(result, attribute)] for key, attribute in
               (("failures", "failures"), ("errors", "errors"), ("skipped", "skipped"), ("expected_failures", "expectedFailures"))},
            "unexpected_successes": [test.id() for test in result.unexpectedSuccesses]},
        "log": args.log.resolve().relative_to(ROOT).as_posix(), "log_sha256": digest(args.log)}
    args.output.write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    validate_receipt(receipt)
    print(json.dumps({"stage_id": STAGE, "status": "passed", "tests": result.testsRun}))


if __name__ == "__main__":
    main()
