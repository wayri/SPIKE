# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""API-spelling compatibility, not relaxed convergence or a solver fallback."""
import unittest
from unittest.mock import patch

from python.spike_core import cfd_tetra_stokes as stokes


class MinresCompatibilityTests(unittest.TestCase):
    def test_both_supported_spellings_receive_exact_original_tolerance(self):
        calls = []
        def old(a, b, *, M, maxiter, callback, tol):
            calls.append((a, b, M, maxiter, callback, tol))
            return "old", 0
        def new(a, b, *, M, maxiter, callback, rtol):
            calls.append((a, b, M, maxiter, callback, rtol))
            return "new", 0
        for function, expected in ((old, "old"), (new, "new")):
            with patch.object(stokes, "minres", function):
                self.assertEqual(stokes._minres_correction("A", "b", M="P", maxiter=5000,
                                                          callback="callback"), (expected, 0))
        self.assertEqual(calls, [("A", "b", "P", 5000, "callback", 1e-14)]*2)

    def test_unknown_api_and_internal_typeerror_do_not_retry(self):
        def unknown(a, b):
            self.fail("Unsupported API must not execute")
        with patch.object(stokes, "minres", unknown):
            with self.assertRaisesRegex(stokes.CfdTetraStokesError, "Unsupported MINRES"):
                stokes._minres_correction(None, None, M=None, maxiter=5000, callback=None)
        calls = []
        def broken(a, b, *, M, maxiter, callback, rtol):
            calls.append(1)
            raise TypeError("internal failure")
        with patch.object(stokes, "minres", broken):
            with self.assertRaisesRegex(TypeError, "internal failure"):
                stokes._minres_correction(None, None, M=None, maxiter=5000, callback=None)
        self.assertEqual(len(calls), 1)
