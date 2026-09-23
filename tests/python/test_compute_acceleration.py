from __future__ import annotations

import os
import unittest
from unittest.mock import patch
import numpy as np
from scipy.sparse import csr_matrix
from python.spike_core.acceleration import (
    AccelerationUnavailableError, assemble_graph_laplacian, choose_assembly_backend,
    choose_sparse_backend, solve_sparse_system,
)
from python.spike_core.compute_policy import cpu_thread_budget
from python.spike_core.gpu_acceleration import checked_solution, cuda_status, solve_cuda
from python.spikes.native_abi import _runtime_linear_threads


class ComputeAccelerationTests(unittest.TestCase):
    def test_thread_budget_uses_large_machines_and_bounds_overrides(self):
        with patch("os.cpu_count", return_value=32), patch("os.process_cpu_count", return_value=32, create=True), patch("os.sched_getaffinity", return_value=set(range(32)), create=True):
            for setting, expected in [("", 30), ("bad", 30), ("0", 30), ("1", 1), ("16", 16), ("999", 32)]:
                with self.subTest(setting=setting), patch.dict(os.environ, {"SPIKE_CPU_THREADS": setting}):
                    self.assertEqual(cpu_thread_budget(), expected)
            with patch.dict(os.environ, {"SPIKE_CPU_THREADS": "24"}):
                self.assertEqual(_runtime_linear_threads(True), 24)
                self.assertEqual(_runtime_linear_threads(False), 1, "old DLLs remain usable")

    def test_threaded_assembly_matches_serial_across_chunk_boundaries(self):
        count = 200003
        p = np.arange(count, dtype=np.int64) % 10000
        n = (p + 1) % 10000
        conductance = np.linspace(.01, 1000, count)
        expected = assemble_graph_laplacian(p, n, conductance, requested="numpy")
        with patch("python.spike_core.acceleration.cpu_thread_budget", return_value=4):
            actual = assemble_graph_laplacian(p, n, conductance, requested="numpy-threaded")
        for serial, threaded in zip(expected[:3], actual[:3]):
            np.testing.assert_array_equal(serial, threaded)
        self.assertEqual(actual[3]["threads"], 4)
        self.assertFalse(actual[3]["fallback_used"])
        empty = assemble_graph_laplacian(iter([]), iter([]), iter([]), requested="numpy-threaded")
        self.assertEqual(empty[0].size, 0)

    def test_auto_assembly_uses_budget_and_explicit_environment(self):
        with patch.dict(os.environ, {"SPIKE_ASSEMBLY_BACKEND": "auto", "SPIKE_PARALLEL_MIN_BRANCHES": "100"}), patch(
            "python.spike_core.acceleration.cpu_thread_budget", return_value=16
        ):
            self.assertEqual(choose_assembly_backend(100)["selected"], "numpy-threaded")
        with patch.dict(os.environ, {"SPIKE_ASSEMBLY_BACKEND": "numpy"}):
            self.assertEqual(choose_assembly_backend(1000000)["selected"], "numpy")

    def test_cuda_automatic_failure_falls_back_but_explicit_failure_surfaces(self):
        matrix = csr_matrix([[4., -1.], [-1., 3.]])
        rhs = np.array([15., 10.])
        with patch.dict(os.environ, {"SPIKE_SPARSE_BACKEND": "auto", "SPIKE_GPU_COMPUTE": "auto", "SPIKE_GPU_MIN_UNKNOWNS": "1"}), patch(
            "python.spike_core.acceleration.cuda_status", return_value=(True, "test", "")
        ), patch("python.spike_core.acceleration.solve_cuda", side_effect=MemoryError("allocation failed")):
            solution, metadata = solve_sparse_system(matrix, rhs)
            np.testing.assert_allclose(matrix @ solution, rhs)
            self.assertTrue(metadata["fallback_used"])
            self.assertEqual(metadata["selected"], "scipy-superlu")
            self.assertIn("allocation failed", metadata["fallback"])
            with patch("python.spike_core.acceleration._available_backend", return_value=True):
                with self.assertRaisesRegex(AccelerationUnavailableError, "allocation failed"):
                    solve_sparse_system(matrix, rhs, requested="cupy-cuda")

    def test_gpu_disabled_is_respected_in_automatic_policy(self):
        with patch.dict(os.environ, {"SPIKE_SPARSE_BACKEND": "auto", "SPIKE_GPU_COMPUTE": "off", "SPIKE_GPU_MIN_UNKNOWNS": "1"}), patch(
            "python.spike_core.acceleration.cuda_status", return_value=(True, "test", "")
        ):
            self.assertNotEqual(choose_sparse_backend(10, 10)["selected"], "cupy-cuda")

    def test_original_system_validation_rejects_inaccurate_or_invalid_gpu_results(self):
        for dtype in (np.float64, np.complex128):
            matrix = csr_matrix(np.array([[4, -1], [-1, 3]], dtype=dtype))
            for rhs in (np.array([15, 10], dtype=dtype), np.array([[15, 0], [10, 0]], dtype=dtype)):
                solution = np.linalg.solve(matrix.toarray(), rhs)
                self.assertLess(checked_solution(matrix, rhs, solution), 1e-12)
                with self.assertRaisesRegex(RuntimeError, "residual"):
                    checked_solution(matrix, rhs, solution + .1)
                with self.assertRaises(RuntimeError):
                    checked_solution(matrix, rhs, np.full_like(rhs, np.nan))
                with self.assertRaises(RuntimeError):
                    checked_solution(matrix, rhs, np.zeros(3))

    def test_residual_scaling_overflow_cannot_accept_a_wrong_solution(self):
        matrix = csr_matrix([[1.e308]])
        with np.errstate(over="ignore", invalid="ignore"), self.assertRaisesRegex(RuntimeError, "overflowed"):
            checked_solution(matrix, np.array([1.e308]), np.array([2.]))

    @unittest.skipUnless(cuda_status()[0], "CUDA/CuPy runtime unavailable")
    def test_real_cuda_solver_matches_original_real_and_complex_systems(self):
        for dtype in (np.float64, np.complex128):
            matrix = csr_matrix(np.array([[4, -1], [-1, 3]], dtype=dtype))
            rhs = np.array([15, 10], dtype=dtype)
            np.testing.assert_allclose(matrix @ solve_cuda(matrix, rhs), rhs, rtol=1e-9)


if __name__ == "__main__":
    unittest.main()
