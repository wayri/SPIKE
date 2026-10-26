# SPDX-License-Identifier: Apache-2.0
"""Small source/resource and frozen-owner regressions; no package build required."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import prepare_release_resources as staging
from scripts import verify_packaged_source_modules as coherence
from scripts.verify_si_ibis_spatial_runtime import ROOT, verify_si_ibis_spatial_runtime


class SiIbisSpatialPackagingTests(unittest.TestCase):
    @staticmethod
    def request(executable, method, params):
        from python.spike_core.service import handle
        response = handle({"id": "packaging-si-test", "method": method, "params": params})
        if response.get("ok") is not True:
            raise RuntimeError(response)
        return response

    def test_source_service_runs_compile_inspection_and_supplied_pair(self):
        result = verify_si_ibis_spatial_runtime(None, self.request)
        self.assertEqual(result["spatial_samples"], 32)
        self.assertEqual(result["frequencies"], 3)
        self.assertEqual(result["native_execution"], "not_run")
        self.assertFalse(result["production_qualified"])

    def test_probe_rejects_stale_geometry_and_corrupted_display_voltage(self):
        for corruption in ("geometry", "voltage", "status"):
            def request(executable, method, params):
                response = deepcopy(self.request(executable, method, params))
                if method == "run_si_spatial_pair":
                    data = response["result"]["data"]
                    if corruption == "geometry":
                        data["binding"]["sourceDesignDigest"] = "0" * 64
                    elif corruption == "voltage":
                        data["traceSamples"][0]["inducedVoltageV"][0][0] += 1
                    else:
                        data["modelStatus"] = "validated"
                return response
            with self.subTest(corruption=corruption), self.assertRaises(RuntimeError):
                verify_si_ibis_spatial_runtime(None, request)

    def test_missing_and_stale_ibis_owners_fail_frozen_source_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            modules = {}
            for name in coherence.SI_IBIS_SPATIAL_MODULES:
                source = root.joinpath(*name.split(".")).with_suffix(".py")
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("VALUE = 7\n", encoding="utf-8")
                modules[name] = compile("VALUE = 7\n", "relocated.py", "exec")
            archive = SimpleNamespace(toc=modules, extract=lambda name: modules[name])
            reader = SimpleNamespace(open_embedded_archive=lambda name: archive)
            with patch.object(coherence, "CArchiveReader", return_value=reader):
                report = coherence.inspect_packaged_source_modules("fixture", source_root=root,
                                                                  require_si_ibis_spatial=True)
                self.assertEqual(report["status"], "passed")
                name = "python.spike_core.solvers.signal_integrity.receivers.ibis_behavioral_execution"
                modules.pop(name)
                report = coherence.inspect_packaged_source_modules("fixture", source_root=root,
                                                                  require_si_ibis_spatial=True)
                self.assertEqual(report["required_missing"], [name])
                self.assertEqual(report["status"], "failed")
                modules[name] = compile("VALUE = 8\n", "relocated.py", "exec")
                report = coherence.inspect_packaged_source_modules("fixture", source_root=root,
                                                                  require_si_ibis_spatial=True)
                self.assertEqual(report["changed"], [name])
                self.assertEqual(report["status"], "failed")

    def test_release_config_stages_actual_inert_si_fixtures_without_cache(self):
        real = json.loads((ROOT / "app/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        self.assertEqual(real["bundle"]["resources"]["../../examples/si"], "examples/si")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "app/src-tauri/tauri.conf.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"identifier": "org.spike.integrity", "bundle": {
                "resources": {"../../examples/si": "examples/si"}}}), encoding="utf-8")
            included = set()
            # Only these small fixture files are copied; no native payload staging.
            for relative in ("ibis_driver_receiver/request.json", "ibis_driver_receiver/original_cmos.ibs",
                             "spatial_crosstalk/setup.json"):
                source = ROOT / "examples/si" / relative
                target = root / "examples/si" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                included.add(target.relative_to(root).as_posix())
            cache = root / "examples/si/__pycache__/build.pyc"
            cache.parent.mkdir()
            cache.write_bytes(b"cache")
            included.add(cache.relative_to(root).as_posix())
            with patch.object(staging, "source_files", return_value=included):
                staging.prepare(root, root / "build/tauri.release.json")
            stage = root / "build/release-resources"
            self.assertFalse((stage / "examples/si/__pycache__").exists())
            for relative in included - {cache.relative_to(root).as_posix()}:
                self.assertEqual((stage / relative).read_bytes(), (root / relative).read_bytes())
            self.assertEqual(verify_si_ibis_spatial_runtime(None, self.request, resource_root=stage)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
