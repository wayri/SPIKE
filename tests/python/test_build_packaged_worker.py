"""Focused release-probe tests for the packaged worker build script."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.geometry_arrow import canonical_geometry_rows
from scripts import build_packaged_worker as packaged_worker


class PackagedWorkerArrowProbeTests(unittest.TestCase):
    def test_extension_release_probe_executes_real_source_extensions(self) -> None:
        from python.spike_core.service import handle
        from scripts.verify_extension_runtime import verify_extension_runtime
        def request(executable, method, params):
            response = handle({"id": "release-probe-test", "method": method, "params": params})
            self.assertTrue(response["ok"], response)
            return response
        result = verify_extension_runtime(None, request)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["odb_tracks"], 1)

    def test_runtime_qualification_updates_bundle_and_repository_gate_copy(self) -> None:
        qualification = {
            "contract": "spike/release-runtime-qualification/v1",
            "status": "passed",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource_root = root / "resources" / "worker"
            build_report = root / "build" / "release-runtime-qualification.json"
            with patch.object(packaged_worker, "RESOURCE_ROOT", resource_root), patch.object(
                packaged_worker, "RUNTIME_QUALIFICATION_PATH", build_report,
            ):
                bundled_report = packaged_worker._write_runtime_qualification(qualification)

            self.assertEqual(bundled_report, resource_root / "release-runtime-qualification.json")
            self.assertEqual(json.loads(bundled_report.read_text(encoding="utf-8")), qualification)
            self.assertEqual(bundled_report.read_bytes(), build_report.read_bytes())

    def test_request_serializes_supplied_params(self) -> None:
        response = {"ok": True, "result": {}}
        completed = subprocess.CompletedProcess(
            args=["worker"], returncode=0, stdout=json.dumps(response) + "\n", stderr="",
        )
        with patch.object(packaged_worker.subprocess, "run", return_value=completed) as run:
            actual = packaged_worker._request(
                Path("worker.exe"), "write_project_package", {"path": "probe.spike"},
            )

        self.assertEqual(actual, response)
        request = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(request, {
            "id": "package-write_project_package",
            "method": "write_project_package",
            "params": {"path": "probe.spike"},
        })

    def test_arrow_probe_writes_then_source_verifies_manifest_bound_rows(self) -> None:
        response = {"ok": True, "result": {"manifest": {"manifest_payload_sha256": "a" * 64}}}
        package = SimpleNamespace(payload={
            "geometry": {"tables": [{
                "path": "geometry/copper_geometry.arrow",
                "schema": "spike/copper-geometry-arrow/v4",
                "sha256": "b" * 64,
            }]},
            "design_ir": {"design_id": "packaged-arrow-probe"},
        })
        captured: dict[str, object] = {}

        def request(executable: Path, method: str, params: dict[str, object]) -> dict[str, object]:
            captured["request"] = (executable, method, params)
            return response

        def decode(path: Path, table_path: str, **kwargs: object) -> dict[str, object]:
            captured["decode"] = (path, table_path, kwargs)
            design = DesignIRV2.from_dict(captured["request"][2]["snapshot"]["design_ir"])
            return {"rows": canonical_geometry_rows(design)}

        with patch.object(packaged_worker, "_request", side_effect=request), patch.object(
            packaged_worker, "read_spike_package", return_value=package,
        ), patch.object(packaged_worker, "read_geometry_arrow_artifact", side_effect=decode):
            probe = packaged_worker._verify_geometry_arrow_package(Path("worker.exe"))

        _, method, params = captured["request"]
        self.assertEqual(method, "write_project_package")
        self.assertEqual(params["snapshot"]["project"]["id"], "packaged-arrow-probe")
        self.assertEqual(len(params["snapshot"]["design_ir"]["tracks"]), 2)
        self.assertEqual(len(params["snapshot"]["design_ir"]["zones"]), 1)
        self.assertEqual(len(params["snapshot"]["design_ir"]["vias"]), 1)
        _, table_path, kwargs = captured["decode"]
        self.assertEqual(table_path, "geometry/copper_geometry.arrow")
        self.assertEqual(kwargs, {"expected_manifest_payload_sha256": "a" * 64})
        self.assertEqual(probe["rows"], 4)
        self.assertEqual(probe["table_contract"], "spike/copper-geometry-arrow/v4")
        self.assertEqual(probe["retained_unresolved_occurrences"], 1)
