# SPDX-License-Identifier: Apache-2.0
"""Mesh-only topology, preview binding and absence of a field solve."""
import json
import os
from pathlib import Path
import types
import unittest

import numpy as np

from extensions.emerge_suite.board_adapter import compile_board
from extensions.emerge_suite.extension import execute
from extensions.emerge_suite.mesh_capture import capture_mesh
from extensions.emerge_suite.mesh_extension import design_digest, normalize_mesh
from extensions.emerge_suite.runner import run_case
from tests.python.test_emerge_suite_extension import board, parameters


def public_mesh():
    return types.SimpleNamespace(
        nodes=np.asarray([[0., .001, 0., 0.], [0., 0., .001, 0.], [0., 0., 0., .001]]),
        tets=np.asarray([[0], [1], [2], [3]]),
        tris=np.asarray([[0, 0, 0, 1], [1, 1, 2, 2], [2, 3, 3, 3]]),
        vtag_to_tet={1: np.asarray([0])}, ftag_to_tri={2: np.arange(4)})


class EMergeMeshTests(unittest.TestCase):
    def request(self, contribution="emerge-mesh-preview"):
        design = board()
        return {"contract": "spike/extension/v1", "request_id": "mesh-test",
                "contribution_id": contribution, "context": {"design": design,
                "design_binding": design_digest(design), "parameters": parameters()}}

    def test_public_meter_arrays_preserve_connectivity_and_volume(self):
        result = capture_mesh(public_mesh())
        self.assertEqual(result["nodes_mm"][1], [1., 0., 0.])
        self.assertEqual(result["tetrahedra"], [[0, 1, 2, 3]])
        self.assertEqual(result["bounds_mm"], [0., 0., 0., 1., 1., 1.])
        self.assertAlmostEqual(result["quality"]["minimum_absolute_volume_mm3"], 1/6)
        self.assertEqual(normalize_mesh(result), result)
        self.assertFalse(result["solved"])

    def test_malformed_and_degenerate_topology_is_rejected(self):
        for mutate in (lambda m: setattr(m, "tets", np.asarray([[0], [1], [2], [4]])),
                       lambda m: setattr(m, "tets", m.tets.astype(float)),
                       lambda m: setattr(m, "tets", np.asarray([[0], [1], [2], [2]])),
                       lambda m: setattr(m, "tets", np.repeat(m.tets, 2, axis=1)),
                       lambda m: setattr(m, "nodes", np.zeros((3, 4))),
                       lambda m: setattr(m, "vtag_to_tet", {1: np.asarray([1])}),
                       lambda m: setattr(m, "nodes", np.full((3, 4), np.nan))):
            with self.subTest(mutate=mutate):
                mesh = public_mesh()
                mutate(mesh)
                with self.assertRaises(ValueError): capture_mesh(mesh)
        with self.assertRaisesRegex(ValueError, "public Mesh3D"):
            capture_mesh(types.SimpleNamespace())
        result = capture_mesh(public_mesh())
        result["node_count"] += 1
        with self.assertRaisesRegex(ValueError, "counts"):
            normalize_mesh(result)

    def test_preview_required_and_changed_design_or_settings_fail_before_engine(self):
        request = self.request()
        preview = execute(request, backend=lambda *a, **kw: self.fail("preview ran engine"))
        request["contribution_id"] = "emerge-mesh"
        with self.assertRaisesRegex(ValueError, "preview"):
            execute(request, backend=lambda *a, **kw: self.fail("missing preview ran engine"))
        request["context"]["parameters"]["expected_generated_script_sha256"] = preview["data"]["script_sha256"]
        request["context"]["parameters"]["mesh_resolution_mm"] = .5
        with self.assertRaisesRegex(ValueError, "preview"):
            execute(request, backend=lambda *a, **kw: self.fail("changed mesh ran engine"))
        request["context"]["design_binding"]["digest_sha256"] = "a"*64
        with self.assertRaisesRegex(ValueError, "binding"):
            execute(request, backend=lambda *a, **kw: self.fail("stale design ran engine"))

    def test_mesh_result_is_bound_and_never_an_analysis_result(self):
        request = self.request()
        preview = execute(request)
        request["contribution_id"] = "emerge-mesh"
        request["context"]["parameters"]["expected_generated_script_sha256"] = preview["data"]["script_sha256"]
        def engine(case, **kw):
            self.assertTrue(kw["mesh_only"])
            self.assertFalse(kw["radiation_requested"])
            return {"engine_version": "3.0.0a19", "mesh": capture_mesh(public_mesh()), "air_margin_m": .03}
        result = execute(request, backend=engine)
        self.assertNotIn("analysis_result", result["data"])
        mesh = result["data"]["mesh_result"]
        self.assertEqual(mesh["provenance"]["generated_script_sha256"], preview["data"]["script_sha256"])
        self.assertEqual(mesh["provenance"]["case_sha256"], preview["data"]["case_sha256"])
        self.assertEqual(mesh["provenance"]["operation"], "mesh_only")
        self.assertFalse(mesh["solved"])

    def test_runner_stops_after_meshing_without_bc_or_sweep(self):
        calls = []
        class PCB:
            def z(self, i): return -1 if i == 0 else 0
            def add_poly(self, *a, **kw): pass
            def compile_paths(self, **kw): return "traces"
            def set_bounds(self, *a): pass
            def generate_pcb(self, **kw): pass
        class Simulation:
            mesh = public_mesh()
            mw = types.SimpleNamespace(set_frequency_range=lambda *a: None)
            mesher = types.SimpleNamespace(set_boundary_size=lambda *a: None, set_face_size=lambda *a: None)
            def __init__(self, name): pass
            def commit_geometry(self): calls.append("commit")
            def generate_mesh(self): calls.append("mesh")
        em = types.SimpleNamespace(__version__="2.8.9", Simulation=Simulation,
            Material=lambda *a, **kw: None, lib=types.SimpleNamespace(PEC="PEC"),
            geo=types.SimpleNamespace(PCBNew=lambda *a, **kw: PCB(), Plate=lambda *a: "port",
                open_region=lambda *a: types.SimpleNamespace(background=lambda: "air")))
        # MW has neither bc nor run_sweep: any solve/boundary call fails the test.
        result = run_case(compile_board(board(), parameters()), em, radiation=False, mesh_only=True)
        self.assertEqual(calls, ["commit", "mesh"])
        self.assertEqual(result["mesh"]["tetrahedron_count"], 1)

    @unittest.skipUnless(os.environ.get("SPIKE_EMERGE_MESH_INTEGRATION") == "1", "optional real EMerge runtime")
    def test_real_original_antenna_mesh_coordinates_and_dielectric_volume(self):
        from python.spike_core.extension_mesh_results import admit_extension_mesh
        from python.spike_core.kicad_importer import import_kicad_design
        root = Path(__file__).resolve().parents[2]
        config = json.loads((root/"examples/emerge/antenna_run.json").read_text())
        design = json.loads(json.dumps(import_kicad_design(str(root/config["board"])).to_dict()))
        params = config["parameters"]
        params["python_executable"] = os.environ.get(
            "SPIKE_EMERGE_TEST_PYTHON", str(root/".venv-emerge3/Scripts/python.exe"),
        )
        request = self.request()
        request["context"] = {"design": design, "parameters": params, "design_binding": design_digest(design)}
        preview = execute(request)
        request["contribution_id"] = "emerge-mesh"
        params["expected_generated_script_sha256"] = preview["data"]["script_sha256"]
        mesh = admit_extension_mesh(execute(request)["data"]["mesh_result"], design_digest(design), extension_id="spike.emerge-suite")
        np.testing.assert_allclose(mesh["bounds_mm"], [80, 80, -21.6, 160, 150, 20], atol=.001, rtol=0)
        nodes = np.asarray(mesh["nodes_mm"])
        tets = nodes[np.asarray(mesh["tetrahedra"])]
        volumes = abs(np.linalg.det(tets[:, 1:]-tets[:, :1]))/6
        # Original board is a 40 x 30 x 1.6 mm dielectric rectangular solid.
        group_volumes = [float(volumes[group["indices"]].sum()) for group in mesh["volume_groups"]]
        self.assertTrue(any(abs(value-1920) < 1e-5 for value in group_volumes), group_volumes)
        self.assertGreater(mesh["tetrahedron_count"], 1000)
        self.assertFalse(mesh["admission"]["physics_validated"])
        self.assertFalse(mesh["admission"]["cross_engine_reuse"])


if __name__ == "__main__": unittest.main()
