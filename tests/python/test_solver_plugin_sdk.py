"""Contract tests for the clean-room process-solver extension SDK."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.solver_plugins import SolverPluginManifest, SolverRegistry


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
SDK = ROOT / "solver_sdk"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class SolverPluginSdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin_schema = _json(SCHEMAS / "solver-plugin-v1.schema.json")
        cls.probe_schema = _json(SCHEMAS / "solver-plugin-probe-v1.schema.json")
        cls.probe_result_schema = _json(SCHEMAS / "solver-plugin-probe-result-v1.schema.json")
        cls.mesh_schema = _json(SCHEMAS / "solver-mesh-v1.schema.json")
        cls.job_schema = _json(SCHEMAS / "solver-plugin-job-v1.schema.json")
        cls.result_schema = _json(SCHEMAS / "solver-plugin-result-v1.schema.json")
        for schema in (
            cls.plugin_schema, cls.probe_schema, cls.probe_result_schema,
            cls.mesh_schema, cls.job_schema, cls.result_schema,
        ):
            Draft202012Validator.check_schema(schema)

    def test_vendor_examples_are_clean_room_fail_closed_descriptors(self) -> None:
        for name, expected_id in (
            ("openems-solver-plugin.example.json", "external.openems"),
            ("elmerfem-solver-plugin.example.json", "external.elmer"),
            ("sparselizard-solver-plugin.example.json", "external.sparselizard"),
        ):
            with self.subTest(name=name):
                example = _json(SDK / name)
                Draft202012Validator(self.plugin_schema).validate(example)
                manifest = SolverPluginManifest.from_dict(example)
                self.assertEqual(manifest.id, expected_id)
                self.assertEqual(manifest.state, "unavailable")
                self.assertEqual(manifest.model_status, "unsupported")
                self.assertTrue(manifest.qualification["runtime_probe_required"])
                self.assertTrue(manifest.qualification["adapter_validation_required"])
                self.assertTrue(manifest.qualification["workflow_validation_required"])

    def test_mesh_job_and_result_artifacts_are_bounded_and_job_relative(self) -> None:
        mesh = {
            "contract": "spike/solver-mesh/v1", "units": "mm", "coordinate_system": "right_handed_xyz",
            "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            "cells": [{"id": "tri-1", "kind": "triangle", "vertices": [0, 1, 2], "source_object_ids": ["track:t1"]}],
            "object_map": {"track:t1": {"kind": "track", "net": "SIG", "layer": "F.Cu"}},
            "counts": {"vertices": 3, "cells": 1},
        }
        Draft202012Validator(self.mesh_schema).validate(mesh)
        job = {
            "contract": "spike/solver-plugin-job/v1", "request_id": "sdk-fixture",
            "solver": {"id": "external.example", "version": "1"}, "analysis": {"mode": "ac"},
            "inputs": {"geometry": {"path": "input/geometry.json", "sha256": "a" * 64, "contract": "spike/solver-geometry/v1"}, "meshes": [{"path": "input/mesh.json", "sha256": "b" * 64, "contract": "spike/solver-mesh/v1"}]},
            "output": {"result_contract": "spike/solver-plugin-result/v1", "path": "output/result.json"},
            "resource_budget": {"max_wall_time_s": 60, "max_result_bytes": 1048576},
        }
        Draft202012Validator(self.job_schema).validate(job)
        result = {
            "contract": "spike/solver-plugin-result/v1", "request_id": "sdk-fixture",
            "solver": {"id": "external.example", "version": "1"}, "status": "completed", "model_status": "unvalidated",
            "artifacts": [{"kind": "network", "path": "output/result.s2p", "sha256": "c" * 64, "bytes": 128, "contract": "touchstone/2.1"}],
            "provenance": {"adapter_version": "1", "runtime_probe": "passed", "qualification": "workflow_validation_pending"}, "issues": [],
        }
        Draft202012Validator(self.result_schema).validate(result)
        escaped = json.loads(json.dumps(job))
        escaped["output"]["path"] = "../result.json"
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.job_schema).validate(escaped)

    def test_probe_schema_never_conflates_runtime_evidence_with_qualification(self) -> None:
        probe = {"contract": "spike/solver-plugin-probe/v1", "argv": ["--spike-probe"], "timeout_s": 15, "result_contract": "spike/solver-plugin-probe-result/v1"}
        Draft202012Validator(self.probe_schema).validate(probe)
        passed = {"contract": "spike/solver-plugin-probe-result/v1", "status": "passed", "runtime": {"name": "fixture", "version": "1"}, "adapter": {"version": "1", "protocol": "spike/solver-plugin/v1"}}
        Draft202012Validator(self.probe_result_schema).validate(passed)
        self.assertNotIn("validated", passed)

    def test_manifest_runtime_probe_is_bounded_and_declares_its_exact_result_contract(self) -> None:
        base = _json(SDK / "elmerfem-solver-plugin.example.json")
        invalid_timeout = json.loads(json.dumps(base))
        invalid_timeout["runtime_probe"]["timeout_s"] = 61
        with self.assertRaisesRegex(ValueError, "1 to 60"):
            SolverPluginManifest.from_dict(invalid_timeout)
        invalid_contract = json.loads(json.dumps(base))
        invalid_contract["runtime_probe"]["result_contract"] = "spike/not-a-probe-result/v1"
        with self.assertRaisesRegex(ValueError, "probe-result contract"):
            SolverPluginManifest.from_dict(invalid_contract)

    def test_schema_catalog_registers_every_process_extension_contract(self) -> None:
        catalog = _json(SCHEMAS / "manifest.json")["schemas"]
        self.assertEqual(catalog["spike/solver-plugin/v1"], "solver-plugin-v1.schema.json")
        self.assertEqual(catalog["spike/solver-plugin-probe/v1"], "solver-plugin-probe-v1.schema.json")
        self.assertEqual(catalog["spike/solver-plugin-probe-result/v1"], "solver-plugin-probe-result-v1.schema.json")
        self.assertEqual(catalog["spike/solver-mesh/v1"], "solver-mesh-v1.schema.json")
        self.assertEqual(catalog["spike/solver-plugin-job/v1"], "solver-plugin-job-v1.schema.json")
        self.assertEqual(catalog["spike/solver-plugin-result/v1"], "solver-plugin-result-v1.schema.json")

    def test_explicit_selection_cannot_execute_an_unavailable_process_plugin(self) -> None:
        manifest = SolverPluginManifest(
            id="external.unavailable-fixture", name="Unavailable fixture", version="1", provider="tests",
            analyses=["dc"], formulations=["fixture"], capabilities=[], state="unavailable",
            model_status="unsupported", validation="Runtime and workflow evidence are absent.",
        )

        class MustNotRun:
            def __init__(self) -> None:
                self.manifest = manifest

            def run(self, design, spec):  # pragma: no cover - execution is the failure
                raise AssertionError("Unavailable plugin was executed")

        registry = SolverRegistry()
        registry.register(MustNotRun())
        result = registry.run(DesignIR(), AnalysisSpec(mode="dc", solver_id=manifest.id))
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.issues[0].code, "SOLVER_PLUGIN_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
