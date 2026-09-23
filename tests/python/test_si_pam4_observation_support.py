# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Independent finite-record oracle: a pure delay preserves PAM4 levels.

The transfer exp(-j*2*pi*k*d/N) has a unit impulse at integer sample d
by discrete Fourier orthogonality. No external source or fixture is copied.
This verifies observation support, not a physical CDR or BER qualification.
"""

import unittest

import numpy as np

from python.spike_core.si_pam4_eye import SiPam4EyeError, pam4_eye
from python.spike_core.sparameters import NetworkData


def delayed_channel(delay_samples):
    frequencies = np.arange(4097, dtype=float) * 1e6
    transfer = np.exp(-2j * np.pi * np.arange(4097) * delay_samples / 8193)
    s = np.zeros((4097, 2, 2), dtype=complex)
    s[:, 1, 0] = transfer
    s[:, 0, 1] = transfer
    return NetworkData(frequencies, s, np.asarray([50.0, 50.0]))


class Pam4ObservationSupportTests(unittest.TestCase):
    def run_eye(self, delay, mode="fixed_center"):
        return pam4_eye(
            delayed_channel(delay), symbol_rate_hz=8193e6 / 8,
            symbol_count=256, model={"cdr_mode": mode},
        )

    def test_long_delay_does_not_extrapolate_constant_endpoint(self):
        result = self.run_eye(800)
        phase = result["bathtub"][0]
        np.testing.assert_allclose(phase["level_means"], [-1, -1/3, 1/3, 1], atol=1e-12)
        np.testing.assert_allclose(result["eye_heights_normalized"], [2/3] * 3, atol=1e-12)
        support = result["resource_admission"]
        self.assertEqual(support["observed_symbols_per_phase"], 122)
        self.assertFalse(support["response_extrapolation_used"])
        self.assertEqual(support["channel_peak_delay_samples"], 800)

    def test_phase_search_uses_one_common_observed_symbol_set(self):
        result = self.run_eye(800, "ideal_phase_search")
        support = result["resource_admission"]
        self.assertEqual(support["observed_symbols_per_phase"], 121)
        self.assertEqual(support["phase_evaluations"], 121 * 65)
        np.testing.assert_allclose(result["eye_heights_normalized"], [2/3] * 3, atol=1e-12)

    def test_delay_without_enough_observation_support_fails(self):
        with self.assertRaisesRegex(SiPam4EyeError, "channel delay"):
            self.run_eye(1600)

    def test_zero_delay_retains_original_sample_population(self):
        result = self.run_eye(0)
        self.assertEqual(result["resource_admission"]["observed_symbols_per_phase"], 220)
        np.testing.assert_allclose(result["eye_heights_normalized"], [2/3] * 3, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
