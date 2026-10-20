# SPDX-License-Identifier: Apache-2.0
"""Explicit geometry uncertainty, conforming flux and no feature deletion."""
from copy import deepcopy
import math
import unittest

import numpy as np
from shapely.affinity import rotate
from shapely.geometry import Polygon, box

from python.spike_core.dc_triangle_partition import partition_polygon_groups
from python.spike_core.peec_conforming_dc import (
    assemble_conforming_dc, solve_conforming_dc, solve_hybridized_conforming_dc,
)


def fixture(angle=.61):
    transform = lambda shape: rotate(shape, angle, origin=(0, 0), use_radians=True)
    groups = {("F.Cu", "N"): {"geometry": transform(box(0, 0, 2, 1)),
              "thickness_mm": .035, "conductivity_s_m": 5.8e7, "z_mm": 0.}}
    contacts = [{"id": name, "layer": "F.Cu", "net": "N", "geometry": transform(shape)}
                for name, shape in zip(("source", "load"), (box(0, 0, .5, 1), box(1.5, 0, 2, 1)))]
    return groups, contacts


class PrecisionPartitionTests(unittest.TestCase):
    def test_original_failure_fixed_with_explicit_measured_geometry(self):
        groups, contacts = fixture()
        source_wkb = [groups[("F.Cu", "N")]["geometry"].wkb, *[c["geometry"].wkb for c in contacts]]
        mesh = partition_polygon_groups(groups, contacts, target_mm=.25, geometry_grid_mm=1e-12)
        result = solve_hybridized_conforming_dc(mesh, 0, 1, include_density=True)
        mixed = solve_conforming_dc(mesh, 0, 1)
        self.assertLess(abs(result["resistance_ohm"]/mixed["resistance_ohm"]-1), 1e-9)
        exact = (2-4*.5/3)/(5.8e7*.035e-3)
        self.assertLess(abs(result["resistance_ohm"]/exact-1), .004)
        self.assertLess(result["maximum_face_kcl_error_a"], 1e-8)
        audit = mesh.branch_admission["conforming_partition"]["groups"][0]["precision_geometry"]
        self.assertFalse(audit["formal_roundoff_certificate"])
        for shape in [audit["copper"], *audit["contacts"]]:
            self.assertLessEqual(shape["boundary_displacement_mm"], 4e-12)
            self.assertLessEqual(shape["symmetric_difference_mm2"], shape["area_budget_mm2"])
        self.assertEqual(source_wkb, [groups[("F.Cu", "N")]["geometry"].wkb, *[c["geometry"].wkb for c in contacts]])
        self.assertTrue(all("node" not in c for c in contacts))

    def test_no_triangle_guard_relaxation_or_legacy_silent_snap(self):
        groups, contacts = fixture()
        mesh = partition_polygon_groups(groups, contacts, target_mm=.5)
        with self.assertRaisesRegex(ValueError, "reversed, degenerate or ill-shaped"):
            assemble_conforming_dc(mesh)
        self.assertNotIn("precision_geometry", mesh.branch_admission["conforming_partition"]["groups"][0])

    def test_holes_and_inactive_components_preserved(self):
        shape = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)],
                        holes=[[(.8, .8), (.8, 1.2), (1.2, 1.2), (1.2, .8)]])
        shape = shape.union(box(3, 0, 4, 1))
        groups = {("F.Cu", "N"): {"geometry": rotate(shape, .61, origin=(0, 0), use_radians=True),
                  "thickness_mm": .035, "conductivity_s_m": 5.8e7, "z_mm": 0.}}
        mesh = partition_polygon_groups(groups, [], target_mm=.25, geometry_grid_mm=1e-12)
        system = assemble_conforming_dc(mesh)
        self.assertAlmostEqual(float(system.areas_mm2.sum()), 4.84, places=10)
        audit = mesh.branch_admission["conforming_partition"]["groups"][0]["precision_geometry"]["copper"]
        self.assertEqual(audit["components"], 2)
        self.assertEqual(audit["hole_counts"], [0, 1])

    def test_narrow_copper_and_holes_are_rejected_not_removed(self):
        groups, _ = fixture(0.)
        for shape in (box(0, 0, 1, 1e-11),
                      Polygon([(0, 0), (2, 0), (2, 2), (0, 2)],
                              holes=[[(1, 1), (1+1e-11, 1), (1+1e-11, 1.1), (1, 1.1)]])):
            groups[("F.Cu", "N")]["geometry"] = shape
            with self.assertRaisesRegex(ValueError, "cannot resolve"):
                partition_polygon_groups(groups, [], target_mm=.25, geometry_grid_mm=1e-12)

    def test_narrow_contact_separation_is_rejected(self):
        groups, contacts = fixture(0.)
        contacts[0]["geometry"] = box(0, 0, 1, 1)
        contacts[1]["geometry"] = box(1+1e-11, 0, 2, 1)
        with self.assertRaisesRegex(ValueError, "cannot resolve separation"):
            partition_polygon_groups(groups, contacts, target_mm=.25, geometry_grid_mm=1e-12)

    def test_grid_origin_and_resource_bounds(self):
        for grid in (-1., math.nan, math.inf, 1e-3, 1e-30, True, False):
            groups, contacts = fixture()
            with self.assertRaises(ValueError):
                partition_polygon_groups(groups, contacts, target_mm=.25, geometry_grid_mm=grid)
        groups, contacts = fixture()
        with self.assertRaisesRegex(ValueError, "budget"):
            partition_polygon_groups(groups, contacts, target_mm=.001, max_triangles=10, geometry_grid_mm=1e-12)

    def test_separate_copper_nets_cannot_be_snapped_into_contact(self):
        groups, _ = fixture(0.)
        material = groups[("F.Cu", "N")]
        groups = {("F.Cu", "A"): dict(material, geometry=box(0, 0, .5, 1)),
                  ("F.Cu", "B"): dict(material, geometry=box(.5+4e-13, 0, 1, 1))}
        with self.assertRaisesRegex(ValueError, "separation between copper groups"):
            partition_polygon_groups(groups, [], target_mm=.25, geometry_grid_mm=1e-12)

    def test_interior_contact_margin_cannot_be_snapped_to_exterior(self):
        groups, contacts = fixture(0.)
        contacts = [dict(contacts[0], geometry=box(4e-13, .2, .5, .8))]
        with self.assertRaisesRegex(ValueError, "contact-to-copper boundary clearance"):
            partition_polygon_groups(groups, contacts, target_mm=.25, geometry_grid_mm=1e-12)


if __name__ == "__main__":
    unittest.main()
