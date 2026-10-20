# SPDX-License-Identifier: Apache-2.0
"""Execute source-bound SI02-S07 physical coupled-pair verification."""
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

STAGE = "SI02-S07"
MODULES = ("tests.python.test_rlgc_coupled_pair", "tests.python.test_rlgc_coupled_pair_contract")
SOURCES = ("scripts/parity_coupled_pair_gate.py", "scripts/parity_pisi_gate.py",
    "python/spike_core/rlgc_coupled_pair.py", "python/spike_core/rlgc_line_fields.py",
    "python/spike_core/rlgc_line_network.py", "python/spike_core/sparameter_sampling.py",
    "python/spike_core/service.py", "python/spike_core/service_simulation_handlers.py",
    "python/spike_core/service_sparameter_processing.py", "python/spike_core/cli.py",
    "schemas/rlgc-coupled-pair-request-v1.schema.json", "schemas/rlgc-coupled-pair-result-v1.schema.json",
    "schemas/rlgc-line-network-request-v1.schema.json", "schemas/rlgc-line-fields-request-v1.schema.json",
    "schemas/rlgc-line-fields-result-v1.schema.json", "schemas/manifest.json",
    "examples/rlgc_coupled_pair/run_pair.py", "examples/rlgc_coupled_pair/symmetric-pair.request.json",
    "tests/python/test_rlgc_coupled_pair.py", "tests/python/test_rlgc_coupled_pair_contract.py",
    "tests/python/test_coupled_pair_stage_evidence.py", "docs/RLGC_COUPLED_PAIR.md")


def suite():
    return unittest.defaultTestLoader.loadTestsFromNames(MODULES)


def validate_receipt(receipt, root=ROOT):
    if (receipt.get("contract") != "spike/coupled-pair-stage/v1" or receipt.get("stage_id") != STAGE
            or receipt.get("status") != "passed" or receipt.get("production_qualified") is not False):
        raise ValueError("Coupled pair evidence identity/status/scope differs")
    hashes = receipt.get("sources_before", {})
    if set(hashes) != set(SOURCES) or receipt.get("sources_after") != hashes:
        raise ValueError("Coupled pair source coverage differs or drifted")
    for name, sha in hashes.items():
        bound(root, name, sha)
    expected, result = names(suite()), receipt.get("tests", {})
    if (not expected or any("_FailedTest" in name for name in expected)
            or result.get("names") != expected or result.get("run") != len(expected)
            or any(result.get(key) != [] for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes"))):
        raise ValueError("Coupled pair execution incomplete or failed")
    log = bound(root, receipt.get("log"), receipt.get("log_sha256")).read_text(encoding="utf-8")
    if f"Ran {len(expected)} tests" not in log or not log.rstrip().endswith("OK"):
        raise ValueError("Coupled pair log incomplete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.log):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error("Choose fresh repository output paths")
        path.parent.mkdir(parents=True, exist_ok=True)
    before = {name: digest(ROOT/name) for name in SOURCES}
    tests = suite(); expected = names(tests); stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding="utf-8")
    after = {name: digest(ROOT/name) for name in SOURCES}
    receipt = {"contract": "spike/coupled-pair-stage/v1", "stage_id": STAGE,
        "status": "passed" if before == after and result.wasSuccessful() and not result.skipped else "failed",
        "production_qualified": False, "sources_before": before, "sources_after": after,
        "tests": {"names": expected, "run": result.testsRun,
            **{key: [test.id() for test, _ in getattr(result, attribute)] for key, attribute in
               (("failures", "failures"), ("errors", "errors"), ("skipped", "skipped"), ("expected_failures", "expectedFailures"))},
            "unexpected_successes": [test.id() for test in result.unexpectedSuccesses]},
        "log": args.log.resolve().relative_to(ROOT).as_posix(), "log_sha256": digest(args.log)}
    args.output.write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    validate_receipt(receipt)
    print(json.dumps({"stage_id": STAGE, "tests": result.testsRun, "status": "passed"}))


if __name__ == "__main__":
    main()
