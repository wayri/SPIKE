# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from python.spike_core.solvers.geometry_meshing.preparation.internal_meshing_engine import CONTROL_LIMIT_BYTES, internal_mesh_capabilities, run_internal_meshing
from python.spike_core.service_meshing import handle_meshing_request
from python.spike_core.solvers.geometry_meshing.preparation.tetra_mesh_refinement import TetraRefinementError


ROOT = Path(__file__).resolve().parents[2]


def example():
    return json.loads((ROOT / "examples/internal_meshing/noncuboidal.json").read_text(encoding="utf-8"))


class InternalMeshEngineTests(unittest.TestCase):
    def test_generation_digests_and_immutable_request(self):
        request = example()
        original = copy.deepcopy(request)
        result = run_internal_meshing(request)
        self.assertEqual(request, original)
        self.assertFalse(result["production_qualified"])
        mesh_bytes = json.dumps(result["candidate"]["mesh"], sort_keys=True,
                                separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
        self.assertEqual(result["mesh_sha256"], hashlib.sha256(mesh_bytes).hexdigest())
        self.assertEqual(result, run_internal_meshing(request))

    def test_capabilities_are_bounded_and_explicit(self):
        cap = internal_mesh_capabilities()
        self.assertEqual(cap["status"], "experimental")
        self.assertFalse(cap["external_mesher_required"])
        self.assertIn("nonconvex_CAD_generation", cap["unsupported"])
        self.assertEqual(cap["limits"]["control_bytes"], CONTROL_LIMIT_BYTES)

    def test_adaptation_worker_and_transfer(self):
        source = run_internal_meshing(example())["candidate"]
        mesh = source["mesh"]
        field = [2 + p[0] - 3*p[1] + .5*p[2] for p in mesh["vertices"]]
        request = {"contract": "spike/internal-mesh-request/v1", "operation": "adapt", "parameters": {
            "mesh": mesh, "boundary_triangles": source["boundary_triangles"],
            "manual_edges": [mesh["cells"][0]["vertices"][:2]], "optimize": False,
            "nodal_fields": {"temperature": field},
        }}
        result = handle_meshing_request("run_internal_meshing", {"request": request})
        self.assertTrue(result["ok"], result)
        self.assertGreater(result["result"]["candidate"]["mesh"]["counts"]["cells"], mesh["counts"]["cells"])

    def test_optimization_worker(self):
        source = run_internal_meshing(example())["candidate"]
        request = {"contract": "spike/internal-mesh-request/v1", "operation": "optimize", "parameters": {
            "mesh": source["mesh"], "boundary_triangles": source["boundary_triangles"]}}
        result = run_internal_meshing(request)["candidate"]
        self.assertGreaterEqual(result["quality"]["after"]["minimum_mean_ratio"],
                                result["quality"]["before"]["minimum_mean_ratio"])

    def test_unknown_fields_and_contract_rejected(self):
        for change in ({"unexpected": 1}, {"contract": "spike/rom-package/v1"},
                       {"operation": "shell"}, {"parameters": {"points": [], "executable": "mesher"}}):
            request = {**example(), **change}
            with self.subTest(change=change), self.assertRaises(TetraRefinementError):
                run_internal_meshing(request)

    def test_nonfinite_and_oversize(self):
        for value in (float("nan"), float("inf"), True):
            request = example()
            request["parameters"]["points"][0][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                run_internal_meshing(request)
        with self.assertRaisesRegex(TetraRefinementError, "8 MiB"):
            run_internal_meshing({"padding": "x" * CONTROL_LIMIT_BYTES})

    def test_worker_rejections_are_structured(self):
        self.assertIsNone(handle_meshing_request("unknown", {}))
        self.assertTrue(handle_meshing_request("internal_mesh_capabilities", {})["ok"])
        for method, params in (("run_internal_meshing", {}),
                               ("run_internal_meshing", {"request": example(), "executable": "bad"}),
                               ("internal_mesh_capabilities", {"extra": 1})):
            result = handle_meshing_request(method, params, request_id="mesh-fixture")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "SPIKE-BE-IPC-E-0001")

    def test_schema_golden_and_unknown_parameters(self):
        from jsonschema import Draft202012Validator
        schema = json.loads((ROOT / "schemas/internal-mesh-request-v1.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        validator.validate(example())
        request = example()
        request["parameters"]["unexpected"] = True
        self.assertTrue(list(validator.iter_errors(request)))

    def test_json_line_worker_process(self):
        requests = [{"id": "probe", "method": "internal_mesh_capabilities", "params": {}},
                    {"id": "generate", "method": "run_internal_meshing",
                     "params": {"request": example()}}]
        process = subprocess.run([sys.executable, "-m", "python.spike_core.service"],
                                 input="".join(json.dumps(item)+"\n" for item in requests),
                                 text=True, capture_output=True, cwd=ROOT, timeout=45)
        self.assertEqual(process.returncode, 0, process.stderr)
        results = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([item["id"] for item in results], ["probe", "generate"])
        self.assertTrue(all(item["ok"] for item in results), results)
        self.assertEqual(results[1]["result"]["candidate"]["mesh"]["counts"]["vertices"], 5)

    def test_field_budget_is_enforced_by_decoder(self):
        candidate = run_internal_meshing(example())["candidate"]
        request = {"contract": "spike/internal-mesh-request/v1", "operation": "adapt", "parameters": {
            "mesh": candidate["mesh"], "boundary_triangles": candidate["boundary_triangles"],
            "optimize": False, "nodal_fields": {str(i): [0.]*5 for i in range(33)}}}
        with self.assertRaises(TetraRefinementError):
            run_internal_meshing(request)


if __name__ == "__main__":
    unittest.main()
