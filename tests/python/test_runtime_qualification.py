from __future__ import annotations

import copy
import json
import subprocess
import unittest
from unittest.mock import patch

from python.spike_core.runtime_qualification import (
    QUALIFICATION_CONTRACT,
    canonical_digest,
    collect_runtime_snapshot,
    normalize_runtime_results,
    qualify_runtime_snapshots,
)


def fixture_results() -> dict:
    return {
        "health": {
            "contract": "spike/worker-health/v1",
            "status": "ready",
            "worker_version": "1.2.3",
            "analysis_contract": "spike/v1",
            "protocol": "json-line",
            "pid": 99,
            "python_version": "3.12.0",
        },
        "capabilities": {
            "contract": "spike/v1",
            "version": "1.2.3",
            "analyses": {"dc": {"state": "available"}},
            "imports": {},
            "geometry": {},
            "network_data": {},
            "models": {},
            "solver_runtime": {},
            "extension_runtime": {},
            "solver_plugins": [
                {"id": "spike.dc", "state": "available", "reason": "machine prose"}
            ],
        },
        "capability_ledger": {"contract": "spike/native-capability-ledger/v1", "workflows": []},
        "list_accelerators": {
            "contract": "spike/acceleration-catalog/v1",
            "backends": [{"id": "numpy", "state": "available", "reason": ""}],
        },
        "list_external_engines": {
            "contract": "spike/external-engine-catalog/v1",
            "engines": [
                {
                    "id": "external.ngspice",
                    "state": "available",
                    "executable": "C:/runtime/ngspice.exe",
                    "reason": "",
                    "runtime_validation": {"volatile": True},
                    "qualification": {"generated": True},
                }
            ],
        },
        "benchmarks": {
            "contract": "spike/solver-benchmark-report/v1",
            "status": "passed",
            "summary": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
            "benchmarks": [
                {
                    "name": "trace",
                    "status": "passed",
                    "measured": 1.0,
                    "expected": 1.0,
                    "relative_error": 0.0,
                    "tolerance": 1e-9,
                    "units": "ohm",
                    "detail": "diagnostic prose",
                }
            ],
        },
    }


class RuntimeQualificationTests(unittest.TestCase):
    def test_snapshot_propagates_explicit_runtime_environment(self):
        responses = [
            json.dumps({"id": f"qualify-{method}", "ok": True, "result": fixture_results()[method]})
            for method in (
                "health",
                "capabilities",
                "capability_ledger",
                "list_accelerators",
                "list_external_engines",
                "benchmarks",
            )
        ]
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="\n".join(responses) + "\n", stderr=""
        )
        with patch(
            "python.spike_core.runtime_qualification.subprocess.run", return_value=completed
        ) as spawned:
            collect_runtime_snapshot(
                ["worker"], cwd=".", environment_overrides={"SPIKE_HOME": "C:/SPIKE"}
            )
        self.assertEqual(spawned.call_args.kwargs["env"]["SPIKE_HOME"], "C:/SPIKE")

    def test_normalization_removes_process_and_path_specific_fields(self):
        source = normalize_runtime_results(fixture_results())
        changed = fixture_results()
        changed["health"]["pid"] = 12345
        changed["health"]["python_version"] = "3.12.9"
        changed["list_external_engines"]["engines"][0]["executable"] = "D:/other/ngspice.exe"
        self.assertEqual(source, normalize_runtime_results(changed))

    def test_identical_snapshots_pass_all_release_checks(self):
        snapshot = normalize_runtime_results(fixture_results())
        report = qualify_runtime_snapshots(snapshot, copy.deepcopy(snapshot))
        self.assertEqual(report["contract"], QUALIFICATION_CONTRACT)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(report["summary"]["total"], 8)

    def test_collection_errors_are_stable_release_evidence(self):
        normalized = normalize_runtime_results(
            fixture_results(),
            collection_errors=[
                {
                    "method": "capability_ledger",
                    "type": "UnknownWorkerMethod",
                    "error_code": "SPIKE-BE-IPC-E-0002",
                }
            ],
        )
        self.assertEqual(
            normalized["collection_errors"],
            [
                {
                    "method": "capability_ledger",
                    "type": "UnknownWorkerMethod",
                    "error_code": "SPIKE-BE-IPC-E-0002",
                }
            ],
        )

    def test_missing_packaged_solver_is_release_blocking(self):
        source = normalize_runtime_results(fixture_results())
        packaged = copy.deepcopy(source)
        packaged["solver_plugins"][0]["state"] = "unavailable"
        report = qualify_runtime_snapshots(source, packaged)
        self.assertEqual(report["status"], "failed")
        failed = {item["id"] for item in report["checks"] if item["status"] == "failed"}
        self.assertEqual(failed, {"runtime.solver_plugins"})

    def test_digest_is_order_independent_for_object_keys(self):
        self.assertEqual(canonical_digest({"a": 1, "b": 2}), canonical_digest({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
