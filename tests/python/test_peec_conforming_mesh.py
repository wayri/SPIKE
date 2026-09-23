# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Manufactured copper-support, face-current and fixed-contact oracles."""

import unittest

import numpy as np

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import TOPOLOGY_ONLY_BRANCH_KINDS
from python.spike_core.peec_conforming_mesh import build_conforming_mesh, _coalesce_rectangles
from python.spike_core.peec_volume_resistance import _basis, assemble_overlap_resistance

try:
    from shapely.geometry import Polygon
except ImportError:
    Polygon = None


def _design(points):
    return DesignIR(layers=[{"name": "F.Cu"}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        zones=[{"id": "sheet", "net_name": "N", "layer": "F.Cu", "points": points}])


def _mesh(design, target, **settings):
    return build_conforming_mesh(design, AnalysisSpec(mode="ac", net_names=["N"],
        mesh={"target_size_mm": target, "zone_cell_mm": target,
              "max_conductors": 10000, "conforming_boundary_depth": 5, **settings}))


@unittest.skipUnless(Polygon is not None, "optional Shapely geometry backend required")
class ConformingCopperTests(unittest.TestCase):
    def test_explicit_interior_edge_refinement_preserves_union_contacts_and_components(self):
        from shapely.ops import unary_union
        design = _design([[0,0],[2,0],[2,1],[0,1]])
        design.zones.append({"id":"island", "net_name":"N", "layer":"F.Cu",
            "points":[[2.1,0],[3.1,0],[3.1,1],[2.1,1]]})
        design.pads = [{"id":"P1", "at":[.5,.5], "size":[1,1],
            "shape":"rect", "layer":"F.Cu", "net_name":"N"}]
        original = _mesh(design,.5)
        refined = _mesh(design,.5,conforming_interior_max_edge_mm=.125)
        repeated = _mesh(design,.5,conforming_interior_max_edge_mm=.125)
        self.assertEqual(refined.cells,repeated.cells)
        for mesh in (original,refined):
            self.assertFalse(mesh.truncated,[issue.message for issue in mesh.issues])
        def region(mesh):
            return unary_union([Polygon([vertex[:2] for vertex in cell["vertices_mm"]])
                for cell in mesh.cells])
        self.assertLess(region(original).symmetric_difference(region(refined)).area,1e-12)
        original_report = original.branch_admission["conforming_partition"]
        report = refined.branch_admission["conforming_partition"]
        self.assertEqual(original_report["terminal_contacts"],report["terminal_contacts"])
        self.assertGreater(report["interior_subdivision_added_cells"],0)
        self.assertEqual(report["interior_max_edge_mm"],.125)
        contact_nodes = {contact["node"] for contact in report["terminal_contacts"]}
        contact_cells = [cell for cell in refined.cells if cell["control_node"] in contact_nodes]
        self.assertEqual(len(contact_cells),1)
        self.assertAlmostEqual(contact_cells[0]["vertices_mm"][2][0]-contact_cells[0]["vertices_mm"][0][0],.25)
        for cell in refined.cells:
            if cell["control_node"] in contact_nodes:
                continue
            a,b = cell["vertices_mm"][0],cell["vertices_mm"][2]
            self.assertLessEqual(max(b[0]-a[0],b[1]-a[1]),.125+1e-12)
        def components(mesh):
            parent = list(range(len(mesh.nodes)))
            def root(i):
                while parent[i] != i:
                    parent[i] = parent[parent[i]]
                    i = parent[i]
                return i
            for branch in mesh.branches:
                parent[root(branch.node_p)] = root(branch.node_n)
            return len({root(node.id) for node in mesh.nodes})
        self.assertEqual(components(original),2)
        self.assertEqual(components(refined),2)

    def test_interior_refinement_default_is_disabled_and_invalid_or_over_budget_fails(self):
        design = _design([[0,0],[2,0],[2,1],[0,1]])
        original = _mesh(design,.5)
        disabled = _mesh(design,.5,conforming_interior_max_edge_mm=None)
        self.assertEqual(original.cells,disabled.cells)
        self.assertEqual(original.branches,disabled.branches)
        for value in (0,-1,float("nan"),float("inf"),True,"invalid"):
            with self.subTest(value=value):
                mesh = _mesh(design,.5,conforming_interior_max_edge_mm=value)
                self.assertTrue(mesh.truncated)
                self.assertTrue(any("finite and positive" in issue.message for issue in mesh.issues))
        for value in (.01,1e-320):
            with self.subTest(value=value):
                mesh = _mesh(design,.5,conforming_interior_max_edge_mm=value,max_conforming_cells=100)
                self.assertTrue(mesh.truncated)
                self.assertTrue(any("subdivision exceeds" in issue.message for issue in mesh.issues))
                self.assertLessEqual(len(mesh.cells),100)

    def test_coalescing_removes_only_redundant_faces_without_filling_voids(self):
        from shapely.geometry import box
        from shapely.ops import unary_union
        # An excluded center is a fixed contact/void; a 1e-9 mm gap between the
        # two distant cells must survive independently of geometry tolerance.
        rectangles = [(x/4,y/4,(x+1)/4,(y+1)/4)
            for x in range(12) for y in range(12)
            if not (4 <= x < 8 and 4 <= y < 8)]
        rectangles += [(4,0,4.5,0.5), (4.500000001,0,5,0.5)]
        coalesced = _coalesce_rectangles(rectangles, 1.0)
        before = unary_union([box(*bounds) for bounds in rectangles])
        after = unary_union([box(*bounds) for bounds in coalesced])
        self.assertEqual(before.symmetric_difference(after).area, 0.0)
        self.assertEqual(after.intersection(box(1,1,2,2)).area, 0.0)
        self.assertLess(len(coalesced), len(rectangles)/4)
        self.assertTrue(all(x1-x0 <= 1 and y1-y0 <= 1 for x0,y0,x1,y1 in coalesced))
        self.assertEqual(len(list(after.geoms)), 3)

    def test_uniform_sheet_full_face_resistance_matches_rho_length_over_area(self):
        design = _design([[0, 0], [2, 0], [2, 1], [0, 1]])
        for h in (0.5, 0.25, 0.125):
            with self.subTest(h=h):
                mesh = _mesh(design, h)
                self.assertFalse(mesh.truncated, [issue.message for issue in mesh.issues])
                # Exact solution for equipotential end control planes is
                # V=x/(2-h). Use J=1/(thickness*width) and check every branch
                # constitutive equation and every interior KCL row directly.
                resistance, _ = assemble_overlap_resistance(design, mesh.branches)
                currents = np.array([h if abs(b.end_mm[0]-b.start_mm[0]) > 1e-12 else 0.0 for b in mesh.branches])
                expected_r = (2-h)*1e-3/(5.8e7*1*0.035*1e-6)
                potentials = np.array([(node.x_mm-h/2)/(2-h)*expected_r for node in mesh.nodes])
                drops = np.array([potentials[b.node_n]-potentials[b.node_p] for b in mesh.branches])
                np.testing.assert_allclose(resistance @ currents, drops, rtol=1e-11, atol=1e-16)
                balance = np.zeros(len(mesh.nodes))
                for branch, current in zip(mesh.branches, currents):
                    balance[branch.node_p] -= current
                    balance[branch.node_n] += current
                middle = [node.id for node in mesh.nodes if h/2+1e-10 < node.x_mm < 2-h/2-1e-10]
                np.testing.assert_allclose(balance[middle], 0, atol=1e-14)
                self.assertAlmostEqual(float(currents @ resistance @ currents), expected_r, places=14)

    def test_clipped_boundary_support_stays_inside_and_omission_is_bounded(self):
        points = [[0,0], [2,0], [2,0.4], [0.8,1], [0,1]]
        design = _design(points)
        mesh = _mesh(design, 0.5)
        self.assertFalse(mesh.truncated, [issue.message for issue in mesh.issues])
        polygon = Polygon(points)
        for branch in mesh.branches:
            support = Polygon(_basis(design, branch).polygon)
            self.assertLessEqual(support.difference(polygon).area, 1e-8)
        report = mesh.branch_admission["conforming_partition"]
        self.assertLessEqual(report["groups"][0]["omitted_area_fraction"], 0.01)
        self.assertEqual(report["support_outside_area_max_mm2"], 0.0)
        self.assertTrue(report["area_bound_is_not_port_error_bound"])

    def test_pad_terminal_support_is_fixed_and_face_loss_is_finite(self):
        design = _design([[0,0], [2,0], [2,1], [0,1]])
        design.pads = [{"id":"P1", "at":[0.5,0.5], "size":[0.5,0.5],
                       "shape":"rect", "layer":"F.Cu", "net_name":"N"}]
        supports = []
        for h in (0.5, 0.25, 0.125):
            mesh = _mesh(design, h)
            self.assertFalse(mesh.truncated, [issue.message for issue in mesh.issues])
            contact = mesh.branch_admission["conforming_partition"]["terminal_contacts"][0]
            supports.append((contact["area_mm2"], contact["bounds_mm"]))
            touching = [branch for branch in mesh.branches if contact["node"] in (branch.node_p, branch.node_n)]
            self.assertGreaterEqual(len(touching), 4)
            self.assertAlmostEqual(sum(branch.width_mm for branch in touching), 0.5)
            self.assertTrue(all(branch.length_mm > 0 and branch.resistance_ohm > 0 for branch in touching))
            self.assertFalse(any(branch.kind in TOPOLOGY_ONLY_BRANCH_KINDS for branch in mesh.branches))
        self.assertEqual(supports[0], supports[1])
        self.assertEqual(supports[1], supports[2])

    def test_disjoint_copper_islands_do_not_gain_face_connection(self):
        design = _design([[0,0],[1,0],[1,1],[0,1]])
        design.zones.append({"id":"other", "net_name":"N", "layer":"F.Cu",
            "points":[[1.001,0],[2,0],[2,1],[1.001,1]]})
        mesh = _mesh(design, 0.5)
        self.assertFalse(mesh.truncated, [issue.message for issue in mesh.issues])
        for branch in mesh.branches:
            self.assertFalse(branch.start_mm[0] <= 1 and branch.end_mm[0] >= 1.001)

    def test_via_has_distributed_fixed_contacts_with_finite_planar_faces(self):
        from shapely.geometry import Point, box
        design = DesignIR(layers=[{"name":"F.Cu"}, {"name":"B.Cu"}],
            vias=[{"id":"v", "at":[0,0], "size":0.6, "drill":0.3,
                   "layers":["F.Cu","B.Cu"], "net_name":"N"}])
        # This is a mesh/contact test, not a dense magnetic solve. Use the
        # sparse-DC resource policy for its several thousand boundary faces.
        mesh = build_conforming_mesh(design, AnalysisSpec(mode="dc", net_names=["N"],
            mesh={"target_size_mm":0.25, "conforming_boundary_depth":6,
                  "conforming_max_omitted_area_fraction":0.02, "max_conductors":20000}))
        self.assertFalse(mesh.truncated, [issue.message for issue in mesh.issues])
        report = mesh.branch_admission["conforming_partition"]
        self.assertEqual(len(report["terminal_contacts"]), 8)
        annulus = Point(0,0).buffer(0.175, quad_segs=128).difference(Point(0,0).buffer(0.15, quad_segs=128))
        for contact in report["terminal_contacts"]:
            self.assertLessEqual(box(*contact["bounds_mm"]).difference(annulus).area, 1e-8)
            touching = [branch for branch in mesh.branches
                if branch.kind != "via" and contact["node"] in (branch.node_p, branch.node_n)]
            self.assertGreaterEqual(len(touching), 16)
            self.assertTrue(all(branch.resistance_ohm > 0 for branch in touching))
        self.assertEqual(sum(branch.kind == "via" for branch in mesh.branches), 1)
        self.assertTrue(any(branch.kind == "via_landing" for branch in mesh.branches))
        self.assertFalse(any(branch.kind == "zone" and branch.source_id == "v"
                             for branch in mesh.branches))
        self.assertFalse(any(branch.kind in TOPOLOGY_ONLY_BRANCH_KINDS for branch in mesh.branches))

    def test_area_or_resource_failure_does_not_admit_legacy_bases(self):
        design = _design([[0,0],[2,0],[0,1]])
        mesh = _mesh(design, 0.5, conforming_boundary_depth=1)
        self.assertTrue(mesh.truncated)
        self.assertTrue(any(issue.code == "PEEC_CONFORMING_PARTITION_UNQUALIFIED" for issue in mesh.issues))
        bounded = _mesh(_design([[0,0],[2,0],[2,1],[0,1]]), 0.125, max_conductors=5)
        self.assertTrue(bounded.truncated)
        self.assertLessEqual(len(bounded.branches), bounded.branch_admission["effective_branch_limit"])

    def test_unselected_unsupported_geometry_does_not_block_selected_copper(self):
        design = _design([[0,0],[2,0],[2,1],[0,1]])
        design.pads = [{"id":"unrelated", "net_name":"OTHER", "shape":"custom",
                       "at":[10,10], "size":[1,1], "drill":0.5, "layer":"F.Cu"}]
        design.tracks = [{"id":"unrelated-arc", "net_name":"OTHER", "layer":"F.Cu",
                          "start":[0,0], "end":[1,1], "mid":[1,0], "width":0.1}]
        mesh = _mesh(design, 0.5)
        self.assertFalse(mesh.truncated, [issue.message for issue in mesh.issues])
        self.assertTrue(all(branch.net == "N" for branch in mesh.branches))


if __name__ == "__main__":
    unittest.main()
