import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[2] / "extension_sdk" / "python" / "spike_extension_sdk.py"
SPEC = importlib.util.spec_from_file_location("spike_extension_sdk", MODULE_PATH)
SDK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SDK)


class ExtensionSdkPythonTests(unittest.TestCase):
    def test_mesh_helper_and_result_carry_host_binding(self):
        request = {"contract": "spike/extension/v1", "context": {
            "design_binding": {"design_id": "board-a", "digest_sha256": "f" * 64},
            "mesh": {"contract": "spike/hybrid-mesh-exchange/v1", "truncated": False,
                     "nodes": [], "branches": [], "cells": []},
            "mesh_preview": {"contract": "spike/mesh/v3", "cells": []},
            "mesh_binding": {"mesh_digest_sha256": "a" * 64,
                             "analysis_spec_digest_sha256": "b" * 64},
            "solver_geometry": {"contract": "spike/solver-geometry/v1"},
            "analysis_spec": {"mode": "si"},
        }}
        exchange = SDK.mesh_exchange(request)
        self.assertEqual(exchange["analysis_spec"]["mode"], "si")
        result = SDK.analysis_result(request, analysis_id="mesh", mode="si",
            model_status="unvalidated", solver="external", summary={})
        self.assertEqual(result["provenance"]["input_mesh_sha256"], "a" * 64)
        self.assertEqual(result["provenance"]["input_analysis_spec_sha256"], "b" * 64)
        request["context"]["mesh"]["truncated"] = True
        with self.assertRaisesRegex(ValueError, "complete mesh"):
            SDK.mesh_exchange(request)

    def test_bound_analysis_round_trip(self):
        request = {"contract": "spike/extension/v1", "context": {
            "design": {"contract": "spike/v1", "design_id": "board-a"},
            "design_binding": {"design_id": "board-a", "digest_sha256": "f" * 64},
        }}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "request.json").write_text(json.dumps(request), encoding="utf-8")
            loaded = SDK.read_request(root / "request.json")
            result = SDK.analysis_result(loaded, analysis_id="demo", mode="dc", model_status="approximate",
                solver="example.external", summary={"max_voltage_v": 1.0},
                visualization={"scalar_fields": {"voltage_v": [{"x_mm": 1, "y_mm": 2, "value": 1.0}]}})
            SDK.write_result(root / "result.json", SDK.analysis_envelope(result, title="Example"))
            saved = json.loads((root / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["data"]["analysis_result"]["provenance"]["design_digest_sha256"], "f" * 64)
        self.assertEqual(saved["data"]["analysis_result"]["fields"]["visualization"]["schema"], "spike/result-visualization/v1")

    def test_missing_binding_and_nonfinite_result_are_rejected(self):
        request = {"context": {}}
        with self.assertRaisesRegex(ValueError, "binding"):
            SDK.analysis_result(request, analysis_id="demo", mode="dc", model_status="approximate", solver="s", summary={})
        request["context"]["design_binding"] = {"design_id": "a", "digest_sha256": "f" * 64}
        with self.assertRaises(ValueError):
            SDK.analysis_result(request, analysis_id="demo", mode="dc", model_status="approximate", solver="s", summary={"bad": float("nan")})


if __name__ == "__main__":
    unittest.main()
