from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse import csr_matrix

from python.spike_core.acceleration import (
    AccelerationUnavailableError,
    _package_version,
    acceleration_catalog,
    assemble_graph_laplacian,
    choose_assembly_backend,
    choose_sparse_backend,
    solve_sparse_system,
)


class AccelerationTests(unittest.TestCase):
    def test_package_version_falls_back_to_frozen_module_metadata(self):
        module = type("FrozenModule", (), {"__version__": "9.8.7"})()
        with patch(
            "python.spike_core.acceleration.importlib.metadata.version",
            side_effect=__import__("importlib.metadata").metadata.PackageNotFoundError,
        ), patch("python.spike_core.acceleration.importlib.import_module", return_value=module):
            self.assertEqual(_package_version("frozen-package"), "9.8.7")

    def test_catalog_distinguishes_assembly_and_sparse_backends(self):
        catalog = acceleration_catalog()
        self.assertEqual(catalog["contract"], "spike/acceleration-catalog/v1")
        by_id = {item["id"]: item for item in catalog["backends"]}
        self.assertEqual(by_id["numba"]["kind"], "assembly")
        self.assertEqual(by_id["petsc-mumps"]["kind"], "sparse_direct")
        self.assertEqual(by_id["scipy-superlu"]["state"], "available")

    def test_numpy_graph_assembly_builds_expected_laplacian(self):
        rows, columns, values, metadata = assemble_graph_laplacian(
            [0, 1], [1, 2], [2.0, 4.0], requested="numpy"
        )
        matrix = csr_matrix((values, (rows, columns)), shape=(3, 3)).toarray()
        np.testing.assert_allclose(matrix, [[2, -2, 0], [-2, 6, -4], [0, -4, 4]])
        self.assertEqual(metadata["selected"], "numpy")
        self.assertFalse(metadata["fallback_used"])

    def test_superlu_solution_and_metadata_are_reproducible(self):
        matrix = csr_matrix([[4.0, -1.0], [-1.0, 3.0]])
        rhs = np.array([15.0, 10.0])
        solution, metadata = solve_sparse_system(matrix, rhs, requested="scipy-superlu")
        np.testing.assert_allclose(solution, np.linalg.solve(matrix.toarray(), rhs))
        self.assertEqual(metadata["selected"], "scipy-superlu")
        self.assertEqual(metadata["unknowns"], 2)

    def test_superlu_preserves_complex_solution_with_real_rhs(self):
        matrix = csr_matrix(np.array([[1.0 + 1.0j, 0.0], [0.0, 2.0 - 1.0j]]))
        rhs = np.array([1.0, 1.0])
        solution, metadata = solve_sparse_system(matrix, rhs, requested="scipy-superlu")

        np.testing.assert_allclose(solution, np.linalg.solve(matrix.toarray(), rhs))
        self.assertTrue(np.iscomplexobj(solution))
        self.assertTrue(metadata["complex_values"])

    def test_superlu_promotes_a_real_matrix_for_a_complex_rhs(self):
        matrix = csr_matrix(np.array([[3.0, 1.0], [1.0, 2.0]], dtype=np.float64))
        rhs = np.array([1.0 + 2.0j, 4.0 - 0.5j], dtype=np.complex128)
        solution, metadata = solve_sparse_system(matrix, rhs, requested="scipy-superlu")

        self.assertEqual(metadata["selected"], "scipy-superlu")
        self.assertEqual(solution.dtype, np.dtype(np.complex128))
        np.testing.assert_allclose(solution, np.linalg.solve(matrix.toarray().astype(np.complex128), rhs))

    def test_superlu_promotes_float32_matrix_for_float64_rhs(self):
        matrix = csr_matrix(np.array([[4.0, -1.0], [-1.0, 4.0]], dtype=np.float32))
        rhs = np.array([1.0, 2.0], dtype=np.float64)
        solution, _ = solve_sparse_system(matrix, rhs, requested="scipy-superlu")

        self.assertEqual(solution.dtype, np.dtype(np.float64))
        np.testing.assert_allclose(solution, np.linalg.solve(matrix.toarray().astype(np.float64), rhs))

    def test_auto_policy_only_selects_mumps_when_available_and_large(self):
        with patch("python.spike_core.acceleration._available_backend", return_value=True), patch.dict(
            os.environ, {"SPIKE_MUMPS_MIN_UNKNOWNS": "100"}
        ):
            selected = choose_sparse_backend(100, 500)
        self.assertEqual(selected["selected"], "petsc-mumps")

    def test_complex_auto_policy_skips_a_real_only_mumps_runtime(self):
        with patch("python.spike_core.acceleration._available_backend", return_value=True), patch(
            "python.spike_core.acceleration._backend_supports", return_value=False
        ), patch.dict(os.environ, {"SPIKE_MUMPS_MIN_UNKNOWNS": "1"}):
            selected = choose_sparse_backend(100, 500, complex_values=True)
        self.assertEqual(selected["selected"], "scipy-superlu")

    def test_explicit_complex_mumps_requires_complex_scalars(self):
        with patch("python.spike_core.acceleration._available_backend", return_value=True), patch(
            "python.spike_core.acceleration._backend_supports", return_value=False
        ):
            with self.assertRaisesRegex(AccelerationUnavailableError, "complex scalars"):
                choose_sparse_backend(100, 500, requested="petsc-mumps", complex_values=True)

    def test_explicit_unavailable_numba_is_not_silently_ignored(self):
        with patch("python.spike_core.acceleration._available_backend", return_value=False):
            with self.assertRaises(AccelerationUnavailableError):
                choose_assembly_backend(1000, requested="numba")


if __name__ == "__main__":
    unittest.main()
