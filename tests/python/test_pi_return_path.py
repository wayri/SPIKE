# SPDX-License-Identifier: Apache-2.0
"""Original analytical fixtures for approximate copper routing; no board qualification."""

from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from python.spike_core.contracts import ValidationIssue
from python.spike_core.hybrid_mesh import HybridMesh, MeshBranch, MeshNode
from python.spike_core.pi_return_path import plan_pi_return_path


def design():
    return {"contract": "spike/v1", "units": "mm", "layers": [{"name": "F.Cu"}],
            "nets": [{"id": "1", "name": "VCC"}, {"id": "2", "name": "GND"}],
            "stackup": [{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
            "pads": [{"id": identity, "net_id": "2", "at": [x, 0], "size": [1, 1],
                      "shape": "rect", "layers": ["F.Cu"]} for identity, x in (("source", 0), ("load", 10))],
            "tracks": [{"id": "track", "net_id": "2", "start": [0, 0], "end": [10, 0], "width": 1, "layer": "F.Cu"}]}


def request():
    return {"contract": "spike/pi-return-path-request/v1", "occurrence_id": "board-1", "forward_net": "VCC",
            "return_net": "GND", "source_pad_id": "source", "load_pad_ids": ["load"], "mesh_target_mm": 1.0}


class PiReturnPathTests(unittest.TestCase):
    def blocked(self, board, req, code):
        result = plan_pi_return_path(board, req)
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["paths"], [])
        self.assertIn(code, [issue["code"] for issue in result["issues"]])
        json.dumps(result, allow_nan=False)

    def test_actual_mesh_line_matches_resistivity_and_refinement(self):
        # L=10 mm, w=1 mm, t=35 um, sigma=5.8e7 S/m.
        expected = 0.010 / (5.8e7 * 0.001 * 35e-6)
        board = design()
        original = deepcopy(board)
        for target in (2.0, 1.0, 0.5, 0.25):
            with self.subTest(target=target):
                req = dict(request(), mesh_target_mm=target)
                result = plan_pi_return_path(board, req)
                self.assertEqual(result["status"], "connected", result)
                route = result["paths"][0]
                self.assertAlmostEqual(route["resistance_ohm"], expected, delta=1e-12)
                self.assertAlmostEqual(route["length_mm"], 10.0, delta=1e-12)
                self.assertEqual(route["points_mm"][0], [0, 0, -0.0175])
                self.assertEqual(route["points_mm"][-1], [10, 0, -0.0175])
                self.assertEqual(result["model_status"], "approximate")
                self.assertEqual(result["request"], req)
                json.dumps(result, allow_nan=False)
        self.assertEqual(board, original)

    def test_actual_mesh_disconnected_does_not_snap_across_empty_space(self):
        board = design()
        board["tracks"] = []
        result = plan_pi_return_path(board, request())
        self.assertEqual(result["status"], "disconnected", result)
        self.assertEqual(result["paths"], [{"load_pad_id": "load", "connected": False,
                         "resistance_ohm": None, "length_mm": None, "points_mm": []}])
        self.assertNotIn("proposals", result)

    def test_parallel_graph_chooses_resistance_not_geometric_distance(self):
        # Direct 10 mm route = 10 ohm; two 7.071 mm segments = 2 ohm.
        # The parallel equivalent would be 5/3 ohm, which must NOT be reported.
        nodes = [MeshNode(i, x, y, 0, "F.Cu", "GND") for i, (x, y) in enumerate(((0, 0), (5, 5), (10, 0)))]
        branches = []
        for index, (a, b, resistance) in enumerate(((0, 2, 10), (0, 1, 1), (1, 2, 1))):
            p = (nodes[a].x_mm, nodes[a].y_mm, 0)
            q = (nodes[b].x_mm, nodes[b].y_mm, 0)
            sigma = math.dist(p, q) * 1e3 / resistance  # area=1 mm^2
            branches.append(MeshBranch(str(index), "track", a, b, p, q, 1, 1, sigma, "F.Cu", "GND", "track"))
        mesh = HybridMesh(nodes=nodes, branches=branches, cells=[
            {"source_kind": "pad", "source_id": "source", "node_id": 0},
            {"source_kind": "pad", "source_id": "load", "node_id": 2}])
        with patch("python.spike_core.pi_return_path.build_hybrid_mesh", return_value=mesh):
            result = plan_pi_return_path(design(), request())
        self.assertEqual(result["status"], "connected", result)
        route = result["paths"][0]
        self.assertAlmostEqual(route["resistance_ohm"], 2.0)
        self.assertAlmostEqual(route["length_mm"], math.sqrt(200))
        self.assertEqual(route["points_mm"][1], [5, 5, 0])

    def test_actual_filled_zone_respects_explicit_pad_isolation(self):
        board = design()
        board["tracks"] = []
        board["zones"] = [{"id": "plane", "points": [[-1, -1], [11, -1], [11, 1], [-1, 1]],
                           "layer": "F.Cu", "net_name": "GND", "source_zone_id": "source-plane",
                           "filled_copper_id": "plane", "zone_kind": "copper", "filled_copper_state": "source_filled",
                           "zone_connection_default": "solid", "zone_connection_declared": True,
                           "clearance_mm": 0.2, "thermal_gap_mm": 0.2, "thermal_spoke_width_mm": 0.2,
                           "fill_mode": "solid", "thermal_settings_valid": True}]
        for pad in board["pads"]:
            pad.update(pad_kind="smd", zone_connection_override="solid", zone_connection_declared=True,
                       zone_connection_layer_overrides={}, thermal_settings_valid=True)
        connected = plan_pi_return_path(board, request())
        self.assertEqual(connected["status"], "connected", connected)
        self.assertGreater(connected["paths"][0]["resistance_ohm"], 0)
        board["pads"][1]["zone_connection_override"] = "none"
        isolated = plan_pi_return_path(board, request())
        self.assertEqual(isolated["status"], "disconnected", isolated)

    def test_mixed_loads_preserve_disconnected_result_and_order(self):
        board = design()
        board["pads"].append(dict(deepcopy(board["pads"][1]), id="island", at=[20, 0]))
        result = plan_pi_return_path(board, dict(request(), load_pad_ids=["island", "load"]))
        self.assertEqual(result["status"], "disconnected", result)
        self.assertEqual([p["load_pad_id"] for p in result["paths"]], ["island", "load"])
        self.assertEqual([p["connected"] for p in result["paths"]], [False, True])

    def test_request_rejections(self):
        cases = [("mesh_target_mm", value, "PI_RETURN_MESH_TARGET") for value in (0, -1, 0.001, 1001, math.inf, math.nan, True, "1")]
        cases += [("load_pad_ids", value, code) for value, code in [([], "PI_RETURN_LOAD_LIMIT"), (["load"] * 33, "PI_RETURN_LOAD_LIMIT"),
                  (["load", "load"], "PI_RETURN_TERMINAL_IDENTITY"), (["source"], "PI_RETURN_TERMINAL_IDENTITY"),
                  (["foreign"], "PI_RETURN_UNKNOWN_PAD")]]
        cases += [("forward_net", "missing", "PI_RETURN_UNKNOWN_NET"), ("forward_net", "GND", "PI_RETURN_NET_IDENTITY"),
                  ("occurrence_id", "", "PI_RETURN_REQUEST_IDENTITY"), ("contract", "bad", "PI_RETURN_REQUEST_CONTRACT")]
        for key, value, code in cases:
            with self.subTest(key=key, value=value):
                self.blocked(design(), dict(request(), **{key: value}), code)
        self.blocked(design(), dict(request(), extra=1), "PI_RETURN_REQUEST_CONTRACT")

    def test_pad_ownership_and_actual_net_mapping(self):
        board = design()
        board["pads"].append(deepcopy(board["pads"][0]))
        self.blocked(board, request(), "PI_RETURN_PAD_IDENTITY")
        board = design()
        board["pads"][1]["net_id"] = "1"
        self.blocked(board, request(), "PI_RETURN_PAD_NET_MISMATCH")
        board["pads"][1]["net_name"] = "GND"
        self.blocked(board, request(), "PI_RETURN_NET_MAPPING")
        board = design()
        board["occurrence_id"] = "foreign"
        self.blocked(board, request(), "PI_RETURN_OCCURRENCE_MISMATCH")
        board = design()
        board["tracks"][0]["id"] = "source"
        self.blocked(board, request(), "PI_RETURN_GEOMETRY_IDENTITY")

    def test_geometry_bounds_and_nonfinite(self):
        board = design()
        board["pads"][0]["at"][0] = math.nan
        self.blocked(board, request(), "PI_RETURN_NONFINITE_INPUT")
        board = design()
        board["tracks"][0]["width"] = -1
        self.blocked(board, request(), "PI_RETURN_DESIGN_GEOMETRY")
        board = design()
        board["tracks"][0]["end"][0] = 1e6
        self.blocked(board, request(), "PI_RETURN_MESH_LIMIT")
        board = design()
        board["pads"][0]["shape"] = "roundrect"
        self.blocked(board, request(), "PI_RETURN_PAD_SHAPE_UNSUPPORTED")
        board = design()
        board["zones"] = [{"id": "zone", "net_name": "GND", "layer": "F.Cu", "points": [[0, 0], [10, 0], [10, 10]]}]
        self.blocked(board, request(), "PI_RETURN_ZONE_FILL_REQUIRED")
        board = design()
        board["pads"][0]["size"] = [1e6, 0.001]
        self.blocked(board, request(), "PI_RETURN_MESH_LIMIT")
        board = design()
        del board["tracks"][0]["id"]
        self.blocked(board, request(), "PI_RETURN_GEOMETRY_IDENTITY")

    def test_incomplete_and_invalid_mesh_blocked(self):
        for mesh, code in [(HybridMesh(truncated=True), "PI_RETURN_MESH_BLOCKED"),
                           (HybridMesh(issues=[ValidationIssue("TEST", "error", "Bad mesh")]), "PI_RETURN_MESH_BLOCKED"),
                           (HybridMesh(), "PI_RETURN_PAD_UNMESHED"),
                           (HybridMesh(nodes=[MeshNode(0, 0, 0, 0, "F.Cu", "VCC")]), "PI_RETURN_INVALID_MESH")]:
            with self.subTest(code=code), patch("python.spike_core.pi_return_path.build_hybrid_mesh", return_value=mesh):
                self.blocked(design(), request(), code)


if __name__ == "__main__":
    unittest.main()
