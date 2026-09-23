import unittest

import numpy as np

from python.spike_core.contracts import AnalysisSpec
from python.spike_core.hybrid_mesh import HybridMesh, MeshBranch, MeshNode
from python.spike_core.loop_parasitics import (
    extract_loop_parasitics,
    solve_coupled_path_currents,
)


def branch(identifier, node_p, node_n, y_mm, net):
    return MeshBranch(
        identifier,
        "track",
        node_p,
        node_n,
        (0.0, y_mm, 0.0),
        (10.0, y_mm, 0.0),
        1.0,
        0.035,
        5.8e7,
        "F.Cu",
        net,
        identifier,
    )


class FakeResistanceSolver:
    def compute_resistance(self, _frequency):
        return np.diag([0.010, 0.012])


class CoupledLoopTests(unittest.TestCase):
    def setUp(self):
        self.mesh = HybridMesh(
            nodes=[
                MeshNode(0, 0.0, 0.0, 0.0, "F.Cu", "VIN"),
                MeshNode(1, 10.0, 0.0, 0.0, "F.Cu", "VIN"),
                MeshNode(2, 0.0, 1.0, 0.0, "F.Cu", "GND"),
                MeshNode(3, 10.0, 1.0, 0.0, "F.Cu", "GND"),
            ],
            branches=[
                branch("forward", 0, 1, 0.0, "VIN"),
                branch("return", 2, 3, 1.0, "GND"),
            ],
        )
        self.paths = [
            {"node_ids": [0, 1], "branch_indices": [0], "start_node": 0, "end_node": 1},
            {"node_ids": [2, 3], "branch_indices": [1], "start_node": 3, "end_node": 2},
        ]

    def test_mutual_inductance_is_subtracted_for_opposing_return_current(self):
        frequency = 1e6
        omega = 2.0 * np.pi * frequency
        self_inductance = 10e-9
        mutual_inductance = 4e-9
        impedance_matrix = np.diag([0.010, 0.012]).astype(complex) + 1j * omega * np.asarray([
            [self_inductance, mutual_inductance],
            [mutual_inductance, self_inductance],
        ])

        impedance, currents, quality = solve_coupled_path_currents(
            self.mesh,
            self.paths,
            [0, 1],
            impedance_matrix,
            diagnostics=True,
        )

        np.testing.assert_allclose(currents, [1.0, -1.0], rtol=1e-12, atol=1e-12)
        self.assertAlmostEqual(impedance.real, 0.022, places=12)
        self.assertAlmostEqual(impedance.imag / omega, 12e-9, places=15)
        self.assertLess(quality["relative_residual"], 1e-12)

    def test_explicit_pad_to_pad_request_emits_loop_contract_and_components(self):
        frequencies = np.asarray([1e3, 1e6])
        spec = AnalysisSpec(
            mode="ac",
            return_path={"mode": "explicit", "net": "GND"},
            options={
                "loop_extractions": [{
                    "id": "vin-loop",
                    "forward": {
                        "net": "VIN",
                        "source": {"position_mm": [0.0, 0.0], "layer": "F.Cu"},
                        "load": {"position_mm": [10.0, 0.0], "layer": "F.Cu"},
                    },
                    "return": {
                        "net": "GND",
                        "load": {"position_mm": [10.0, 1.0], "layer": "F.Cu"},
                        "source": {"position_mm": [0.0, 1.0], "layer": "F.Cu"},
                    },
                    "component_models": [{
                        "id": "L1",
                        "reference": "L1",
                        "model_kind": "linear_rlc",
                        "topology": "series",
                        "resistance_ohm": 0.003,
                        "inductance_h": 5e-9,
                        "capacitance_f": 2e-9,
                        "reviewed": True,
                        "input_pins": ["1"],
                        "output_pins": ["2"],
                        "geometry_center_mm": [5.0, 0.5],
                    }],
                }]
            },
        )
        inductance = np.asarray([[10e-9, 4e-9], [4e-9, 10e-9]])
        branch_capacitance = np.asarray([20e-12, 0.0])

        results, issues, currents = extract_loop_parasitics(
            self.mesh,
            spec,
            FakeResistanceSolver(),
            inductance,
            branch_capacitance,
            frequencies,
        )

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["contract"], "spike/loop-parasitics/v1")
        self.assertAlmostEqual(result["geometry_loop_inductance_h"], 12e-9, places=15)
        self.assertAlmostEqual(result["total_loop_inductance_h"], 17e-9, places=15)
        self.assertAlmostEqual(result["component_series_capacitance_f"], 2e-9, places=15)
        self.assertAlmostEqual(result["estimated_net_capacitance_f"], 20e-12, places=18)
        self.assertEqual(result["component_models"][0]["input_pins"], ["1"])
        self.assertEqual(result["component_models"][0]["output_pins"], ["2"])
        self.assertEqual(result["component_models"][0]["geometry_center_mm"], [5.0, 0.5])
        self.assertAlmostEqual(result["impedance"][0]["resistance_ohm"], 0.025, places=12)
        self.assertEqual(currents, {0: 1.0, 1: 1.0})
        self.assertIn("SPIKE-BE-PI-W-0202", {issue.code for issue in issues})

    def test_unreviewed_component_model_is_rejected(self):
        spec = AnalysisSpec(
            mode="ac",
            options={
                "loop_extractions": [{
                    "forward": {
                        "net": "VIN",
                        "start": {"position_mm": [0.0, 0.0]},
                        "end": {"position_mm": [10.0, 0.0]},
                    },
                    "return": {
                        "net": "GND",
                        "start": {"position_mm": [10.0, 1.0]},
                        "end": {"position_mm": [0.0, 1.0]},
                    },
                    "component_models": [{"id": "Q1", "linearized_resistance_ohm": 0.01}],
                }]
            },
        )

        results, issues, _ = extract_loop_parasitics(
            self.mesh,
            spec,
            FakeResistanceSolver(),
            np.asarray([[10e-9, 4e-9], [4e-9, 10e-9]]),
            np.zeros(2),
            [1e3],
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["component_models"], [])
        self.assertIn("SPIKE-BE-PI-E-0204", {issue.code for issue in issues})

    def test_invalid_reviewed_component_values_reject_loop(self):
        for value in (-0.1, float("nan"), float("inf"), True):
            with self.subTest(resistance_ohm=value):
                spec = AnalysisSpec(
                    mode="ac",
                    options={"loop_extractions": [{
                        "forward": {
                            "net": "VIN", "start": {"position_mm": [0.0, 0.0]},
                            "end": {"position_mm": [10.0, 0.0]},
                        },
                        "return": {
                            "net": "GND", "start": {"position_mm": [10.0, 1.0]},
                            "end": {"position_mm": [0.0, 1.0]},
                        },
                        "component_models": [{"id": "Rbad", "reviewed": True, "resistance_ohm": value}],
                    }]},
                )
                results, issues, _ = extract_loop_parasitics(
                    self.mesh, spec, FakeResistanceSolver(),
                    np.asarray([[10e-9, 4e-9], [4e-9, 10e-9]]), np.zeros(2), [1e3],
                )
                self.assertEqual(results, [])
                self.assertIn("SPIKE-BE-PI-E-0201", {issue.code for issue in issues})
                self.assertIn("finite and non-negative", issues[0].message)

    def test_capacitance_is_not_reused_for_a_different_return_net(self):
        spec = AnalysisSpec(
            mode="ac",
            return_path={"mode": "explicit", "net": "CHASSIS"},
            options={
                "loop_extractions": [{
                    "id": "vin-loop",
                    "forward": {
                        "net": "VIN",
                        "start": {"position_mm": [0.0, 0.0]},
                        "end": {"position_mm": [10.0, 0.0]},
                    },
                    "return": {
                        "net": "GND",
                        "start": {"position_mm": [10.0, 1.0]},
                        "end": {"position_mm": [0.0, 1.0]},
                    },
                }]
            },
        )

        results, issues, _ = extract_loop_parasitics(
            self.mesh,
            spec,
            FakeResistanceSolver(),
            np.asarray([[10e-9, 4e-9], [4e-9, 10e-9]]),
            np.asarray([20e-12, 0.0]),
            [1e3],
        )

        self.assertIsNone(results[0]["estimated_net_capacitance_f"])
        self.assertEqual(results[0]["capacitance_model_status"], "unsupported")
        self.assertIn("SPIKE-BE-PI-W-0203", {issue.code for issue in issues})


if __name__ == "__main__":
    unittest.main()
