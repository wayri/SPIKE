"""Regression tests for graph-only links in native PEEC field assembly."""

from __future__ import annotations

import unittest

import numpy as np

from python.spike_core.hybrid_mesh import HybridMesh, MeshBranch, MeshNode
from python.spike_core.peec_network import solve_port
from python.spike_core.peec_matrices import TopologyResistanceSolver, embed_physical_inductance


def branch(identifier: str, kind: str, node_p: int, node_n: int) -> MeshBranch:
    return MeshBranch(
        id=identifier,
        kind=kind,
        node_p=node_p,
        node_n=node_n,
        start_mm=(float(node_p), 0.0, 0.0),
        end_mm=(float(node_n), 0.0, 0.0),
        width_mm=0.2,
        thickness_mm=0.035,
        conductivity_s_m=5.8e7,
        layer="F.Cu",
        net="VCC",
        source_id=identifier,
    )


class _ResistanceKernel:
    def __init__(self, resistance: float) -> None:
        self.resistance = resistance

    def compute_resistance(self, _frequency: float) -> np.ndarray:
        return np.asarray([[self.resistance]], dtype=float)


class PEECTopologyTests(unittest.TestCase):
    def test_attachment_retains_resistance_but_has_no_field_inductance(self):
        mesh = HybridMesh(
            nodes=[MeshNode(index, float(index), 0.0, 0.0, "F.Cu", "VCC") for index in range(3)],
            branches=[
                branch("pad-center", "pad_attachment", 0, 1),
                branch("trace", "track", 1, 2),
            ],
        )
        kernel = TopologyResistanceSolver(_ResistanceKernel(0.25), mesh, [1])

        resistance = kernel.compute_resistance(0.0)
        inductance = embed_physical_inductance(np.asarray([[4.0e-9]]), 2, [1])

        self.assertGreater(resistance[0, 0], 0.0)
        self.assertEqual(resistance[1, 1], 0.25)
        self.assertEqual(inductance[0, 0], 0.0)
        self.assertEqual(inductance[1, 1], 4.0e-9)
        self.assertEqual(inductance[0, 1], 0.0)

    def test_source_and_load_contact_links_keep_declared_mesh_resistance(self):
        mesh = HybridMesh(
            nodes=[MeshNode(index, float(index), 0.0, 0.0, "F.Cu", "VCC") for index in range(3)],
            branches=[
                branch("source", "source_contact", 0, 1),
                branch("load", "load_contact", 1, 2),
            ],
        )
        resistance = TopologyResistanceSolver(_ResistanceKernel(0.0), mesh, []).compute_resistance(0.0)

        self.assertGreater(resistance[0, 0], 0.0)
        self.assertGreater(resistance[1, 1], 0.0)
        self.assertTrue(np.allclose(embed_physical_inductance(np.empty((0, 0)), 2, []), 0.0))

    def test_zero_frequency_port_solution_keeps_attachment_dc_loss(self):
        mesh = HybridMesh(
            nodes=[MeshNode(index, float(index), 0.0, 0.0, "F.Cu", "VCC") for index in range(3)],
            branches=[
                branch("attachment", "pad_attachment", 0, 1),
                branch("trace", "track", 1, 2),
            ],
        )
        resistance = TopologyResistanceSolver(_ResistanceKernel(0.25), mesh, [1]).compute_resistance(0.0)
        impedance, _currents, quality = solve_port(
            mesh, [0, 1, 2], [0, 1], 0, 2, resistance,
        )

        self.assertAlmostEqual(impedance.real, mesh.branches[0].resistance_ohm + 0.25)
        self.assertAlmostEqual(impedance.imag, 0.0)
        self.assertLess(quality["relative_residual"], 1e-12)


if __name__ == "__main__":
    unittest.main()
