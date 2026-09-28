# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent continuous-time finite-edge NRZ timing reference fixtures."""
import unittest
import warnings

import numpy as np

from python.spike_core.si_clock_recovery import (
    MAX_INPUT_SAMPLES, recover_nrz_clock, validate_cdr_model,
)


def waveform(offset_ppm=0, drift_ppm=0, samples_per_ui=32, phase=0.23,
             count=3000, pattern="random"):
    """Knots straddle exact known crossings; no production stimulus helper."""
    rate = 1e9
    frequency = 1 + np.linspace(offset_ppm, offset_ppm + drift_ppm, count) * 1e-6
    boundaries = np.r_[phase, phase + np.cumsum(1 / frequency)]
    bits = (np.arange(count + 1) % 2 if pattern == "alternating"
            else np.random.default_rng(4761).integers(0, 2, count + 1))
    knots, levels = [-1.0], [float(bits[0])]
    for i, boundary in enumerate(boundaries[1:-1], 1):
        knots.extend([boundary - 0.1, boundary + 0.1])
        levels.extend([float(bits[i - 1]), float(bits[i])])
    knots.append(boundaries[-1] + 1)
    levels.append(float(bits[-2]))
    t = np.arange(0, boundaries[-1], 1 / samples_per_ui)
    return t / rate, np.interp(t, knots, levels), boundaries / rate, rate


def center_errors(result, boundaries, rate):
    samples = result["sample_times_s"]
    indices = np.searchsorted(boundaries, samples, side="right") - 1
    supported = (indices >= 0) & (indices + 1 < len(boundaries))
    indices = indices[supported]
    ideal = (boundaries[indices] + boundaries[indices + 1]) / 2
    return (samples[supported] - ideal) * rate


class ClockRecoveryTests(unittest.TestCase):
    def test_acquires_phase_and_signed_frequency_offset(self):
        for offset in (-4000, 4000):
            with self.subTest(offset=offset):
                t, v, b, rate = waveform(offset_ppm=offset)
                result = recover_nrz_clock(t, v, rate, {})
                error = center_errors(result, b, rate)
                self.assertLess(np.sqrt(np.mean(error[-500:] ** 2)), 1e-5)
                self.assertGreater(np.sqrt(np.mean(error[:32] ** 2)), 0.04)
                self.assertLess(abs(result["frequency_offset_ppm"][-1] - offset), 0.1)
                self.assertEqual(result["status"], "tracking")
                self.assertEqual(result["model_status"], "approximate")
                self.assertNotIn("locked", result)
                self.assertTrue(np.all(np.diff(result["sample_times_s"]) > 0))

    def test_tracks_frequency_drift_better_than_free_running(self):
        t, v, b, rate = waveform(offset_ppm=-2000, drift_ppm=4000)
        result = recover_nrz_clock(t, v, rate, {})
        recovered_error = center_errors(result, b, rate)[-500:]
        fixed = dict(sample_times_s=(np.arange(3000) + 0.5) / rate)
        fixed_error = center_errors(fixed, b, rate)[-500:]
        self.assertLess(np.sqrt(np.mean(recovered_error ** 2)), 0.003)
        self.assertLess(np.std(recovered_error), np.std(fixed_error) / 20)
        self.assertGreater(result["frequency_offset_ppm"][-1], 1800)

    def test_grid_convergence_on_smooth_known_crossings(self):
        # Cubic monotone edges are deliberately not exactly reproduced by the
        # detector's linear interpolation. Their true crossing is still b[k].
        errors = []
        for density in (8, 16, 32, 64):
            t, _, b, rate = waveform(samples_per_ui=density, pattern="alternating")
            index = np.searchsorted(b[1:-1], t)
            previous = np.maximum(index - 1, 0)
            following = np.minimum(index, len(b) - 3)
            before, after = b[1:-1][previous], b[1:-1][following]
            nearest = np.where(abs(t - before) < abs(t - after), previous, following)
            z = np.clip((t - b[1:-1][nearest]) * rate / 0.18, -1, 1)
            smooth = (3 * z - z ** 3) / 2
            v = (1 + smooth * np.where(nearest % 2 == 0, 1, -1)) / 2
            result = recover_nrz_clock(t, v, rate, {})
            errors.append(float(np.sqrt(np.mean(center_errors(result, b, rate)[-500:] ** 2))))
        self.assertTrue(all(a > b for a, b in zip(errors, errors[1:])), errors)
        self.assertLess(errors[-1], 1e-4)

    def test_no_transitions_never_claims_lock(self):
        t = np.arange(1024) / 32e9
        result = recover_nrz_clock(t, np.ones(len(t)), 1e9, {})
        self.assertEqual(result["status"], "insufficient_transitions")
        self.assertEqual(result["accepted_transition_count"], 0)
        np.testing.assert_allclose(result["period_s"], 1e-9)
        self.assertEqual(len(result["phase_error_ui"]), 0)

    def test_finite_record_bounds_and_voltage_affine_invariance(self):
        t, v, b, rate = waveform(count=400, phase=0.15)
        reference = recover_nrz_clock(t, v, rate, {})
        scaled = recover_nrz_clock(t, 2 * v - 3, rate,
                                   {"threshold_v": -2, "normalization_v": 2})
        np.testing.assert_allclose(reference["sample_times_s"], scaled["sample_times_s"], atol=1e-20)
        self.assertGreaterEqual(reference["sample_times_s"][0], t[0])
        self.assertLessEqual(reference["sample_times_s"][-1], t[-1])
        np.testing.assert_allclose(reference["sample_values_v"],
                                   np.interp(reference["sample_times_s"], t, v), atol=1e-12)

    def test_frequency_integrator_is_bounded(self):
        t, v, _, rate = waveform(offset_ppm=8000, count=1000)
        result = recover_nrz_clock(t, v, rate, {"max_frequency_offset_ppm": 1000})
        self.assertTrue(np.all(abs(result["frequency_offset_ppm"]) <= 1000 + 1e-8))
        self.assertGreater(result["frequency_bound_hit_count"], 0)

    def test_ambiguous_crossings_are_not_used_as_timing_evidence(self):
        t = np.arange(640) / 32e9
        # Two crossings straddle every nominal boundary. This is a ringing
        # stress fixture, not an admitted clean NRZ signal.
        v = np.where(abs(((t * 1e9 + 0.5) % 1) - 0.5) < 0.15, 1.0, 0.0)
        result = recover_nrz_clock(t, v, 1e9, {"initial_phase_ui": 0.99})
        self.assertGreater(result["ambiguous_gate_count"], 10)
        self.assertEqual(result["accepted_transition_count"], 0)
        self.assertEqual(result["status"], "insufficient_transitions")

    def test_initial_phase_and_absolute_record_origin(self):
        t, v, b, rate = waveform(count=100, phase=0.23)
        result = recover_nrz_clock(t, v, rate, {"initial_phase_ui": 0.23})
        shifted = recover_nrz_clock(t + 1e-3, v, rate, {"initial_phase_ui": 0.23})
        np.testing.assert_allclose(center_errors(result, b, rate), 0, atol=1e-10)
        np.testing.assert_allclose(shifted["sample_times_s"] - 1e-3,
                                   result["sample_times_s"], atol=1e-18, rtol=0)

    def test_invalid_configuration(self):
        for model in (None, {"kind": "gardner"}, {"typo": 1}, {"threshold_v": float("nan")},
                      {"threshold_v": 10 ** 400},
                      {"initial_phase_ui": 1}, {"normalization_v": 0}, {"proportional_gain": 0},
                      {"integral_gain": 0.3}, {"max_symbols": True}, {"max_symbols": 65537},
                      {"max_symbols": 1.5}, {"max_frequency_offset_ppm": 1e6}):
            with self.subTest(model=model), self.assertRaises(ValueError):
                validate_cdr_model(model)

    def test_invalid_samples_and_resource_limits(self):
        t = np.arange(64) / 16e9
        v = np.zeros(64)
        invalid = [(t[:-1], v, 1e9, {}), (t[::-1], v, 1e9, {}),
                   (t * 100, v, 1e9, {}), (t, v + 1j, 1e9, {}),
                   (t, v, 0, {}), (t, v, True, {}), (t, v, 1e9, {"max_symbols": 1}),
                   (t, np.full(64, np.nan), 1e9, {}),
                   (np.zeros((8, 8)), v, 1e9, {}),
                   (np.zeros(MAX_INPUT_SAMPLES + 1), np.zeros(4), 1e9, {})]
        for args in invalid:
            with self.assertRaises(ValueError):
                recover_nrz_clock(*args)

    def test_extreme_numbers_fail_cleanly_without_runtime_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            with self.assertRaises(ValueError):
                recover_nrz_clock(np.arange(4), np.zeros(4), 10 ** 400, {})
            with self.assertRaises(ValueError):
                recover_nrz_clock(np.array([-1e308, -9e307, 9e307, 1e308]),
                                   np.zeros(4), 1e9, {})


if __name__ == "__main__":
    unittest.main()
