# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Contract checks for the frozen native CHT probe; not numerical proof."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.verify_native_cht_runtime import verify_native_cht_runtime


class PackagedNativeChtProbeTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[2] / ".local" / "test-temp" / "release-full-20261023"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temp_root)
        root = Path(self.directory.name)
        self.worker = root / "spike-worker.exe"
        self.native = root / "_internal" / "native" / "spike_native_cht.exe"
        self.native.parent.mkdir(parents=True)
        self.worker.write_bytes(b"worker")
        self.native.write_bytes(b"native-cht")
        self.sha = hashlib.sha256(self.native.read_bytes()).hexdigest()

    def tearDown(self):
        self.directory.cleanup()

    def capabilities(self):
        return {"ok": True, "result": {"production_qualified": False,
            "assembly_cht_supported": False, "engines": {"spike.native_cht": {
                "available": True, "executable": str(self.native),
                "contract": "spike/native-cht-request/v1", "model_status": "experimental",
                "production_qualified": False,
                "geometry": "2d_square_cavity_between_two_solid_slabs",
                "flow": "constant_property_incompressible_laminar", "thermal": True,
                "conjugate_interfaces": True, "turbulence": False,
                "assembly_geometry": False}}}}

    def converged(self):
        heat = 10 / 105
        return {"ok": True, "result": {"contract": "spike/native-cht-result/v1",
            "status": "converged", "model_status": "experimental",
            "production_qualified": False, "provenance": {"executable_sha256": self.sha},
            "fields": {"thermal": {"temperature_k": [305.] * 96}},
            "interfaces": {"bottom": {}, "top": {}},
            "diagnostics": {"hot_input_w": heat, "cold_output_w": heat,
                            "interface_heat_flow_w": {"bottom": heat, "top": heat}}}}

    def failed(self):
        return {"ok": True, "result": {"contract": "spike/native-cht-result/v1",
            "status": "failed_to_converge", "model_status": "experimental",
            "production_qualified": False, "provenance": {"executable_sha256": self.sha},
            "fields": None, "interfaces": None}}

    def transport(self, executable, method, params):
        self.assertEqual(Path(executable), self.worker)
        if method == "cfd_capabilities":
            return self.capabilities()
        self.assertEqual(method, "run_native_cht")
        return self.failed() if params["request"].get("max_thermal_iterations") == 1 else self.converged()

    def test_valid_transport_contract_produces_bounded_report(self):
        report = verify_native_cht_runtime(self.worker, self.transport)
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["production_qualified"])
        self.assertEqual(report["native_binary_sha256"], self.sha)
        self.assertAlmostEqual(report["conduction_heat_w"], 10 / 105)
        self.assertLess(len(str(report)), 2048)

    def assertMutationRejected(self, stage, mutate):
        def transport(executable, method, params):
            value = (self.capabilities() if method == "cfd_capabilities" else
                     self.failed() if params["request"].get("max_thermal_iterations") == 1
                     else self.converged())
            if ((stage == "capability" and method == "cfd_capabilities")
                    or (stage == "result" and method != "cfd_capabilities"
                        and "max_thermal_iterations" not in params["request"])
                    or (stage == "failure" and params.get("request", {}).get("max_thermal_iterations") == 1)):
                mutate(value)
            return value
        with self.assertRaises(RuntimeError):
            verify_native_cht_runtime(self.worker, transport)

    def test_malformed_result_false_qualification_heat_and_nonfinite_reject(self):
        cases = (
            ("result", lambda r: r["result"].pop("fields")),
            ("result", lambda r: r["result"].update(production_qualified=True)),
            ("result", lambda r: r["result"]["diagnostics"].update(hot_input_w=.2)),
            ("result", lambda r: r["result"]["fields"]["thermal"].update(
                temperature_k=[math.nan] * 96)),
            ("failure", lambda r: r["result"].update(fields={})),
            ("capability", lambda r: r["result"]["engines"]["spike.native_cht"].update(
                turbulence=True)),
        )
        for stage, mutation in cases:
            with self.subTest(stage=stage, mutation=mutation):
                self.assertMutationRejected(stage, mutation)

    def test_outside_bundle_path_rejects(self):
        outside = Path(self.directory.name).parent / "spike_native_cht.exe"
        outside.write_bytes(b"outside")
        try:
            self.assertMutationRejected("capability", lambda r: r["result"]["engines"][
                "spike.native_cht"].update(executable=str(outside)))
        finally:
            outside.unlink()

    def test_legacy_root_native_path_rejects(self):
        legacy = self.worker.parent / "native" / "spike_native_cht.exe"
        legacy.parent.mkdir()
        legacy.write_bytes(b"legacy")
        self.assertMutationRejected("capability", lambda r: r["result"]["engines"][
            "spike.native_cht"].update(executable=str(legacy)))

    def test_resolved_symlink_escape_rejects(self):
        link = self.native.parent / "linked_native_cht.exe"
        outside = self.worker.parent / "outside" / "spike_native_cht.exe"
        outside.parent.mkdir()
        outside.write_bytes(b"outside-link-target")
        original_resolve = Path.resolve
        def resolve(path, *args, **kwargs):
            if path == link:
                return original_resolve(outside, *args, **kwargs)
            return original_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", autospec=True, side_effect=resolve):
            self.assertMutationRejected("capability", lambda r: r["result"]["engines"][
                "spike.native_cht"].update(executable=str(link)))

    def test_binary_hash_mismatch_and_drift_reject(self):
        self.assertMutationRejected("result", lambda r: r["result"]["provenance"].update(
            executable_sha256="0" * 64))
        calls = 0
        def drifting(executable, method, params):
            nonlocal calls
            calls += 1
            value = self.transport(executable, method, params)
            if calls == 2:
                self.native.write_bytes(b"changed")
            return value
        with self.assertRaises(RuntimeError):
            verify_native_cht_runtime(self.worker, drifting)

    def test_none_and_list_results_fail_as_runtime_errors(self):
        for malformed in (None, []):
            def transport(executable, method, params, value=malformed):
                if method == "cfd_capabilities":
                    return self.capabilities()
                return {"ok": True, "result": value}
            with self.subTest(malformed=malformed), self.assertRaises(RuntimeError):
                verify_native_cht_runtime(self.worker, transport)

    def test_direct_cli_reaches_lazy_builder_import(self):
        script = Path(__file__).resolve().parents[2] / "scripts" / "verify_native_cht_runtime.py"
        missing = Path(self.directory.name) / "missing-worker.exe"
        process = subprocess.run([sys.executable, str(script), "--worker", str(missing)],
                                 cwd=Path(self.directory.name), text=True,
                                 capture_output=True, timeout=30, check=False)
        self.assertNotEqual(process.returncode, 0)
        self.assertNotIn("ModuleNotFoundError", process.stderr)
        self.assertIn("Frozen worker executable is unavailable", process.stderr)


if __name__ == "__main__":
    unittest.main()
