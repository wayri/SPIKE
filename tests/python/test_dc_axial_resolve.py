# SPDX-License-Identifier: Apache-2.0
"""Fresh RT0 solves use face-to-face gap R; old currents are not relabelled."""
from copy import deepcopy
import math
import unittest

from shapely.geometry import Point

from python.spike_core.dc_axial_ownership import compile_axial_ownership, make_gap_branches
from python.spike_core.dc_triangle_partition import partition_polygon_groups
from python.spike_core.hybrid_mesh import HybridMesh, MeshNode
from python.spike_core.peec_conforming_dc import solve_hybridized_conforming_dc
from tests.python.test_dc_axial_ownership import explicit_stack


def solve_stack(use_center_spans=False):
    request = explicit_stack()
    # Deliberately restricted integration fixture: all face contacts and lands
    # share one annular footprint per layer. General spreading is not inferred.
    for node, land in enumerate(request["lands"]):
        old = land["node"]
        land["node"] = node
        land["outer_radius_mm"] = .175
        for segment in request["segments"]:
            for end in ("source_contact", "target_contact"):
                if segment[end]["node"] == old:
                    segment[end]["node"] = node
    ownership = compile_axial_ownership(request)
    branches = make_gap_branches(request)
    if use_center_spans:
        for branch, segment in zip(branches, request["segments"]):
            branch.start_mm = (*request["center_xy_mm"], segment["start_z_mm"])
            branch.end_mm = (*request["center_xy_mm"], segment["end_z_mm"])
    mesh = HybridMesh(branches=branches)
    groups, contacts = {}, []
    center = Point(*request["center_xy_mm"])
    # Polygon approximation is explicitly recorded against exact annular area;
    # it is not substituted into the axial resistance supplied to the solve.
    footprint = center.buffer(.175, quad_segs=32).difference(center.buffer(.15, quad_segs=32))
    for land in request["lands"]:
        z = (land["z_min_mm"]+land["z_max_mm"])/2
        mesh.nodes.append(MeshNode(land["node"], *request["center_xy_mm"], z, land["layer"], request["net"]))
        groups[(land["layer"], request["net"])] = {"geometry": footprint,
            "thickness_mm": land["z_max_mm"]-land["z_min_mm"],
            "conductivity_s_m": land["conductivity_s_m"], "z_mm": z}
        contacts.append({"id": land["id"], "node": land["node"], "layer": land["layer"],
                         "net": request["net"], "geometry": footprint})
    mesh = partition_polygon_groups(groups, contacts, target_mm=.05, mesh=mesh)
    result = solve_hybridized_conforming_dc(mesh, 0, 2, include_density=True)
    exact_area = math.pi*(.175**2-.15**2)
    return ownership, result, {"contact_polygon_area_mm2": footprint.area,
                               "exact_annular_face_area_mm2": exact_area,
                               "relative_contact_area_discrepancy": abs(footprint.area/exact_area-1)}


class AxialResolveTests(unittest.TestCase):
    def test_gap_resistance_requires_actual_new_solve(self):
        ownership, actual, approximation = solve_stack()
        _, previous, _ = solve_stack(use_center_spans=True)
        exact_r = 1000*1.8/(5.8e7*math.pi*(.175**2-.15**2))
        self.assertLess(abs(actual["resistance_ohm"]/exact_r-1), 1e-9)
        self.assertLess(abs(actual["resistance_ohm"]/previous["resistance_ohm"]-.9), 1e-9)
        self.assertLess(abs(actual["dissipation_w_at_one_ampere"]/exact_r-1), 1e-9)
        self.assertLess(actual["maximum_cell_kcl_error_a"], 1e-8)
        self.assertLess(actual["maximum_face_kcl_error_a"], 1e-8)
        self.assertGreater(approximation["relative_contact_area_discrepancy"], 0)
        self.assertLess(approximation["relative_contact_area_discrepancy"], .0005)
        self.assertTrue(ownership["requires_resolve"])
        self.assertFalse(actual["current_density_observable"]["complete_physical_volume"])
        self.assertFalse(actual["production_qualified"])
        # Inputs contain imposed 2/3 A currents; actual solve is at 1 A. Their
        # precomputed heat is intentionally not substituted into this ledger.
        self.assertNotAlmostEqual(actual["dissipation_w_at_one_ampere"], ownership["axial_imposed_current_heat_w"])


if __name__ == "__main__":
    unittest.main()
