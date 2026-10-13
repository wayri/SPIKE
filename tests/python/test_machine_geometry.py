# SPDX-License-Identifier: Apache-2.0
"""Analytical geometry checks for independently authored machine meshes."""
import math
import unittest

import numpy as np

from python.spike_core.machine_geometry import (
    CONTRACT,
    MachineGeometryError,
    build_pm_machine_mesh,
    build_solenoid_mesh,
    validate_machine_mesh,
)


def region_areas(mesh):
    points = mesh["nodes_m"][mesh["triangles"]]
    areas = 0.5 * np.abs(
        (points[:, 1, 0] - points[:, 0, 0]) * (points[:, 2, 1] - points[:, 0, 1])
        - (points[:, 1, 1] - points[:, 0, 1]) * (points[:, 2, 0] - points[:, 0, 0])
    )
    region_ids = np.asarray(mesh["region_ids"], dtype=object)
    result = {}
    for region in set(region_ids):
        result[region] = float(np.sum(areas[region_ids == region]))
    return result


def signed_polygon_area(points):
    return 0.5 * float(np.sum(
        points[:-1, 0] * points[1:, 1] - points[1:, 0] * points[:-1, 1]
    ))


class MachineGeometryTests(unittest.TestCase):
    def assert_valid_mesh(self, mesh):
        self.assertEqual(mesh["contract"], CONTRACT)
        self.assertIsNotNone(validate_machine_mesh(mesh))
        nodes, triangles = mesh["nodes_m"], mesh["triangles"]
        self.assertEqual(nodes.shape[1], 2)
        self.assertEqual(triangles.shape[1], 3)
        self.assertEqual(len(mesh["region_ids"]), len(triangles))
        self.assertEqual(len(mesh["current_density_a_m2"]), len(triangles))
        points = nodes[triangles]
        twice_area = (
            (points[:, 1, 0] - points[:, 0, 0]) * (points[:, 2, 1] - points[:, 0, 1])
            - (points[:, 1, 1] - points[:, 0, 1]) * (points[:, 2, 0] - points[:, 0, 0])
        )
        self.assertTrue(np.all(twice_area > 0.0))
        self.assertTrue(set(mesh["region_ids"]).issubset(mesh["materials"]))
        boundary = mesh["boundary_nodes"]
        boundary_points = nodes[boundary]
        if mesh["meshing"]["outer_boundary_shape"] == "circle":
            radius = mesh["meshing"]["outer_boundary_radius_m"]
            np.testing.assert_allclose(
                np.linalg.norm(boundary_points, axis=1), radius, rtol=0.0, atol=2e-15
            )
        else:
            xmin, ymin = np.min(nodes, axis=0)
            xmax, ymax = np.max(nodes, axis=0)
            self.assertTrue(np.all(
                np.isclose(boundary_points[:, 0], xmin)
                | np.isclose(boundary_points[:, 0], xmax)
                | np.isclose(boundary_points[:, 1], ymin)
                | np.isclose(boundary_points[:, 1], ymax)
            ))
        self.assertFalse(mesh["meshing"]["sliding_interface"])
        self.assertEqual(mesh["meshing"]["model_status"], "approximate")

    def test_pm_regions_match_analytic_areas_under_refinement(self):
        settings = dict(
            air_box_half_extent_m=0.04,
            rotor_core_radius_m=0.009,
            magnet_outer_radius_m=0.013,
            stator_inner_radius_m=0.018,
            slot_outer_radius_m=0.025,
            stator_outer_radius_m=0.031,
            pole_pairs=2,
            slots=6,
            slot_angular_fraction=0.4,
        )
        coarse = build_pm_machine_mesh(target_edge_m=0.003, **settings)
        fine = build_pm_machine_mesh(target_edge_m=0.001, **settings)
        self.assert_valid_mesh(fine)
        exact = {
            "rotor_steel": math.pi * settings["rotor_core_radius_m"] ** 2,
            "magnets": math.pi * (
                settings["magnet_outer_radius_m"] ** 2
                - settings["rotor_core_radius_m"] ** 2
            ),
            "windings": settings["slot_angular_fraction"] * math.pi * (
                settings["slot_outer_radius_m"] ** 2
                - settings["stator_inner_radius_m"] ** 2
            ),
        }

        def measured(mesh):
            areas = region_areas(mesh)
            return {
                "rotor_steel": areas["rotor_steel"],
                "magnets": sum(areas[f"magnet_{index}"] for index in range(4)),
                "windings": areas["winding_pos"] + areas["winding_neg"],
            }

        coarse_values, fine_values = measured(coarse), measured(fine)
        for region, expected in exact.items():
            with self.subTest(region=region):
                coarse_error = abs(coarse_values[region] - expected)
                fine_error = abs(fine_values[region] - expected)
                self.assertLessEqual(fine_error, coarse_error + 2e-7)
                self.assertLess(fine_error, 0.06 * expected)

    def test_rotor_rotation_changes_geometry_attribution_and_remanence(self):
        baseline = build_pm_machine_mesh(target_edge_m=0.0015, rotor_angle_rad=0.0)
        angle = 0.173
        rotated = build_pm_machine_mesh(target_edge_m=0.0015, rotor_angle_rad=angle)
        self.assertFalse(np.array_equal(baseline["nodes_m"], rotated["nodes_m"]))
        self.assertTrue(rotated["meshing"]["moving_remesh"])
        self.assertTrue(rotated["meshing"]["conforming_material_interfaces"])
        before = np.asarray(baseline["materials"]["magnet_0"]["remanence_t"])
        after = np.asarray(rotated["materials"]["magnet_0"]["remanence_t"])
        rotation = np.asarray([
            [math.cos(angle), -math.sin(angle)],
            [math.sin(angle), math.cos(angle)],
        ])
        np.testing.assert_allclose(after, rotation @ before, rtol=0.0, atol=2e-15)
        self.assertEqual(
            rotated["motion"]["mover_region_ids"],
            ["rotor_steel", "magnet_0", "magnet_1", "magnet_2", "magnet_3"],
        )

    def test_pm_winding_has_explicit_balanced_element_sources(self):
        mesh = build_pm_machine_mesh(
            target_edge_m=0.001,
            winding_current_density_a_m2=2.5e6,
        )
        regions = np.asarray(mesh["region_ids"], dtype=object)
        source = np.asarray(mesh["current_density_a_m2"], dtype=float)
        self.assertTrue(np.all(source[regions == "winding_pos"] == 2.5e6))
        self.assertTrue(np.all(source[regions == "winding_neg"] == -2.5e6))
        self.assertTrue(np.all(source[~np.isin(regions, ["winding_pos", "winding_neg"])] == 0.0))
        areas = region_areas(mesh)
        self.assertAlmostEqual(areas["winding_pos"], areas["winding_neg"], delta=2e-6)

    def test_rotor_stress_contour_is_closed_ccw_and_inside_air_gap(self):
        mesh = build_pm_machine_mesh(
            magnet_outer_radius_m=0.014,
            stator_inner_radius_m=0.020,
        )
        contour = mesh["motion"]["stress_contour_m"]
        np.testing.assert_array_equal(contour[0], contour[-1])
        self.assertGreater(signed_polygon_area(contour), 0.0)
        radii = np.linalg.norm(contour, axis=1)
        self.assertTrue(np.all(radii > 0.014))
        self.assertTrue(np.all(radii < 0.020))

    def test_solenoid_regions_match_rectangular_analytic_areas(self):
        mesh = build_solenoid_mesh(
            target_edge_m=0.001,
            core_outer_width_m=0.050,
            stationary_core_height_m=0.025,
            core_leg_width_m=0.008,
            yoke_thickness_m=0.008,
            armature_width_m=0.046,
            armature_thickness_m=0.007,
            coil_clearance_m=0.001,
        )
        self.assert_valid_mesh(mesh)
        areas = region_areas(mesh)
        expected_stationary = 0.050 * 0.008 + 2.0 * 0.008 * (0.025 - 0.008)
        expected_armature = 0.046 * 0.007
        coil_width = (0.025 - 0.008 - 0.001) - 0.001
        coil_height = (-0.001) - (-0.025 + 0.008 + 0.001)
        self.assertAlmostEqual(areas["stationary_steel"], expected_stationary, delta=5e-5)
        self.assertAlmostEqual(areas["armature_steel"], expected_armature, delta=4e-5)
        self.assertAlmostEqual(areas["winding_pos"], coil_width * coil_height, delta=4e-5)
        self.assertAlmostEqual(areas["winding_neg"], coil_width * coil_height, delta=4e-5)

    def test_solenoid_translation_moves_only_armature_attribution(self):
        closed = build_solenoid_mesh(target_edge_m=0.001, plunger_position_m=0.0)
        opened = build_solenoid_mesh(target_edge_m=0.001, plunger_position_m=0.004)
        self.assertFalse(np.array_equal(closed["nodes_m"], opened["nodes_m"]))
        self.assertTrue(opened["meshing"]["moving_remesh"])
        self.assertTrue(opened["meshing"]["conforming_material_interfaces"])
        self.assertEqual(opened["motion"]["actual_gap_m"], 0.007)

    def test_polar_material_changes_only_across_conforming_mesh_edges(self):
        mesh = build_pm_machine_mesh(target_edge_m=0.0017, rotor_angle_rad=0.137)
        nodes = mesh["nodes_m"]
        triangles = mesh["triangles"]
        regions = mesh["region_ids"]
        points = nodes[triangles]
        areas = 0.5 * (
            (points[:, 1, 0] - points[:, 0, 0]) * (points[:, 2, 1] - points[:, 0, 1])
            - (points[:, 1, 1] - points[:, 0, 1]) * (points[:, 2, 0] - points[:, 0, 0])
        )
        self.assertGreater(float(np.min(areas)), 1e-3 * 0.0017 ** 2)
        owners = {}
        for triangle_index, triangle in enumerate(triangles):
            for a, b in ((triangle[0], triangle[1]), (triangle[1], triangle[2]),
                         (triangle[2], triangle[0])):
                edge = tuple(sorted((int(a), int(b))))
                owners.setdefault(edge, []).append(triangle_index)
        cross_region_edges = 0
        for edge, adjacent in owners.items():
            if len(adjacent) != 2 or regions[adjacent[0]] == regions[adjacent[1]]:
                continue
            cross_region_edges += 1
            first, second = nodes[list(edge)]
            radii = np.linalg.norm([first, second], axis=1)
            constant_radius = math.isclose(radii[0], radii[1], rel_tol=0.0, abs_tol=2e-14)
            same_ray = (
                abs(first[0] * second[1] - first[1] * second[0]) < 2e-14
                and float(first @ second) > 0.0
            )
            self.assertTrue(constant_radius or same_ray, (edge, first, second))
        self.assertGreater(cross_region_edges, 0)
        self.assertEqual(mesh["meshing"]["outer_boundary_shape"], "circle")
        self.assertEqual(mesh["meshing"]["curved_interfaces"], "inscribed_polygon_facets")

    def test_legacy_fixed_background_mode_remains_explicit(self):
        before = build_pm_machine_mesh(
            target_edge_m=0.003, rotor_angle_rad=0.0, mesh_method="fixed_cartesian"
        )
        after = build_pm_machine_mesh(
            target_edge_m=0.003, rotor_angle_rad=0.21, mesh_method="fixed_cartesian"
        )
        np.testing.assert_array_equal(before["nodes_m"], after["nodes_m"])
        np.testing.assert_array_equal(before["triangles"], after["triangles"])
        self.assertFalse(after["meshing"]["conforming_material_interfaces"])
        self.assertFalse(after["meshing"]["moving_remesh"])

    def test_conforming_pm_actual_solve_torque_has_shrinking_refinement_difference(self):
        from python.spike_core.magnetic_fem import solve_magnetostatic
        from python.spike_core.magnetic_machine_study import maxwell_stress_integral

        torques = []
        for edge in (0.002, 0.001, 0.0005):
            mesh = build_pm_machine_mesh(
                target_edge_m=edge,
                rotor_angle_rad=0.123,
                winding_current_density_a_m2=1.0e6,
                magnet_remanence_t=1.0,
                stack_depth_m=0.02,
            )
            field = solve_magnetostatic(
                nodes_m=mesh["nodes_m"],
                triangles=mesh["triangles"],
                region_ids=mesh["region_ids"],
                materials=mesh["materials"],
                stack_depth_m=mesh["stack_depth_m"],
                dirichlet_a_wb_per_m={int(index): 0.0 for index in mesh["boundary_nodes"]},
                current_density_a_per_m2=mesh["current_density_a_m2"],
                absolute_tolerance_a=1e-8,
            )
            corners = np.asarray(mesh["motion"]["stress_contour_m"])
            samples = []
            for start, end in zip(corners[:-1], corners[1:]):
                count = max(1, math.ceil(np.linalg.norm(end - start) / (edge / 4.0)))
                samples.extend(start + (end - start) * fraction
                               for fraction in np.arange(count) / count)
            contour = np.asarray([*samples, samples[0]])
            stress = maxwell_stress_integral(
                mesh["nodes_m"], mesh["triangles"], field["element_b_t"],
                mesh["region_ids"], contour, mesh["stack_depth_m"],
            )
            torques.append(stress["torque_n_m"])
        self.assertTrue(all(math.isfinite(value) and value < 0.0 for value in torques), torques)
        # This is only an observed refinement trend, not an accuracy gate.
        # No trusted machine torque reference or asymptotic order is available.
        self.assertLess(abs(torques[2] - torques[1]), abs(torques[1] - torques[0]), torques)

    def test_solenoid_stress_contour_is_closed_ccw_and_encloses_only_armature(self):
        mesh = build_solenoid_mesh(
            armature_width_m=0.046,
            armature_thickness_m=0.007,
            plunger_position_m=0.002,
        )
        contour = mesh["motion"]["stress_contour_m"]
        np.testing.assert_array_equal(contour[0], contour[-1])
        self.assertGreater(signed_polygon_area(contour), 0.0)
        gap = mesh["motion"]["actual_gap_m"]
        self.assertGreater(np.min(contour[:, 1]), 0.0)
        self.assertLess(np.min(contour[:, 1]), gap)
        self.assertGreater(np.max(contour[:, 1]), gap + 0.007)
        self.assertGreater(-np.min(contour[:, 0]), 0.5 * 0.046)
        self.assertGreater(np.max(contour[:, 0]), 0.5 * 0.046)

    def test_invalid_geometry_and_corrupted_triangle_fail_closed(self):
        with self.assertRaisesRegex(MachineGeometryError, "Radii"):
            build_pm_machine_mesh(magnet_outer_radius_m=0.025)
        with self.assertRaisesRegex(MachineGeometryError, "positive gap"):
            build_solenoid_mesh(plunger_position_m=-0.003)
        mesh = build_pm_machine_mesh(target_edge_m=0.004)
        damaged = dict(mesh)
        damaged["triangles"] = mesh["triangles"].copy()
        damaged["triangles"][0, 2] = damaged["triangles"][0, 1]
        with self.assertRaisesRegex(MachineGeometryError, "degenerate"):
            validate_machine_mesh(damaged)


if __name__ == "__main__":
    unittest.main()
