# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Polygon, box
from shapely.ops import unary_union

from python.spike_core.solvers.power_integrity.dc.dc_board_partition import partition_board_volumes


def volume(geometry, z0=0., z1=.1, net="N"):
    return {"geometry": geometry, "z0": z0, "z1": z1, "net": net}


class BoardPartitionTests(unittest.TestCase):
    def test_old_fixture_physical_coverage_equivalence(self):
        from tests.python.test_dc_board_volume import fixture
        groups, barrels, contacts = fixture()
        volumes, group_index = [], {}
        for key, row in groups.items():
            group_index[key] = len(volumes)
            volumes.append(volume(row["geometry"], row["z_mm"]-row["thickness_mm"]/2,
                                  row["z_mm"]+row["thickness_mm"]/2, key[1]))
        for row in barrels:
            volumes.append(volume(row["geometry"], row["z_min_mm"], row["z_max_mm"], row["net"]))
        contact_rows = [{"id": row["id"], "geometry": row["geometry"],
                         "group_index": group_index[row["layer"], row["net"]]} for row in contacts]
        result = partition_board_volumes(volumes, contact_rows, target_mm=.8, max_cells=5000)
        self.assertEqual(len(result["coverage_audits"]), len(volumes))
        self.assertTrue(all(row["accepted"] for row in result["coverage_audits"]))
        for owner, source in enumerate(volumes):
            represented = unary_union([Polygon(triangle) for triangle, signature in
                                       zip(result["triangles"], result["signatures"]) if owner in signature])
            self.assertEqual(source["geometry"].symmetric_difference(represented).area, 0.)
            prism_volume = sum(Polygon(result["triangles"][triangle]).area*(high-low)
                               for triangle, item, low, high in result["prism_rows"] if item == owner)
            self.assertAlmostEqual(prism_volume,
                source["geometry"].area*(source["z1"]-source["z0"]), delta=1e-12)
        self.assertEqual({row[1] for row in result["prism_rows"]}, set(range(len(volumes))))

    def test_rotated_holes_and_contacts_are_retained(self):
        outer = affinity.rotate(box(0, 0, 4, 3), 17, origin=(2, 1.5))
        hole = affinity.rotate(box(1, 1, 2, 2), 17, origin=(2, 1.5))
        copper = outer.difference(hole)
        contact = affinity.rotate(box(2.5, .2, 3.5, .8), 17, origin=(2, 1.5))
        result = partition_board_volumes([volume(copper)],
            [{"id": "drive", "geometry": contact, "group_index": 0}], target_mm=1., max_cells=5000)
        self.assertTrue(result["coverage_audits"][0]["accepted"])
        self.assertEqual(len(copper.interiors), 1)
        represented = unary_union([Polygon(triangle) for triangle in result["triangles"]])
        self.assertEqual(copper.symmetric_difference(represented).area, 0.)
        represented_contact = unary_union([
            Polygon(triangle) for triangle, identities in
            zip(result["triangles"], result["contact_signatures"]) if "drive" in identities])
        self.assertEqual(contact.symmetric_difference(represented_contact).area, 0.)

    def test_scalable_profile_is_explicit_and_does_not_change_default_cap(self):
        geometry = box(0, 0, 1, 1)
        with self.assertRaisesRegex(ValueError, "tetrahedron budget"):
            partition_board_volumes([volume(geometry)], [], target_mm=2., max_cells=5001)
        result = partition_board_volumes([volume(geometry)], [], target_mm=2.,
                                         max_cells=5001, scalable=True)
        self.assertEqual(len(result["prism_rows"])*3, 6)
        with self.assertRaisesRegex(ValueError, "profile flag"):
            partition_board_volumes([volume(geometry)], [], target_mm=2.,
                                    max_cells=5001, scalable=1)

    def test_curved_contact_split_by_interface_retains_complete_area_atoms(self):
        contact = LineString([(0, .5), (0, 1.5)]).buffer(.35, quad_segs=32)
        volumes = [volume(box(-1, 0, 1, 2), 0., .1),
                   volume(box(-.8, .75, .8, 1.25), .1, .2)]
        result = partition_board_volumes(volumes,
            [{"id": "rounded", "geometry": contact, "group_index": 0}],
            target_mm=1., max_cells=5000)
        represented = unary_union([
            Polygon(triangle) for triangle, identities in
            zip(result["triangles"], result["contact_signatures"])
            if "rounded" in identities])
        self.assertLessEqual(contact.symmetric_difference(represented).area,
                             128*2.220446049250313e-16*max(contact.area, 2.0**2))

    def test_horizontal_and_lateral_interfaces_have_no_hanging_partition(self):
        lower = volume(box(0, 0, 2, 1), 0., .1)
        upper = volume(box(.5, 0, 1.5, 1), .1, .2)
        side = volume(box(2, 0, 3, 1), 0., .1)
        result = partition_board_volumes([lower, upper, side], [], target_mm=.6, max_cells=5000)
        self.assertEqual(result["stats"]["conforming_cluster_count"], 1)
        projected = [(tuple(map(tuple, triangle)), signature)
                     for triangle, signature in zip(result["triangles"], result["signatures"])]
        self.assertTrue(any(set(signature) == {0, 1} for _, signature in projected))
        planes = {(low, high) for _, owner, low, high in result["prism_rows"] if owner in (0, 2)}
        self.assertEqual(planes, {(0., .1)})
        with self.assertRaisesRegex(ValueError, "Different nets share"):
            partition_board_volumes([lower, volume(box(.5, 0, 1.5, 1), .1, .2, "OTHER")], [],
                                    target_mm=.6, max_cells=5000)

    def test_disjoint_components_do_not_inherit_contact_or_z_cuts(self):
        left, right = box(0, 0, 1, 1), box(10, 0, 11, 1)
        volumes = [volume(MultiPolygon([left, right]))]
        plain = partition_board_volumes(volumes, [], target_mm=2., max_cells=5000)
        cut = partition_board_volumes(volumes,
            [{"id": "left-contact", "geometry": box(0, 0, .5, 1), "group_index": 0}],
            target_mm=2., max_cells=5000)
        def right_triangles(result):
            return [triangle for triangle in result["triangles"] if triangle[:, 0].min() >= 10]
        self.assertEqual(len(right_triangles(plain)), 2)
        self.assertEqual(len(right_triangles(cut)), 2)
        self.assertEqual(cut["stats"]["conforming_cluster_count"], 2)

    def test_overlap_partial_contact_and_budget_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            partition_board_volumes([volume(box(0, 0, 1, 1)), volume(box(.5, 0, 1.5, 1))], [],
                                    target_mm=1., max_cells=5000)
        with self.assertRaisesRegex(ValueError, "owning volume"):
            partition_board_volumes([volume(box(0, 0, 1, 1))],
                [{"id": "bad", "geometry": box(.8, .8, 1.2, 1.2), "group_index": 0}],
                target_mm=1., max_cells=5000)
        with self.assertRaisesRegex(ValueError, "budget"):
            partition_board_volumes([volume(box(0, 0, 10, 10))], [], target_mm=.1, max_cells=30)


if __name__ == "__main__":
    unittest.main()
