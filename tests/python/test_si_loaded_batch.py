# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import unittest
import numpy as np
from python.spike_core.sparameters import NetworkData
from python.spike_core.si_workflow import _loaded_response
from python.spike_core.si_passives import KB


class LoadedBatchTests(unittest.TestCase):
    def test_scalar_oracle_multiple_rhs_noise_and_chunk_tail(self):
        rng = np.random.default_rng(71)
        count, ports, sources = 259, 4, 3
        s = (rng.normal(size=(count, ports, ports)) + 1j*rng.normal(size=(count, ports, ports))) * .02
        z = np.array([35., 50., 75., 100.])
        network = NetworkData(np.arange(count, dtype=float), s, z)
        y = rng.uniform(.005, .03, (count, ports)) + 1j*rng.uniform(0, .01, (count, ports))
        drive = rng.normal(size=(count, ports, sources)).astype(complex)
        current = rng.uniform(0, 1e-20, (count, ports))
        actual = _loaded_response(network, y, drive, 40, current)
        expected = [[], [], []]
        root, identity = np.diag(np.sqrt(z)), np.eye(ports)
        for k, matrix in enumerate(s):
            load = np.diag(z*y[k])
            gain = root @ (identity+matrix) @ np.linalg.solve(identity+load+(load-identity)@matrix, root)
            expected[0].append(gain@drive[k])
            expected[1].append(abs(gain)**2 @ (4*KB*313.15*y[k].real))
            expected[2].append(abs(gain)**2 @ current[k])
        for result, reference in zip(actual, expected):
            np.testing.assert_allclose(result, reference, rtol=1e-13, atol=1e-30)


if __name__ == "__main__":
    unittest.main()
