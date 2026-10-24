# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Regression coverage for allocation-only tetra energy assembly changes."""
import unittest

import numpy as np
from scipy.sparse import coo_matrix

from python.spike_core.cfd_tetra_energy import _assemble, _inputs, _temperature_lift
from tests.python.test_cfd_tetra_energy import base_request, layered_mesh


def original_loop_matrices(mesh, conductivity):
    """Independently retain the former scalar COO insertion definition."""
    nc, nf = len(mesh["cells"]), len(mesh["face_areas"])
    rows, cols, values = [], [], []
    drow, dcol, dval = [], [], []
    for cell, vertices in enumerate(mesh["cells"]):
        points = mesh["vertices"][vertices]
        local = points-points[0]
        offsets = local-local.mean(axis=0)
        covariance_trace = float(np.sum(offsets*offsets))/20.
        gram = np.sum(offsets[:, None, :]*offsets[None, :, :], axis=2)+covariance_trace
        signs = mesh["cell_face_signs"][cell]
        block = (gram/(9.*mesh["cell_volumes"][cell])/conductivity[cell]) * (
            signs[:, None]*signs[None, :])
        faces = mesh["cell_faces"][cell]
        for i in range(4):
            drow.append(cell); dcol.append(int(faces[i])); dval.append(int(signs[i]))
            for j in range(4):
                rows.append(int(faces[i])); cols.append(int(faces[j])); values.append(block[i, j])
    return (coo_matrix((values, (rows, cols)), shape=(nf, nf)).tocsr(),
            coo_matrix((dval, (drow, dcol)), shape=(nc, nf)).tocsr())


class TetraEnergyPerformanceRegressionTests(unittest.TestCase):
    def test_preallocated_triplets_preserve_original_matrices_and_forcing(self):
        request, _ = base_request(layered_mesh(2))
        request["source_w_m3"] = np.arange(len(request["mesh"]["cells"]), dtype=float)
        for index, boundary in enumerate(request["boundaries"].values(), 1):
            boundary["temperature_k"] = 300.+index
        values = _inputs(request, None)
        mesh, conductivity, cp, _, mass, source, anchor, boundaries, balance, _ = values
        lift = _temperature_lift(mesh, boundaries, anchor)
        actual = _assemble(mesh, conductivity, cp, mass, source, lift, boundaries, balance, None)
        expected_mixed, expected_divergence = original_loop_matrices(mesh, conductivity)
        for expected, observed in zip((expected_mixed, expected_divergence), actual[:2]):
            np.testing.assert_array_equal(observed.indptr, expected.indptr)
            np.testing.assert_array_equal(observed.indices, expected.indices)
            np.testing.assert_array_equal(observed.data, expected.data)
        expected_flux_rhs = np.zeros(len(mesh["face_areas"]))
        for patch, faces in mesh["boundary_patches"].items():
            expected_flux_rhs[faces] = -(request["boundaries"][patch]["temperature_k"]-lift)
        np.testing.assert_array_equal(actual[3], expected_flux_rhs)
        np.testing.assert_array_equal(actual[4], source*mesh["cell_volumes"]-lift*cp*balance)


if __name__ == "__main__":
    unittest.main()
