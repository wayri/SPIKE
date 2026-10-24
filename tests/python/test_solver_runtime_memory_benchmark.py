# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Contract tests for the fresh-process runtime/memory benchmark harness."""
import math
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import benchmark_solver_runtime_memory as benchmark


class SolverRuntimeMemoryBenchmarkTests(unittest.TestCase):
    def test_equivalence_rejects_bad_shape_keys_and_nonfinite(self):
        expected = {"a": [[1.0, 2.0]], "b": [3.0]}
        self.assertTrue(benchmark._equivalent(expected, expected))
        self.assertFalse(benchmark._equivalent({"a": [1.0, 2.0], "b": [3.0]}, expected))
        self.assertFalse(benchmark._equivalent({"a": [[1.0, 2.0]]}, expected))
        self.assertFalse(benchmark._equivalent({"a": [[1.0, math.nan]], "b": [3.0]}, expected))

    def test_missing_source_fails_closed(self):
        with patch.object(benchmark, "SOURCES", ("definitely-missing.file",)):
            with self.assertRaises(FileNotFoundError):
                benchmark._hash_sources()

    def test_parent_argument_bounds_and_fresh_output(self):
        output = Path(__file__).with_name("unused-runtime-memory-output.json")
        self.assertFalse(output.exists())
        benchmark._validate_parent_arguments(output, 1, 0.1)
        benchmark._validate_parent_arguments(output, 20, 600.0)
        with self.assertRaises(FileExistsError):
            benchmark._validate_parent_arguments(Path(__file__).resolve(), 5, 10.0)
        for samples in (0, 21):
            with self.assertRaises(ValueError):
                benchmark._validate_parent_arguments(Path("unused"), samples, 10.0)
        for timeout in (0.0, -1.0, 601.0, math.inf, math.nan):
            with self.assertRaises(ValueError):
                benchmark._validate_parent_arguments(Path("unused"), 5, timeout)

    def test_environment_does_not_mutate_parent(self):
        original = dict(os.environ)
        with patch.dict(os.environ, {"OMP_NUM_THREADS": "77", "SPIKE_BLAS_THREADS": "9"}, clear=False):
            before = dict(os.environ)
            default = benchmark._environment("backend-default")
            explicit = benchmark._environment("explicit-one-thread")
            self.assertEqual(dict(os.environ), before)
            self.assertNotIn("OMP_NUM_THREADS", default)
            self.assertNotIn("SPIKE_BLAS_THREADS", default)
            self.assertEqual(explicit["OMP_NUM_THREADS"], "1")
            self.assertEqual(explicit["SPIKE_BLAS_THREADS"], "1")
        self.assertEqual(dict(os.environ), original)


if __name__ == "__main__":
    unittest.main()
