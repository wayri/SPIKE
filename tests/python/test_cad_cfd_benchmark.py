# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Adversarial cross-solver transfer checks, independent of constant-T success."""
import unittest
import itertools
import math
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scripts import benchmark_cad_cfd_open_flow as benchmark
from tests.python.test_cfd_tetra_stokes import box_mesh


class CadCfdBenchmarkTests(unittest.TestCase):
    def fixture(self):
        mesh = box_mesh(1)
        g = benchmark.admit_cfd_tetra_mesh(mesh)
        velocity = np.tile([1e-4, 0., 0.], (len(g["face_areas"]), 1))
        mass = g["face_areas"]*np.einsum("fd,fd->f", velocity, g["face_normals"])
        flow = {"fields": {"face_average_velocity_m_s": velocity.tolist()},
                "diagnostics": {"boundary_patch_outward_flux_m3_s": {
                    key: float(sum(mass[faces])) for key, faces in g["boundary_patches"].items()}}}
        return mesh, flow

    def result(self, request, multiplier):
        return {"status": "completed", "fields": {
            "temperature_k": [350.]*len(request["mesh"]["cells"]),
            "face_advective_heat_flow_w": (np.asarray(request["face_mass_flow_kg_s"])*350000.*multiplier).tolist()},
            "diagnostics": {}}

    def test_correct_transfer_and_reversed_or_scaled_enthalpy(self):
        mesh, flow = self.fixture()
        with patch.object(benchmark, "save"), patch.object(benchmark, "solve_cfd_tetra_energy",
                side_effect=lambda request: self.result(request, 1.)):
            result = benchmark.enthalpy_case(mesh, flow, Path("unused"))
            self.assertLess(result["signed_enthalpy_transfer_relative_error"], 1e-10)
        for multiplier in (-1., .1):
            with self.subTest(multiplier=multiplier), patch.object(benchmark, "save"), patch.object(
                    benchmark, "solve_cfd_tetra_energy",
                    side_effect=lambda request: self.result(request, multiplier)):
                with self.assertRaisesRegex(ValueError, "Signed source-flow"):
                    benchmark.enthalpy_case(mesh, flow, Path("unused"))

    def test_independent_degree_four_tetra_quadrature(self):
        # The production benchmark rule integrates velocity-error squares.
        bary, weight = benchmark.quadrature()
        for a, b, c in itertools.product(range(5), repeat=3):
            if a+b+c <= 4:
                exact = 6*math.factorial(a)*math.factorial(b)*math.factorial(c)/math.factorial(a+b+c+3)
                actual = sum(weight*bary[:, 1]**a*bary[:, 2]**b*bary[:, 3]**c)
                self.assertAlmostEqual(actual, exact, delta=5e-15)
        mesh = box_mesh(1)
        request = benchmark.flow_request(mesh, True)
        g = benchmark.admit_cfd_tetra_mesh(mesh)
        face_velocity = np.zeros((len(g["face_areas"]), 3))
        face_velocity[:, 0] = 1e-4+.1*g["face_centroids"][:, 1]
        result = {"fields": {"face_average_velocity_m_s": face_velocity.tolist(),
                             "cell_pressure_pa": [0.]*len(mesh["cells"])}}
        self.assertLess(benchmark.errors(request["mesh"], result, True)["relative_velocity_l2"], 1e-14)


if __name__ == "__main__":
    unittest.main()
