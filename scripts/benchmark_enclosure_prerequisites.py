#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound mathematical benchmark suite; not production qualification.

Retains the full assertion log and machine/dependency/source identities. No
skip, expected failure, unexpected success or changed input is accepted. Use
the separate v2 benchmark for retained public JSON requests and result fields.
"""
import argparse
import hashlib
from importlib.metadata import version
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
MODULES = (
    "test_enclosure_rectilinear_momentum",
    "test_enclosure_obstacle_continuum",
    "test_enclosure_symmetric_stress",
    "test_enclosure_rotating_frame",
    "test_enclosure_sa_transport",
    "test_enclosure_cht_v2",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity():
    # All shared enclosure modules, plus the exact benchmark/oracle sources.
    paths = list((ROOT / "python/spike_core").glob("enclosure*.py"))
    paths += [ROOT / f"tests/python/{name}.py" for name in MODULES]
    paths += [ROOT / name for name in (
        "tests/python/test_enclosure_laminar.py",
        "python/spike_core/service_cfd.py",
        "python/spike_core/service_helpers.py",
        "scripts/run_cfd.py",
        "schemas/enclosure-cht-request-v2.schema.json",
        "schemas/enclosure-cht-result-v2.schema.json",
    )]
    paths.append(Path(__file__))
    return {path.relative_to(ROOT).as_posix(): digest(path)
            for path in sorted(set(paths))}


def run(output):
    output = output.resolve()
    output.mkdir(parents=True)  # Existing receipts cannot be overwritten.
    before = source_identity()
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        [f"tests.python.{name}" for name in MODULES])
    started = time.perf_counter()
    with (output / "assertions.log").open("x", encoding="utf-8") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    duration = time.perf_counter() - started
    unchanged = before == source_identity()
    passed = bool(result.testsRun and result.wasSuccessful() and unchanged
                  and not result.skipped and not result.expectedFailures
                  and not result.unexpectedSuccesses)
    receipt = {
        "contract": "spike/enclosure-prerequisite-benchmark/v1",
        "passed": passed,
        "production_qualified": False,
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "machine": platform.machine(), "processor": platform.processor(),
                        "numpy": np.__version__, "scipy": scipy.__version__,
                        "jsonschema": version("jsonschema")},
        "source_sha256": before,
        "sources_unchanged": unchanged,
        "modules": list(MODULES),
        "tests_run": result.testsRun,
        "failures": [str(test) for test, _ in result.failures],
        "errors": [str(test) for test, _ in result.errors],
        "skipped": [str(test) for test, _ in result.skipped],
        "expected_failures": [str(test) for test, _ in result.expectedFailures],
        "unexpected_successes": [str(test) for test in result.unexpectedSuccesses],
        "elapsed_seconds": duration,
        "assertions_sha256": digest(output / "assertions.log"),
        "interpretation": [
            "Synthetic equation verification, not independent-solver or measured validation.",
            "Wall-clock duration is an observation, not a scaling/performance qualification.",
            "Quadratic stress coarse 4/8/12 accuracy probe remains unqualified; see method record.",
            "SA is fixed-velocity transport, not coupled or engineering-qualified RANS.",
            "Whole-frame rotation is not a blade/propeller/sliding-interface workflow.",
            "Selected rectilinear cuts are not confined octree momentum AMR.",
        ],
    }
    with (output / "receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh evidence directory")
    receipt = run(parser.parse_args().output)
    print(json.dumps({key: receipt[key] for key in
                      ("passed", "tests_run", "sources_unchanged", "elapsed_seconds")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
