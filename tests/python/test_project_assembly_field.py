# SPDX-License-Identifier: Apache-2.0
"""Manifest-bound assembly field-study persistence regressions."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from examples.assembly_field.run_examples import setup
from python.spike_core.solvers.execution.coupling.assembly_field_study import export_assembly_field_study, import_assembly_field_study
from python.spike_core.solvers.execution.coupling.assembly_field_thermal import run_assembly_field_thermal
from python.spike_core.contracts import SpiDeR
from python.spike_core.multiboard_identity import canonical_json_digest
from python.spike_core.multiboard_study import physical_assembly
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_assembly_field import handle_assembly_field_project_request
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.service_mcad_collaboration import _archive_results
from python.spike_core.spider_v2 import SpiDeRV2


MODEL_ARTIFACT = b"ISO-10303-21;END-ISO-10303-21;"


def _payload(request):
    design = SpiDeRV2.from_v1(SpiDeR(
        design_id="original-board", name="Original board", source_format="spike-fixture",
    )).to_dict()
    design["design_id"] = "original-board"
    return {
        "project": {"id": "assembly-field-project", "name": "Assembly field project"},
        "design_ir": design,
        "assembly_ir": copy.deepcopy(request["assembly"]),
        "models": {"contract": "spike/model-index/v1", "models": [{
            "id": "original-case", "name": "Original case", "model_type": "step",
            "uri": "package:models/artifacts/original-case.step",
            "digest": hashlib.sha256(MODEL_ARTIFACT).hexdigest(),
            "transform": [], "extensions": {},
        }]},
        "analyses": {}, "results": {}, "audit": [],
    }


def _write(path, request):
    return write_spike_package(
        path, _payload(request), model_artifacts={"original-case.step": MODEL_ARTIFACT},
    )


def _call(method, path, manifest, **extra):
    return handle_assembly_field_project_request(method, {
        "project_path": str(path),
        "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
        **extra,
    }, request_id=method, application_version="test")


class AssemblyFieldProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request, cls.problem = setup()
        cls.result = run_assembly_field_thermal(cls.request, cls.problem)
        cls.record = export_assembly_field_study(cls.request, cls.problem, cls.result)

    def test_generic_project_handler_does_not_import_field_numerics(self):
        check = subprocess.run(
            [sys.executable, "-c", (
                "import sys; import python.spike_core.service_project_handlers; "
                "assert 'python.spike_core.solvers.execution.coupling.assembly_field_study' not in sys.modules; "
                "assert 'python.spike_core.solvers.execution.coupling.assembly_field_thermal' not in sys.modules"
            )],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
        )
        self.assertEqual(check.returncode, 0, check.stderr or check.stdout)

    def test_actual_experimental_result_saves_reads_and_reopens_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "field-study.spike"
            manifest = _write(path, self.request)
            saved = _call("save_assembly_field_study_in_project", path, manifest, record=self.record)
            self.assertTrue(saved["ok"], saved)
            opened = read_project(path, include_members=True)
            loaded = _call("read_assembly_field_study_in_project", path, opened.manifest)

        self.assertTrue(loaded["ok"], loaded)
        self.assertEqual(loaded["result"]["state"], "current")
        self.assertEqual(loaded["result"]["record"], self.record)
        self.assertEqual(opened.payload["analyses"]["assembly_field_study"], json.loads(json.dumps(self.record)))
        self.assertEqual(opened.members["models/artifacts/original-case.step"], MODEL_ARTIFACT)
        retained = loaded["result"]["record"]["result"]
        self.assertEqual(retained["model_status"], "experimental")
        self.assertFalse(retained["production_qualified"])
        self.assertEqual(retained["field_result"]["status"], "experimental")
        self.assertEqual(retained["field_result"]["model_status"], "experimental")
        self.assertFalse(retained["field_result"]["production_qualified"])

    def test_setup_only_record_with_null_result_is_supported(self):
        record = export_assembly_field_study(
            self.request, self.problem, self.result, include_results=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "field-setup.spike"
            manifest = _write(path, self.request)
            missing = _call("read_assembly_field_study_in_project", path, manifest)
            self.assertTrue(missing["ok"], missing)
            self.assertEqual(missing["result"]["state"], "missing")
            self.assertIsNone(missing["result"]["record"])
            self.assertEqual(missing["result"]["assembly"], physical_assembly(self.request["assembly"]))
            saved = _call("save_assembly_field_study_in_project", path, manifest, record=record)
            self.assertTrue(saved["ok"], saved)
            loaded = _call("read_assembly_field_study_in_project", path, saved["result"]["manifest"])

        self.assertTrue(loaded["ok"], loaded)
        self.assertEqual(loaded["result"]["state"], "current")
        self.assertIsNone(loaded["result"]["record"]["result"])
        self.assertFalse(loaded["result"]["saved_result_present"])

    def test_changed_assembly_returns_stale_without_exposing_saved_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stale-field.spike"
            manifest = _write(path, self.request)
            saved = _call("save_assembly_field_study_in_project", path, manifest, record=self.record)
            self.assertTrue(saved["ok"], saved)
            opened = read_project(path, include_members=True)
            payload = copy.deepcopy(opened.payload)
            transform = list(payload["assembly_ir"]["parts"][0]["frame"]["transform"])
            payload["assembly_ir"]["parts"][0]["frame"]["transform"] = transform
            transform[3] += 1
            changed_manifest = write_spike_package(
                path, payload, preserved_members=opened.members, application_version="test",
            )
            loaded = _call("read_assembly_field_study_in_project", path, changed_manifest)

            self.assertTrue(loaded["ok"], loaded)
            self.assertEqual(loaded["result"]["state"], "stale")
            self.assertIsNone(loaded["result"]["record"])
            self.assertTrue(loaded["result"]["saved_result_present"])
            self.assertIn("rerun", loaded["result"]["action"].lower())
            before_failed_save = read_project(path).manifest["manifest_payload_sha256"]
            failed = _call("save_assembly_field_study_in_project", path, changed_manifest, record=self.record)
            self.assertFalse(failed["ok"])
            self.assertEqual(read_project(path).manifest["manifest_payload_sha256"], before_failed_save)

    def test_corrupt_unknown_oversized_and_mismatched_records_fail_atomically(self):
        corrupt = copy.deepcopy(self.record)
        corrupt["problem"]["boundaries"][0]["temperature_k"] += 1
        unknown = {**copy.deepcopy(self.record), "unexpected": True}
        oversized = {**copy.deepcopy(self.record), "unexpected": "x" * (8 * 1024**2)}
        wrong_reference = copy.deepcopy(self.record)
        wrong_reference["request"]["bodies"][0]["reference_id"] = "different-design"
        wrong_reference["file_digest"] = canonical_json_digest({
            key: value for key, value in wrong_reference.items() if key != "file_digest"
        })
        cases = [corrupt, unknown, oversized, wrong_reference]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rejected-field.spike"
            manifest = _write(path, self.request)
            for record in cases:
                with self.subTest(record_fields=sorted(record)):
                    response = _call("save_assembly_field_study_in_project", path, manifest, record=record)
                    self.assertFalse(response["ok"])
                    self.assertEqual(
                        read_project(path).manifest["manifest_payload_sha256"],
                        manifest["manifest_payload_sha256"],
                    )
            corrupt_payload = _payload(self.request)
            corrupt_payload["analyses"]["assembly_field_study"] = corrupt
            corrupt_manifest = write_spike_package(
                path, corrupt_payload, model_artifacts={"original-case.step": MODEL_ARTIFACT},
            )
            read_response = _call("read_assembly_field_study_in_project", path, corrupt_manifest)
            self.assertFalse(read_response["ok"])
            self.assertIn("corrupt or unsupported", read_response["error"])

    def test_reduced_study_output_extension_is_excluded_from_assembly_identity(self):
        payload = _payload(self.request)
        payload["assembly_ir"].setdefault("extensions", {})["spike.multiboard-studies"] = {
            "thermal": {"result": {"status": "experimental-output"}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reduced-output.spike"
            manifest = write_spike_package(
                path, payload, model_artifacts={"original-case.step": MODEL_ARTIFACT},
            )
            response = _call("save_assembly_field_study_in_project", path, manifest, record=self.record)
            self.assertTrue(response["ok"], response)
            reopened = read_project(path)

        self.assertIn("spike.multiboard-studies", reopened.payload["assembly_ir"]["extensions"])
        self.assertEqual(reopened.payload["analyses"]["assembly_field_study"], json.loads(json.dumps(self.record)))

    def test_normal_project_save_preserves_or_strips_result_with_valid_study_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "field-base.spike"
            manifest = _write(base, self.request)
            saved = _call("save_assembly_field_study_in_project", base, manifest, record=self.record)
            self.assertTrue(saved["ok"], saved)
            opened = read_project(base)
            for include_results in (True, False):
                with self.subTest(include_results=include_results):
                    destination = root / f"normal-save-{include_results}.spike"
                    normal_save = handle_project_request("write_project_package", {
                        "path": str(destination), "snapshot": copy.deepcopy(opened.payload),
                        "base_package_path": str(base), "include_results": include_results,
                        "generate_geometry_tables": False,
                    }, request_id=f"normal-save-{include_results}", application_version="test")
                    self.assertTrue(normal_save["ok"], normal_save)
                    targeted = handle_project_request("read_assembly_field_study_in_project", {
                        "project_path": str(destination),
                        "expected_manifest_payload_sha256": normal_save["result"]["manifest"]["manifest_payload_sha256"],
                    }, request_id=f"targeted-read-{include_results}", application_version="test")
                    self.assertTrue(targeted["ok"], targeted)
                    self.assertEqual(targeted["result"]["state"], "current")
                    self.assertEqual(
                        targeted["result"]["record"]["result"] is not None,
                        include_results,
                    )
                    retained = read_project(destination).payload["analyses"]["assembly_field_study"]
                    self.assertEqual(retained["contract"], "spike/assembly-field-study-file/v1")
                    self.assertEqual(retained["result"] is not None, include_results)

    def test_structure_and_mcad_invalidation_preserve_a_valid_setup_only_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "field-structure.spike"
            manifest = _write(path, self.request)
            saved = _call("save_assembly_field_study_in_project", path, manifest, record=self.record)
            self.assertTrue(saved["ok"], saved)
            opened = read_project(path)
            assembly = opened.payload["assembly_ir"]
            boards = copy.deepcopy(assembly["boards"])
            boards[0]["frame"]["transform"] = list(boards[0]["frame"]["transform"])
            boards[0]["frame"]["transform"][3] += 1
            moved = handle_project_request("update_assembly_structure_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": saved["result"]["manifest"]["manifest_payload_sha256"],
                "boards": boards, "harnesses": assembly["harnesses"],
                "connector_mappings": assembly["connector_mappings"],
                "rigid_flex_links": assembly["rigid_flex_links"],
            }, request_id="move-field-board", application_version="test")
            self.assertTrue(moved["ok"], moved)
            reopened = read_project(path)
            stripped = reopened.payload["analyses"]["assembly_field_study"]
            self.assertIsNone(import_assembly_field_study(stripped)["result"])
            targeted = _call("read_assembly_field_study_in_project", path, moved["result"]["manifest"])
            self.assertTrue(targeted["ok"], targeted)
            self.assertEqual(targeted["result"]["state"], "stale")
            self.assertIsNone(targeted["result"]["record"])

        payload = {"analyses": {"assembly_field_study": copy.deepcopy(self.record)},
                   "results": {}, "extensions": {}}
        _archive_results(payload, self.request["assembly"])
        admitted = import_assembly_field_study(payload["analyses"]["assembly_field_study"])
        self.assertIsNone(admitted["result"])
        previous = payload["extensions"]["spike.mcad-collaboration"]["previous_states"][-1]
        self.assertIsNotNone(previous["analyses"]["assembly_field_study"]["result"])


if __name__ == "__main__":
    unittest.main()
