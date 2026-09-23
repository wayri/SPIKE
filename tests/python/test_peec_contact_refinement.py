# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Production-builder finite-contact h-refinement and budget oracles."""

import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.peec_conforming_mesh import build_conforming_mesh
from python.spike_core.peec_conforming_dc import assemble_conforming_dc, solve_conforming_dc

try:
    import shapely  # noqa: F401
except ImportError:
    shapely = None


def _sheet(h, max_cells=20000):
    design = DesignIR(layers=[{"name": "F.Cu"}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        zones=[{"id": "sheet", "net_name": "N", "layer": "F.Cu",
                "points": [[0, 0], [2, 0], [2, 1], [0, 1]]}],
        pads=[{"id": "source", "at": [.25, .5], "size": [.5, .5],
               "shape": "rect", "layer": "F.Cu", "net_name": "N"},
              {"id": "load", "at": [1.75, .5], "size": [.5, .5],
               "shape": "rect", "layer": "F.Cu", "net_name": "N"}])
    spec = AnalysisSpec(mode="dc", net_names=["N"], mesh={
        "target_size_mm": h, "zone_cell_mm": h,
        "max_conforming_cells": max_cells, "max_conductors": 10000,
        "conforming_boundary_depth": 5,
    })
    return build_conforming_mesh(design, spec)


@unittest.skipUnless(shapely is not None, "optional Shapely geometry backend required")
class FiniteContactRefinementTests(unittest.TestCase):
    def test_fixed_footprint_subdivides_and_rt0_weights_remain_normalized(self):
        counts = []
        for h in (.125, .0625):
            with self.subTest(h=h):
                mesh = _sheet(h)
                self.assertFalse(mesh.truncated, [issue.message for issue in mesh.issues])
                contacts = mesh.branch_admission["conforming_partition"]["terminal_contacts"]
                self.assertEqual({item["source_id"] for item in contacts}, {"source", "load"})
                for contact in contacts:
                    self.assertAlmostEqual(contact["area_mm2"], .125**2, places=12)
                    cells = [cell for cell in mesh.cells
                             if cell["control_node"] == contact["node"]]
                    counts.append(len(cells))
                    self.assertAlmostEqual(sum(
                        (cell["vertices_mm"][2][0]-cell["vertices_mm"][0][0])
                        *(cell["vertices_mm"][2][1]-cell["vertices_mm"][0][1])
                        for cell in cells), .125**2, places=12)
                    for cell in cells:
                        width = cell["vertices_mm"][2][0]-cell["vertices_mm"][0][0]
                        height = cell["vertices_mm"][2][1]-cell["vertices_mm"][0][1]
                        self.assertLessEqual(max(width, height), h+1e-12)
                system = assemble_conforming_dc(mesh)
                for contact in contacts:
                    _, weights = system.contacts[contact["node"]]
                    self.assertAlmostEqual(float(weights.sum()), 1.0, places=12)
        self.assertEqual(counts, [1, 1, 4, 4])

    def test_contact_subdivision_respects_total_cell_budget(self):
        mesh = _sheet(.0625, max_cells=10)
        self.assertTrue(mesh.truncated)
        self.assertLessEqual(len(mesh.cells), 10)
        self.assertTrue(any(issue.code == "PEEC_CONFORMING_PARTITION_UNQUALIFIED"
                            for issue in mesh.issues))

    def test_unattainable_refinement_is_rejected_instead_of_clamped(self):
        mesh = _sheet(.03125)
        self.assertTrue(mesh.truncated)
        self.assertEqual(len(mesh.cells), 0)
        self.assertTrue(any("silently clamp" in issue.message for issue in mesh.issues))

    def test_fixed_contact_port_loss_is_refinement_sensitive(self):
        values = []
        for h in (.25, .125, .0625, .05):
            with self.subTest(h=h):
                mesh = _sheet(h)
                self.assertFalse(mesh.truncated)
                contacts = mesh.branch_admission["conforming_partition"]["terminal_contacts"]
                source = next(item["node"] for item in contacts if item["source_id"] == "source")
                load = next(item["node"] for item in contacts if item["source_id"] == "load")
                result = solve_conforming_dc(mesh, source, load)
                self.assertLess(result["relative_energy_error"], 1e-9)
                self.assertLess(result["maximum_cell_kcl_error_a"], 1e-9)
                values.append(result["resistance_ohm"])
        # A same-method refinement check, not an independent physical oracle.
        self.assertLess(abs(values[2]-values[3]), abs(values[0]-values[1]))


if __name__ == "__main__":
    unittest.main()
