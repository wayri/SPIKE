# SPDX-License-Identifier: Apache-2.0
"""Board admission, EMerge API wiring, and SPIKE analysis-result regression."""

from __future__ import annotations

import json
from pathlib import Path
import types
import unittest

from extensions.emerge_suite.board_adapter import compile_board
from extensions.emerge_suite.capture import theta_cut
from extensions.emerge_suite.extension import execute
from extensions.emerge_suite.normalize import network, radiation
from extensions.emerge_suite.runner import run_case
from python.spike_core.extension_analysis_results import admit_analysis_result
from python.spike_core.extensions import ExtensionManifest, ExtensionRegistry


ROOT = Path(__file__).resolve().parents[2]


def board():
    pads = []
    for name, x, net, layer in (("P1", 0, "RF", "F.Cu"),
                                ("G1", 0, "GND", "B.Cu"),
                                ("P2", 10, "RF", "F.Cu"),
                                ("G2", 10, "GND", "B.Cu")):
        pads.append({"id": name, "net_name": net, "layer": layer,
                     "shape": "rect", "at": [x, 0], "size": [1, 1],
                     "rotation": 0})
    return {"contract": "spike/v1", "design_id": "board-a", "units": "mm",
            "stackup": [{"name": "F.Cu", "type": "copper", "thickness": 0.035},
                        {"name": "dielectric 1", "type": "core", "thickness": 1.0,
                         "epsilon_r": 4.2, "loss_tangent": 0.02},
                        {"name": "B.Cu", "type": "copper", "thickness": 0.035}],
            "tracks": [{"id": "T1", "net_name": "RF", "layer": "F.Cu",
                        "start": [0, 0], "end": [10, 0], "width": 0.4}],
            "pads": pads, "vias": [],
            "zones": [{"id": "Z1", "net_name": "GND", "layer": "B.Cu",
                       "source_kind": "filled_zone", "points": [[-2, -2], [12, -2],
                                                               [12, 2], [-2, 2]]}],
            "metadata": {"board_bounds_mm": [-2, -2, 12, 2]}}


def parameters():
    return {"signal_net": "RF", "return_net": "GND", "signal_pad_id": "P1",
            "return_pad_id": "G1", "receive_signal_pad_id": "P2",
            "receive_return_pad_id": "G2", "frequency_start_hz": 1e9,
            "frequency_stop_hz": 2e9, "frequency_points": 2,
            "mesh_resolution_mm": 0.25}


def backend_result():
    return {"engine_version": "2.8.9", "air_margin_m": 0.05,
            "s_parameters": {"frequencies_hz": [1e9, 2e9], "ports": ["P1", "P2"],
                             "reference_impedance_ohm": 50,
                             "values": [[[[0.2, 0], [0.1, 0]], [[0.5, 0], [0.2, 0]]],
                                        [[[0.3, 0], [0.1, 0]], [[0.4, 0], [0.3, 0]]]]},
            "radiation": {"frequencies_hz": [1e9, 2e9], "cuts": [
                {"frequency_hz": frequency, "angles_deg": [0, 90, 180],
                 "e_theta_v_m": [[1, 0], [2, 0], [0, 0]],
                 "e_phi_v_m": [[0, 0], [0, 0], [0, 0]]}
                for frequency in (1e9, 2e9)], "patterns_3d": [
                {"frequency_hz": frequency, "theta_deg": [0, 90, 180],
                 "phi_deg": [0, 120, 240, 360],
                 "e_theta_v_m": [[1, 0]] * 12, "e_phi_v_m": [[0, 0]] * 12}
                for frequency in (1e9, 2e9)]}}


class EMergeSuiteTests(unittest.TestCase):
    def setUp(self):
        self.request = {"contract": "spike/extension/v1", "request_id": "job-a",
                        "contribution_id": "emerge-radiation", "context": {
                            "design": board(),
                            "design_binding": {"design_id": "board-a", "digest_sha256": "a" * 64},
                            "parameters": parameters()}}

    def test_manifest_and_imported_board_round_trip(self):
        manifest = ExtensionManifest.from_dict(json.loads((ROOT / "extensions" /
            "emerge_suite" / "spike-extension.json").read_text(encoding="utf-8")))
        self.assertTrue(manifest.bundled)
        self.assertEqual(set(manifest.ui["menu_items"]), {"emerge-si", "emerge-radiation"})
        registry = ExtensionRegistry()
        diagnostics = registry.discover([ROOT / "extensions"], trusted_roots=[ROOT / "extensions"])
        self.assertTrue(any(item["id"] == manifest.id and item["status"] == "loaded"
                            for item in diagnostics))
        case = compile_board(board(), parameters())
        self.assertEqual(case["dielectric_thickness_mm"], 1.0)
        self.assertEqual(len(case["polygons"]), 6)
        self.assertEqual(len(case["ports"]), 2)
        output = execute(self.request, backend=lambda *args, **kwargs: backend_result())
        result = output["data"]["analysis_result"]
        admitted = admit_analysis_result(result, self.request["context"]["design_binding"],
                                         extension_id="spike.emerge-suite")
        self.assertEqual(admitted["model_status"], "unvalidated")
        self.assertEqual(result["fields"]["radiation"]["cuts"][0]["relative_amplitude_db"],
                         [-6.020599913279624, 0.0, -300.0])
        self.assertEqual(result["fields"]["radiation"]["patterns_3d"][0]["relative_amplitude_db"], [0.0] * 12)
        self.assertEqual(result["networks"]["s_parameters"]["values"][0][1][0], [0.5, 0.0])
        self.assertTrue(any(issue["code"] == "EMERGE_DIELECTRIC_LOSS_OMITTED"
                            for issue in result["issues"]))

    def test_si_requires_no_radiation_and_preserves_s_parameters(self):
        self.request["contribution_id"] = "emerge-si"
        called = []
        def backend(case, *, radiation_requested, python_executable):
            called.append(radiation_requested)
            value = backend_result()
            del value["radiation"]
            return value
        result = execute(self.request, backend=backend)["data"]["analysis_result"]
        self.assertEqual(called, [False])
        self.assertEqual(result["mode"], "si")
        self.assertNotIn("radiation", result["fields"])

    def test_runtime_probe_reports_available_capabilities(self):
        self.request["contribution_id"] = "emerge-probe"
        self.request["context"] = {"parameters": {"python_executable": "C:/runtime/python.exe"}}
        received = []
        def probe(path):
            received.append(path)
            return {"available": True, "version": "2.8.9",
                    "capabilities": ["si_s_parameters", "radiation_pattern"]}
        result = execute(self.request, probe=probe)
        self.assertEqual(received, ["C:/runtime/python.exe"])
        self.assertEqual(result["data"]["capabilities"], ["si_s_parameters", "radiation_pattern"])

    def test_unsupported_geometry_and_bad_ports_fail_before_engine(self):
        altered = board()
        altered["vias"].append({"id": "V1", "net_name": "RF"})
        with self.assertRaisesRegex(ValueError, "vias"):
            compile_board(altered, parameters())
        altered = board()
        altered["zones"][0]["source_kind"] = "zone_outline_fallback"
        with self.assertRaisesRegex(ValueError, "verified filled"):
            compile_board(altered, parameters())
        altered = board()
        altered["pads"][1]["at"] = [0.2, 0]
        with self.assertRaisesRegex(ValueError, "align"):
            compile_board(altered, parameters())
        altered = parameters()
        altered["receive_return_pad_id"] = ""
        with self.assertRaisesRegex(ValueError, "Second port"):
            compile_board(board(), altered)
        altered = parameters()
        altered["mesh_resolution_mm"] = 0.05
        large = board()
        large["metadata"]["board_bounds_mm"] = [0, 0, 200, 200]
        with self.assertRaisesRegex(ValueError, "planar preflight budget"):
            compile_board(large, altered)

    def test_explicit_source_short_and_attributed_copper_are_disclosed(self):
        reduced = board()
        reduced["vias"] = [{"id": "V1", "net_name": "GND", "at": [9, 0],
                            "layers": ["F.Cu", "B.Cu"], "size": 0.6, "drill": 0.3}]
        reduced["zones"].append({"id": "A1", "net_name": "RF", "layer": "F.Cu",
                                 "source_kind": "attributed_graphic_polygon", "source_original_net_name": "",
                                 "attribution_reason": "reviewed radiator graphic touching source feed",
                                 "points": [[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]})
        params = {**parameters(), "shorting_via_ids": ["V1"]}
        case = compile_board(reduced, params)
        self.assertEqual(case["shorting_vias"][0]["radius_mm"], 0.3)
        self.assertEqual(case["attributed_graphic_polygon_ids"], ["A1"])
        self.assertEqual(len(case["polygons"][-1]["xs_mm"]), 4)
        with self.assertRaisesRegex(ValueError, "not explicitly admitted"):
            compile_board(reduced, parameters())
        reduced["zones"][-1]["attribution_reason"] = ""
        with self.assertRaisesRegex(ValueError, "attribution reason"):
            compile_board(reduced, params)

    def test_dielectric_surroundings_are_bounded_and_result_is_traceable(self):
        params = parameters()
        params["surrounding_geometry"] = {"contract": "spike/emerge-surroundings/v1", "objects": [
            {"kind": "dielectric_box", "name": "Cover", "origin_mm": [-3, -3, 10],
             "size_mm": [16, 6, 1.5], "epsilon_r": 2.1}]}
        case = compile_board(board(), params)
        self.assertEqual(case["surrounding_geometry"][0]["origin_mm"], [-3.0, -3.0, 10.0])
        self.request["context"]["parameters"] = params
        result = execute(self.request, backend=lambda *args, **kwargs: backend_result())["data"]["analysis_result"]
        self.assertEqual(result["provenance"]["surrounding_geometry"], case["surrounding_geometry"])
        self.assertTrue(any(issue["code"] == "EMERGE_SURROUNDINGS_UNVALIDATED" for issue in result["issues"]))
        params["surrounding_geometry"]["objects"][0]["origin_mm"][2] = 0
        with self.assertRaisesRegex(ValueError, "above top copper"):
            compile_board(board(), params)
        params["surrounding_geometry"]["objects"][0]["origin_mm"][2] = 10
        params["surrounding_geometry"]["objects"][0]["size_mm"][2] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            compile_board(board(), params)
        params["surrounding_geometry"]["objects"][0]["size_mm"] = [100, 100, 20]
        with self.assertRaisesRegex(ValueError, "volume"):
            compile_board(board(), params)

    def test_malformed_solver_arrays_rejected(self):
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            radiation({"frequencies_hz": [2, 1], "cuts": []})
        with self.assertRaisesRegex(ValueError, "finite"):
            network({"frequencies_hz": [1], "ports": ["P1"],
                     "reference_impedance_ohm": 50,
                     "values": [[[[float("nan"), 0]]]]})
        wrong = backend_result()
        wrong["s_parameters"]["frequencies_hz"] = [1e9, 3e9]
        with self.assertRaisesRegex(ValueError, "does not match"):
            execute(self.request, backend=lambda *args, **kwargs: wrong)
        wrong = backend_result()
        wrong["radiation"]["patterns_3d"][0]["e_theta_v_m"] = [[1, 0]] * 11
        with self.assertRaisesRegex(ValueError, "match the angular grid"):
            execute(self.request, backend=lambda *args, **kwargs: wrong)

    def test_generated_case_calls_emerge_api_with_metre_ports(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("NumPy needed for EMerge runner")
        calls = []
        class PCB:
            def z(self, index): return -1.0 if index == 0 else 0.0
            def add_poly(self, xs, ys, **kwargs): calls.append(("poly", kwargs["z"]))
            def compile_paths(self, **kwargs): return "traces"
            def set_bounds(self, *value): calls.append(("bounds", value))
            def generate_pcb(self, **kwargs): return "substrate"
        class Air:
            def background(self): return self
            def boundary(self): return "air-boundary"
        class Grid:
            freq = np.asarray([1e9, 2e9])
            def S(self, receive, excited): return np.asarray([0.1 * receive + 0j, 0.2 * excited + 0j])
        class Field:
            def farfield(self, theta, phi, faces, origin=None):
                return np.asarray([[1+0j] * len(theta), [0j] * len(theta),
                                   [0j] * len(theta)]), None, None
        class MW:
            bc = types.SimpleNamespace(
                LumpedPort=lambda *args, **kwargs: calls.append(("port", args, kwargs)),
                AbsorbingBoundary=lambda value: calls.append(("absorbing", value)))
            def set_frequency_range(self, *args): calls.append(("frequency", args))
            def run_sweep(self):
                calls.append(("solve",))
                return types.SimpleNamespace(scalar=types.SimpleNamespace(grid=Grid()),
                    field=types.SimpleNamespace(find=lambda **kwargs: Field()))
        class Simulation:
            mw = MW()
            mesher = types.SimpleNamespace(set_boundary_size=lambda *args: None,
                                          set_face_size=lambda *args: None)
            def __init__(self, name): pass
            def commit_geometry(self): calls.append(("commit",))
            def generate_mesh(self): calls.append(("mesh",))
        em = types.SimpleNamespace(__version__="2.8.9", Simulation=Simulation,
            Material=lambda value: value, lib=types.SimpleNamespace(PEC="PEC"), ZAX="Z",
            geo=types.SimpleNamespace(PCBNew=lambda *args, **kwargs: PCB(),
                Plate=lambda *args: calls.append(("plate", args)) or "plate",
                open_region=lambda *args: Air()))
        raw = run_case(compile_board(board(), parameters()), em, radiation=True)
        self.assertEqual(len(raw["radiation"]["cuts"]), 2)
        self.assertEqual(len(raw["radiation"]["patterns_3d"]), 2)
        self.assertEqual(len(raw["radiation"]["patterns_3d"][0]["e_theta_v_m"]), 13 * 25)
        self.assertEqual(sum(call[0] == "port" for call in calls), 2)
        first_plate = next(call for call in calls if call[0] == "plate")
        self.assertAlmostEqual(first_plate[1][0][2], -0.001)
        self.assertIn(("absorbing", "air-boundary"), calls)
        self.assertLess(calls.index(("mesh",)), next(i for i, call in enumerate(calls) if call[0] == "port"))

    def test_emerge_3_farfield_object_uses_cartesian_samples(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("NumPy needed for far-field projection")

        class Field:
            def farfield(self, theta, phi, faces, origin=None):
                return types.SimpleNamespace(
                    Ex=np.asarray([1 + 0j] * len(theta)),
                    Ey=np.asarray([0j] * len(theta)),
                    Ez=np.asarray([0j] * len(theta)))

        cut = theta_cut(Field(), object(), 3e9, [0, 90, 180])
        self.assertAlmostEqual(cut["e_theta_v_m"][0][0], 1.0)
        self.assertAlmostEqual(cut["e_theta_v_m"][1][0], 0.0, places=12)
        self.assertAlmostEqual(cut["e_theta_v_m"][2][0], -1.0)


if __name__ == "__main__":
    unittest.main()
