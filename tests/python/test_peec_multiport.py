import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import HybridMesh, MeshBranch, MeshNode
from python.spike_core.peec_plugin import (
    _solve_shared_reference_port_matrix,
    native_available,
    solve_peec_2_5d,
)
from python.spike_core.peec_network import extract_pdn_multiport


class SharedReferenceMatrixTests(unittest.TestCase):
    def test_two_resistor_chain_matches_closed_form_z_matrix(self):
        mesh = HybridMesh(
            nodes=[
                MeshNode(10, 0.0, 0.0, 0.0, "F.Cu", "VCC"),
                MeshNode(20, 1.0, 0.0, 0.0, "F.Cu", "VCC"),
                MeshNode(30, 2.0, 0.0, 0.0, "F.Cu", "VCC"),
            ],
            branches=[
                MeshBranch(
                    "r1", "track", 10, 20,
                    (0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                    1.0, 0.035, 5.8e7, "F.Cu", "VCC", "r1",
                ),
                MeshBranch(
                    "r2", "track", 20, 30,
                    (1.0, 0.0, 0.0), (2.0, 0.0, 0.0),
                    1.0, 0.035, 5.8e7, "F.Cu", "VCC", "r2",
                ),
            ],
        )
        matrix, quality = _solve_shared_reference_port_matrix(
            mesh,
            node_ids=[10, 20, 30],
            branch_indices=[0, 1],
            port_nodes=[20, 30],
            reference_node=10,
            branch_impedance=np.diag([2.0, 3.0]).astype(complex),
            diagnostics=True,
        )

        np.testing.assert_allclose(
            matrix,
            np.asarray([[2.0, 2.0], [2.0, 5.0]], dtype=complex),
            rtol=1e-12,
            atol=1e-12,
        )
        self.assertEqual(quality["method"], "dense_direct")
        self.assertLess(quality["relative_residual"], 1e-12)

    def test_nonpassive_pdn_matrix_is_rejected_without_projection(self):
        mesh = HybridMesh(
            nodes=[
                MeshNode(0, 0.0, 0.0, 0.0, "F.Cu", "VCC"),
                MeshNode(1, 1.0, 0.0, 0.0, "F.Cu", "VCC"),
                MeshNode(2, 2.0, 0.0, 0.0, "F.Cu", "VCC"),
            ],
            branches=[
                MeshBranch("rail", "track", 0, 1, (0., 0., 0.), (1., 0., 0.),
                           1., .035, 5.8e7, "F.Cu", "VCC", "rail"),
                MeshBranch("rail2", "track", 1, 2, (1., 0., 0.), (2., 0., 0.),
                           1., .035, 5.8e7, "F.Cu", "VCC", "rail2"),
            ],
        )
        spec = AnalysisSpec(mode="ac", net_names=["VCC"], options={
            "pdn_candidate_ports": [{"id": "candidate", "net": "VCC",
                                     "position_mm": [2., 0.], "layer": "F.Cu"}],
        })
        class Solver:
            def compute_resistance(self, frequency):
                return np.eye(2)

        matrices = [np.array([[2., 0.], [0., 1.]], dtype=complex),
                    np.array([[2., 0.], [0., -0.01]], dtype=complex)]
        with patch("python.spike_core.peec_network.solve_shared_reference_port_matrix",
                   side_effect=[(matrix, {"relative_residual": 0., "condition_number": None})
                                for matrix in matrices]):
            result, issues = extract_pdn_multiport(
                mesh, spec, Solver(), "VCC", 0, ("observation", 1), False,
                [0, 1, 2], [0, 1], np.zeros((2, 2)), np.zeros((3, 3)),
                np.zeros((3, 3)), [1e3, 1e6],
            )
        self.assertIsNone(result)
        self.assertIn("PEEC_PDN_NONPASSIVE", {issue.code for issue in issues})


@unittest.skipUnless(native_available(), "Native PEEC extension is not built")
class NativePdnMultiportTests(unittest.TestCase):
    def test_candidate_ports_emit_bounded_multiport_contract(self):
        design = DesignIR(
            name="PDN multiport rail",
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{
                "id": "rail",
                "start": [0.0, 0.0],
                "end": [10.0, 0.0],
                "width": 1.0,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        spec = AnalysisSpec(
            analysis_id="pdn-native-test",
            mode="ac",
            solver_id="spike.peec_2_5d",
            formulation="peec_2_5d",
            net_names=["VCC"],
            sources=[{
                "id": "source",
                "position_mm": [0.0, 0.0],
                "layer": "F.Cu",
                "net": "VCC",
            }],
            loads=[{
                "id": "observation",
                "position_mm": [10.0, 0.0],
                "layer": "F.Cu",
                "net": "VCC",
            }],
            frequency_start_hz=1e3,
            frequency_stop_hz=1e6,
            frequency_points=3,
            mesh={"target_size_mm": 2.0, "max_preview_cells": 1000},
            options={
                "pdn_candidate_ports": [{
                    "id": "candidate-midrail",
                    "position_mm": [5.0, 0.0],
                    "layer": "F.Cu",
                    "net": "VCC",
                    "endpoint_reviewed": True,
                }],
            },
        )

        result = solve_peec_2_5d(design, spec)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.model_status, "approximate")
        self.assertEqual(result.summary["pdn_multiport_count"], 1)
        multiport = result.networks["pdn_multiports"][0]
        self.assertEqual(multiport["contract"], "spike/pdn-multiport/v1")
        self.assertEqual(multiport["model_status"], "approximate")
        self.assertEqual(len(multiport["z_parameters"]), 3)
        self.assertEqual(len(multiport["ports"]), 2)
        self.assertEqual(multiport["candidates"][0]["id"], "candidate-midrail")
        self.assertTrue(multiport["candidates"][0]["endpoint_reviewed"])
        self.assertIn(
            "SPIKE-BE-PI-W-0101",
            {issue.code for issue in result.issues},
        )

    def test_candidate_for_another_net_does_not_create_false_error(self):
        design = DesignIR(
            name="Single VCC rail",
            layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{
                "id": "rail",
                "start": [0.0, 0.0],
                "end": [4.0, 0.0],
                "width": 1.0,
                "layer": "F.Cu",
                "net_name": "VCC",
            }],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        spec = AnalysisSpec(
            mode="ac",
            net_names=["VCC"],
            sources=[{"position_mm": [0.0, 0.0], "layer": "F.Cu", "net": "VCC"}],
            loads=[{"position_mm": [4.0, 0.0], "layer": "F.Cu", "net": "VCC"}],
            frequency_start_hz=1e3,
            frequency_stop_hz=1e4,
            frequency_points=2,
            mesh={"target_size_mm": 1.0},
            options={
                "pdn_candidate_ports": [{
                    "id": "other-net-candidate",
                    "net": "OTHER",
                    "position_mm": [2.0, 0.0],
                    "layer": "F.Cu",
                }],
            },
        )

        result = solve_peec_2_5d(design, spec)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.networks["pdn_multiports"], [])
        self.assertNotIn(
            "SPIKE-BE-PI-E-0102",
            {issue.code for issue in result.issues},
        )


if __name__ == "__main__":
    unittest.main()
