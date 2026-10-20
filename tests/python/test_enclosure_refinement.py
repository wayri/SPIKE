# SPDX-License-Identifier: Apache-2.0
"""Independent geometry, conservation, and rejection checks for enclosure grids."""
import copy
import math
import unittest

import numpy as np

from python.spike_core.enclosure_refinement import (
    EnclosureRefinementError,
    build_enclosure_grid,
    prolong_mac_fluxes,
)


def request(**updates):
    value = {
        "shape": [2, 2, 2],
        "spacing_m": [2.0, 3.0, 5.0],
        "origin_m": [-1.0, 10.0, 0.5],
        "local_refinement": [{
            "bounds_m": [[-0.5, 0.5], [12.0, 14.0], [1.0, 2.0]],
            "split_factor": 2,
        }],
    }
    value.update(updates)
    return value


def affine_faces(grid, slopes=(1.0, 2.0, -3.0), offsets=(0.2, -0.7, 1.1)):
    coarse_axes = grid["coarse_axes_m"]
    shape = grid["coarse_shape"]
    fields = []
    for axis in range(3):
        face_shape = list(shape)
        face_shape[axis] += 1
        coordinate_shape = [1, 1, 1]
        coordinate_shape[axis] = face_shape[axis]
        values = offsets[axis] + slopes[axis] * coarse_axes[axis].reshape(coordinate_shape)
        fields.append(np.broadcast_to(values, face_shape).copy())
    return tuple(fields)


class EnclosureGridTests(unittest.TestCase):
    def test_narrow_regions_insert_tensor_planes_and_preserve_coarse_cuts(self):
        grid = build_enclosure_grid(request())
        self.assertEqual(grid["coarse_shape"], (2, 2, 2))
        self.assertEqual(grid["shape"], (3, 4, 3))
        np.testing.assert_array_equal(grid["axes_m"][0], [-1.0, 0.0, 1.0, 3.0])
        np.testing.assert_array_equal(grid["axes_m"][1], [10.0, 11.5, 13.0, 14.5, 16.0])
        np.testing.assert_array_equal(grid["axes_m"][2], [0.5, 3.0, 5.5, 10.5])
        np.testing.assert_array_equal(grid["parent_indices"][0], [0, 0, 1])
        np.testing.assert_array_equal(grid["parent_indices"][1], [0, 0, 1, 1])
        np.testing.assert_array_equal(grid["parent_indices"][2], [0, 0, 1])
        for coarse, fine in zip(grid["coarse_axes_m"], grid["axes_m"]):
            self.assertTrue(set(coarse).issubset(set(fine)))
        self.assertEqual(grid["cell_volumes_m3"].shape, (3, 4, 3))
        self.assertEqual([item.shape for item in grid["face_areas_m2"]],
                         [(4, 4, 3), (3, 5, 3), (3, 4, 4)])

    def test_overlapping_factors_form_union_of_original_interval_cuts(self):
        value = request(shape=[1, 1, 1], spacing_m=[1.0, 1.0, 1.0], origin_m=[0.0] * 3,
                        local_refinement=[
                            {"bounds_m": [[0.1, 0.2]] * 3, "split_factor": 2},
                            {"bounds_m": [[0.8, 0.9]] * 3, "split_factor": 3},
                        ])
        grid = build_enclosure_grid(value)
        self.assertEqual(grid["shape"], (4, 4, 4))
        expected = [0.0, 1.0 / 3.0, 0.5, 2.0 / 3.0, 1.0]
        for axis in grid["axes_m"]:
            np.testing.assert_allclose(axis, expected, rtol=0.0, atol=0.0)

    def test_parent_material_and_volume_are_exactly_partitioned(self):
        grid = build_enclosure_grid(request())
        materials = np.arange(8).reshape((2, 2, 2))
        refined = materials[np.ix_(*grid["parent_indices"])]
        self.assertEqual(refined.shape, grid["shape"])
        for index in np.ndindex(grid["coarse_shape"]):
            mask = np.ones(grid["shape"], dtype=bool)
            for axis in range(3):
                selected = grid["parent_indices"][axis] == index[axis]
                view = [1, 1, 1]
                view[axis] = len(selected)
                mask &= selected.reshape(view)
            self.assertTrue(np.all(refined[mask] == materials[index]))
            self.assertAlmostEqual(float(np.sum(grid["cell_volumes_m3"][mask])), 30.0)
        self.assertAlmostEqual(float(np.sum(grid["cell_volumes_m3"])), 240.0)

    def test_unrefined_axis_ordering_and_empty_region_list(self):
        grid = build_enclosure_grid(request(local_refinement=[]))
        self.assertEqual(grid["shape"], (2, 2, 2))
        for axis in range(3):
            np.testing.assert_array_equal(grid["axes_m"][axis], grid["coarse_axes_m"][axis])
            np.testing.assert_array_equal(grid["parent_indices"][axis], [0, 1])

    def test_coordinate_translation_must_preserve_declared_metric(self):
        distorted = request(shape=[4, 4, 4], spacing_m=[0.3, 0.3, 0.3],
                            origin_m=[1e15, 1e15, 1e15], local_refinement=[])
        with self.assertRaisesRegex(EnclosureRefinementError, "declared spacing"):
            build_enclosure_grid(distorted)

        moderate = request(shape=[4, 4, 4], spacing_m=[0.3, 0.3, 0.3],
                           origin_m=[1000.0, 1000.0, 1000.0], local_refinement=[])
        grid = build_enclosure_grid(moderate)
        for axis in grid["coarse_axes_m"]:
            np.testing.assert_allclose(np.diff(axis), 0.3, rtol=1e-10, atol=0.0)

    def test_refined_subcuts_must_preserve_requested_fractional_metric(self):
        value = request(shape=[1, 1, 1], spacing_m=[0.3, 0.3, 0.3],
                        origin_m=[1e5, 1e5, 1e5], local_refinement=[{
                            "bounds_m": [[1e5, 1e5 + 0.3]] * 3,
                            "split_factor": 4,
                        }])
        with self.assertRaisesRegex(EnclosureRefinementError, "requested split widths"):
            build_enclosure_grid(value)

    def test_geometry_rejection_and_budgets(self):
        malformed = [
            {**request(), "extra": 1},
            request(shape=[True, 2, 2]),
            request(spacing_m=[10**1000, 1.0, 1.0]),
            request(spacing_m=[1.0, 0.0, 1.0]),
            request(spacing_m=[1.0, math.inf, 1.0]),
            request(origin_m=[0.0, math.nan, 0.0]),
            request(shape=[32, 32, 5], local_refinement=[]),
            request(origin_m=[1e308, 0.0, 0.0], spacing_m=[1.0, 1.0, 1.0],
                    local_refinement=[]),
            request(spacing_m=[1e-320, 1e-320, 1e-320], origin_m=[0.0, 0.0, 0.0],
                    local_refinement=[]),
            request(local_refinement=[{
                "bounds_m": [[-1.1, 0.0], [10.0, 11.0], [0.5, 1.0]],
                "split_factor": 2,
            }]),
            request(local_refinement=[{
                "bounds_m": [[0.0, 0.0], [10.0, 11.0], [0.5, 1.0]],
                "split_factor": 2,
            }]),
            request(local_refinement=[{
                "bounds_m": [[-1.0, 1.0], [10.0, 13.0], [0.5, 5.5]],
                "split_factor": True,
            }]),
        ]
        for value in malformed:
            with self.subTest(value=value):
                with self.assertRaises(EnclosureRefinementError):
                    build_enclosure_grid(value)

        axis_cap = request(shape=[32, 1, 1], spacing_m=[1.0] * 3, origin_m=[0.0] * 3,
                           local_refinement=[{
                               "bounds_m": [[0.0, 32.0], [0.0, 1.0], [0.0, 1.0]],
                               "split_factor": 4,
                           }])
        with self.assertRaisesRegex(EnclosureRefinementError, "64 intervals"):
            build_enclosure_grid(axis_cap)
        cell_cap = request(shape=[16, 16, 16], spacing_m=[1.0] * 3,
                           origin_m=[0.0] * 3, local_refinement=[{
                               "bounds_m": [[0.0, 16.0]] * 3, "split_factor": 2,
                           }])
        with self.assertRaisesRegex(EnclosureRefinementError, "8192 cells"):
            build_enclosure_grid(cell_cap)
        too_many = request(local_refinement=[{
            "bounds_m": [[-1.0, 0.0], [10.0, 11.0], [0.5, 1.0]],
            "split_factor": 2,
        }] * 65)
        with self.assertRaisesRegex(EnclosureRefinementError, "64 regions"):
            build_enclosure_grid(too_many)

    def test_build_cancellation_precedes_large_allocations(self):
        calls = []

        def cancel():
            calls.append(1)
            return len(calls) >= 2

        with self.assertRaises(InterruptedError):
            build_enclosure_grid(request(), cancel_check=cancel)


class MacFluxProlongationTests(unittest.TestCase):
    def setUp(self):
        self.grid = build_enclosure_grid(request())

    def test_independent_affine_divergence_free_field_and_face_integrals(self):
        coarse = affine_faces(self.grid)
        result = prolong_mac_fluxes(self.grid, coarse)
        fine = result["face_velocity_m_s"]
        for axis in range(3):
            shape = list(self.grid["shape"])
            shape[axis] += 1
            coordinate_shape = [1, 1, 1]
            coordinate_shape[axis] = shape[axis]
            expected = ((0.2, -0.7, 1.1)[axis]
                        + (1.0, 2.0, -3.0)[axis]
                        * self.grid["axes_m"][axis].reshape(coordinate_shape))
            np.testing.assert_allclose(fine[axis], np.broadcast_to(expected, shape),
                                       rtol=2e-15, atol=2e-15)
        diagnostics = result["diagnostics"]
        self.assertLess(diagnostics["maximum_coarse_divergence_s_inv"], 2e-15)
        self.assertLess(diagnostics["maximum_fine_divergence_s_inv"], 5e-15)
        self.assertLess(diagnostics["maximum_divergence_difference_relative"], 2e-15)
        self.assertLess(diagnostics["coarse_face_flux_integral_relative_error"], 2e-15)
        self.assertGreater(diagnostics["coarse_face_flux_integral_scale_m3_s"], 0.0)

    def test_fine_divergence_equals_parent_for_nonzero_coarse_divergence(self):
        coarse = affine_faces(self.grid, slopes=(1.0, 2.0, 4.0))
        result = prolong_mac_fluxes(self.grid, coarse)
        diagnostics = result["diagnostics"]
        self.assertAlmostEqual(diagnostics["maximum_coarse_divergence_s_inv"], 7.0)
        self.assertAlmostEqual(diagnostics["maximum_fine_divergence_s_inv"], 7.0)
        self.assertLess(diagnostics["maximum_divergence_difference_relative"], 2e-15)

    def test_arbitrary_coarse_patch_flux_equals_sum_of_fine_subfaces(self):
        coarse = []
        for axis in range(3):
            shape = list(self.grid["coarse_shape"])
            shape[axis] += 1
            coarse.append(np.arange(math.prod(shape), dtype=float).reshape(shape) - 3.5)
        fine = prolong_mac_fluxes(self.grid, coarse)["face_velocity_m_s"]
        for axis in range(3):
            tangential = [item for item in range(3) if item != axis]
            fine_plane = np.searchsorted(self.grid["axes_m"][axis],
                                         self.grid["coarse_axes_m"][axis])
            coarse_widths = [np.diff(item) for item in self.grid["coarse_axes_m"]]
            for face in range(self.grid["coarse_shape"][axis] + 1):
                for first in range(self.grid["coarse_shape"][tangential[0]]):
                    for second in range(self.grid["coarse_shape"][tangential[1]]):
                        ci = [0, 0, 0]
                        ci[axis], ci[tangential[0]], ci[tangential[1]] = face, first, second
                        expected = (coarse[axis][tuple(ci)]
                                    * coarse_widths[tangential[0]][first]
                                    * coarse_widths[tangential[1]][second])
                        fi = [None, None, None]
                        fi[axis] = np.asarray([fine_plane[face]])
                        fi[tangential[0]] = np.flatnonzero(
                            self.grid["parent_indices"][tangential[0]] == first)
                        fi[tangential[1]] = np.flatnonzero(
                            self.grid["parent_indices"][tangential[1]] == second)
                        selector = np.ix_(*fi)
                        actual = np.sum(fine[axis][selector]
                                        * self.grid["face_areas_m2"][axis][selector])
                        self.assertAlmostEqual(float(actual), float(expected), places=12)

    def test_zero_coarse_normal_faces_remain_exactly_zero(self):
        coarse = list(affine_faces(self.grid, slopes=(0.1, -0.2, 0.1)))
        for axis in range(3):
            low = [slice(None)] * 3
            high = [slice(None)] * 3
            low[axis] = 0
            high[axis] = -1
            coarse[axis][tuple(low)] = 0.0
            coarse[axis][tuple(high)] = 0.0
        result = prolong_mac_fluxes(self.grid, coarse)
        for axis, field in enumerate(result["face_velocity_m_s"]):
            low = [slice(None)] * 3
            high = [slice(None)] * 3
            low[axis] = 0
            high[axis] = -1
            self.assertTrue(np.all(field[tuple(low)] == 0.0))
            self.assertTrue(np.all(field[tuple(high)] == 0.0))
        self.assertGreater(result["diagnostics"]["zero_coarse_face_patches"], 0)
        self.assertEqual(
            result["diagnostics"]["zero_coarse_face_preservation_error_m_s"], 0.0)

    def test_large_cancelling_gradients_remain_finite(self):
        coarse = affine_faces(self.grid, slopes=(1e140, -1e140, 0.0), offsets=(0.0, 0.0, 0.0))
        result = prolong_mac_fluxes(self.grid, coarse)
        diagnostics = result["diagnostics"]
        self.assertTrue(all(math.isfinite(value) for key, value in diagnostics.items()
                            if key != "zero_coarse_face_patches"))
        self.assertLess(diagnostics["maximum_divergence_difference_relative"], 1e-14)

    def test_velocity_shape_type_finiteness_grid_and_cancellation_rejections(self):
        coarse = affine_faces(self.grid)
        invalid = [
            coarse[:2],
            (np.zeros((2, 2, 2)), coarse[1], coarse[2]),
            (np.zeros(coarse[0].shape, dtype=bool), coarse[1], coarse[2]),
            ([[[1.0]], [[2.0, 3.0]]], coarse[1], coarse[2]),
        ]
        nonfinite = list(copy.deepcopy(coarse))
        nonfinite[2][0, 0, 0] = math.nan
        invalid.append(tuple(nonfinite))
        for fields in invalid:
            with self.subTest(fields=type(fields)):
                with self.assertRaises(EnclosureRefinementError):
                    prolong_mac_fluxes(self.grid, fields)

        changed = dict(self.grid)
        changed["extra"] = None
        with self.assertRaises(EnclosureRefinementError):
            prolong_mac_fluxes(changed, coarse)
        with self.assertRaises(InterruptedError):
            prolong_mac_fluxes(self.grid, coarse, cancel_check=lambda: True)


if __name__ == "__main__":
    unittest.main()
