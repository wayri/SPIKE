# SPDX-License-Identifier: Apache-2.0
"""Independent analytical and adversarial screens for explicit scalable RT0."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse import block_diag, csc_matrix, diags, eye
from scipy.sparse.linalg import splu

from python.spike_core.dc_tetra_rt0 import solve_tetra_dc, DCTetraRT0Error
from python.spike_core.dc_tetra_rt0_evidence import validate_tetra_dc
from python.spike_core.dc_tetra_sparse import solve_trace
from tests.python.test_dc_tetra_rt0 import slab, request, merge_meshes, faces_at, face_geometry


SCALABLE = "spike/tetra-dc-rt0-scalable-request/v1"


def scalable(raw):
    result = deepcopy(raw)
    result["contract"] = SCALABLE
    return result


class TetraScalingTests(unittest.TestCase):
    def test_thin_prism_direct_normal_operator_preserves_uniform_physics(self):
        # The former inverse-minus-rank-one local projection loses the scaled
        # symmetry guard on this admitted six-tetrahedron fixture (see evidence).
        raw = scalable(request(slab(1, size=(1., .73, .001)), sigma=2., current=.00073))
        result = solve_tetra_dc(raw)
        validate_tetra_dc(result)
        mesh = raw["mesh"]
        coordinates = np.asarray(mesh["vertices"])
        gauge = result["faces"][result["gauge_face_ids"][0]]
        gauge_offset = coordinates[gauge, 0].mean() / 2
        traces = np.asarray(result["face_potential_v"])
        for cell in result["cells"]:
            np.testing.assert_allclose(cell["vertex_density_a_m2"], np.tile([1., 0., 0.], (4, 1)), atol=1e-8, rtol=0.)
            self.assertAlmostEqual(cell["mean_potential_v"], gauge_offset - coordinates[cell["vertices"], 0].mean() / 2,
                                   delta=5e-9)
            self.assertAlmostEqual(cell["mean_potential_v"], traces[cell["face_ids"]].mean(), delta=1e-14)
            for opposite, face_id in enumerate(cell["face_ids"]):
                face = [node for local, node in enumerate(cell["vertices"]) if local != opposite]
                centroid, area_vector = face_geometry(mesh, face, cell["vertices"])
                self.assertAlmostEqual(traces[face_id], gauge_offset - centroid[0] / 2, delta=5e-9)
                self.assertAlmostEqual(cell["outward_face_current_a"][opposite], area_vector[0], delta=7.3e-13)
        self.assertAlmostEqual(result["joule_heat_w"], .000365, delta=3.65e-13)
        self.assertAlmostEqual(result["current_density_observable"]["physical_volume_m3"], .00073, delta=1e-15)

    def test_six_thousand_cells_uniform_analytical_field_and_retained_witness(self):
        raw = scalable(request(slab(10), sigma=2., current=3.))
        result = solve_tetra_dc(raw)
        validate_tetra_dc(result)
        self.assertEqual(len(result["cells"]), 6000)
        self.assertEqual(result["source_request"]["contract"], SCALABLE)
        for cell in result["cells"]:
            np.testing.assert_allclose(cell["vertex_density_a_m2"], np.tile([3., 0., 0.], (4, 1)), atol=1e-8, rtol=0.)
            self.assertLess(abs(math.fsum(cell["outward_face_current_a"])), 6e-9)
        self.assertAlmostEqual(result["joule_heat_w"], 4.5, delta=4.5e-9)
        self.assertAlmostEqual(result["current_density_observable"]["physical_volume_m3"], 1., places=12)
        self.assertLessEqual(result["diagnostics"]["scaled_condition_estimate"], 1e12)
        self.assertFalse(result["production_qualified"])

    def test_elongated_series_materials_matches_continuum_and_legacy_profile(self):
        raw = request(slab(4, size=(8., .5, .25)), sigma=2., current=.25)
        points = np.array(raw["mesh"]["vertices"])
        raw["conductivity_s_m"] = {cell["id"]: (2. if points[cell["vertices"], 0].mean() < 4. else 8.)
                                   for cell in raw["mesh"]["cells"]}
        legacy, extended = solve_tetra_dc(raw), solve_tetra_dc(scalable(raw))
        validate_tetra_dc(extended)
        # A=1/8 m^2; R=4/(2*A)+4/(8*A)=20 ohm, J=2 A/m^2.
        for cell in extended["cells"]:
            np.testing.assert_allclose(cell["vertex_density_a_m2"], np.tile([2., 0., 0.], (4, 1)), atol=2e-8, rtol=0.)
        self.assertAlmostEqual(extended["joule_heat_w"], 1.25, delta=1.25e-9)
        self.assertAlmostEqual(extended["contacts"][0]["mean_potential_v"] - extended["contacts"][1]["mean_potential_v"], 5., delta=5e-9)
        np.testing.assert_allclose(extended["face_potential_v"], legacy["face_potential_v"], atol=1e-9, rtol=0.)
        self.assertNotEqual(legacy["input_digest"], extended["input_digest"])

    def test_many_components_preserve_weak_drive_and_all_undriven_volume(self):
        mesh = slab(owner="b0")
        for i in range(1, 24):
            mesh = merge_meshes(mesh, slab(origin=(3. * i, 0., 0.), owner=f"b{i}"))
        raw = scalable(request(mesh, sigma=2.))
        raw["contacts"] = [{"id": str(i), "faces": faces_at(mesh, 0, x), "current_a": current}
                           for i, (x, current) in enumerate([(0., 1.), (1., -1.), (3., 1e-12), (4., -1e-12)])]
        result = solve_tetra_dc(raw)
        validate_tetra_dc(result)
        self.assertEqual(len(result["gauge_face_ids"]), 24)
        self.assertEqual(result["diagnostics"]["connected_components"], 24)
        self.assertAlmostEqual(result["current_density_observable"]["physical_volume_m3"], 24.)
        self.assertAlmostEqual(result["current_density_observable"]["undriven_volume_m3"], 22.)
        weak_power = math.fsum(c["joule_heat_w"] for c in result["cells"] if c["id"].startswith("b1-"))
        self.assertAlmostEqual(weak_power / 5e-25, 1., places=9)
        for cell in result["cells"]:
            index = int(cell["id"].split("-")[0][1:])
            expected = 1. if index == 0 else 1e-12 if index == 1 else 0.
            np.testing.assert_allclose(cell["vertex_density_a_m2"], np.tile([expected, 0., 0.], (4, 1)),
                                       atol=expected * 1e-9, rtol=1e-9)

    def test_explicit_profile_keeps_legacy_and_new_hard_limits(self):
        legacy = request()
        legacy["mesh"]["cells"] *= 834  # 5004 > legacy 5000.
        excess_cells = scalable(request())
        excess_cells["mesh"]["cells"] *= 8334  # 50004 > explicit profile 50000.
        excess_nodes = scalable(request())
        excess_nodes["mesh"]["vertices"] = [[0., 0., 0.]] * 50001
        for raw in (legacy, excess_cells, excess_nodes):
            with self.subTest(contract=raw["contract"]), \
                    patch("python.spike_core.dc_tetra_rt0_input.validate_geometry") as geometry, \
                    self.assertRaises(DCTetraRT0Error):
                solve_tetra_dc(raw)
            geometry.assert_not_called()

    def test_shift_invert_spectrum_and_solve_against_independent_sine_modes(self):
        # A tridiagonal(2,-1,-1) has eigenvectors sin(i*k*pi/(n+1)) and
        # eigenvalues 2-2*cos(k*pi/(n+1)); obtained by the sine addition law.
        for n in (12, 256):
            matrix = diags([-np.ones(n - 1), 2*np.ones(n), -np.ones(n - 1)], [-1, 0, 1], format="csc")
            expected = np.sin(np.arange(1, n + 1) * math.pi / (n + 1))
            rhs = matrix @ expected
            with patch("python.spike_core.dc_tetra_sparse.splu", wraps=splu) as factor:
                actual, diagnostics = solve_trace(matrix, rhs)
            self.assertEqual(factor.call_count, 1)
            np.testing.assert_allclose(actual, expected, atol=1e-11, rtol=0.)
            condition = (2 + 2*math.cos(math.pi / (n + 1))) / (2 - 2*math.cos(math.pi / (n + 1)))
            self.assertLess(abs(diagnostics["scaled_condition_estimate"] / condition - 1), 1e-7)

    def test_negative_hidden_mode_and_condition_limit_reject(self):
        hadamard = np.array([[1, 1, 1, 1], [1, -1, 1, -1], [1, 1, -1, -1], [1, -1, -1, 1]]) / 2
        negative = hadamard @ np.diag([-2., 1., 4., 8.]) @ hadamard.T
        # All diagonals are positive. The eigenvalue nearest zero is +1,
        # so shift-invert alone misses the -2 mode, even with tiny residuals.
        self.assertTrue(np.all(np.diag(negative) > 0))
        for matrix in (csc_matrix(negative), block_diag((negative, 2 * eye(128)), format="csc"),
                       diags([1e-14] + [1.] * 15, format="csc"),
                       diags([1e-14] + [1.] * 255, format="csc")):
            with self.subTest(size=matrix.shape[0]), self.assertRaises(ValueError):
                solve_trace(matrix, np.ones(matrix.shape[0]))

    def test_matrix_budget_asymmetry_and_cancellation_fail_before_factorization(self):
        oversized = eye(200001, format="csc")
        asymmetric = csc_matrix([[1., .5], [0., 1.]])
        for matrix in (oversized, asymmetric):
            with self.subTest(size=matrix.shape[0]), patch("python.spike_core.dc_tetra_sparse.splu") as factor, \
                    self.assertRaises(ValueError):
                solve_trace(matrix, np.ones(matrix.shape[0]))
            factor.assert_not_called()
        def cancelled():
            raise DCTetraRT0Error("cancelled")
        with patch("python.spike_core.dc_tetra_sparse.splu") as factor, self.assertRaisesRegex(ValueError, "cancelled"):
            solve_trace(eye(3, format="csc"), np.ones(3), cancelled)
        factor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
