# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent analytical and adversarial checks for bounded PAM3 execution."""

from math import erfc, sqrt
import unittest

import numpy as np

from python.spike_core.si_pam3 import (
    CONTRACT,
    MAX_SYMBOLS,
    SiPam3Error,
    pam3_eye,
    ternary_test_symbols,
)


def balanced_symbols(repeats: int = 100) -> list[int]:
    return [0, 1, 2] * repeats


def identity_result(**overrides):
    arguments = {
        "symbol_to_level_v": {0: -1.0, 1: 0.0, 2: 1.0},
        "channel_impulse": [1.0],
        "symbol_rate_hz": 2.0e9,
        "samples_per_ui": 8,
    }
    arguments.update(overrides)
    return pam3_eye(balanced_symbols(), **arguments)


class Pam3AnalyticalTests(unittest.TestCase):
    def test_identity_preserves_arbitrary_mapping_and_two_eyes(self):
        symbols = ["negative", "zero", "positive"] * 100
        result = pam3_eye(
            symbols,
            symbol_to_level_v={"positive": 0.9, "negative": -0.6, "zero": 0.0},
            channel_impulse=[1.0],
            symbol_rate_hz=4.0e9,
            samples_per_ui=8,
        )
        self.assertEqual(result["contract"], CONTRACT)
        self.assertEqual(result["source"]["modulation"], "PAM3")
        self.assertIsNone(result["source"]["protocol_encoding"])
        self.assertEqual(
            result["source"]["mapping"],
            [
                {"symbol": "negative", "level_v": -0.6},
                {"symbol": "zero", "level_v": 0.0},
                {"symbol": "positive", "level_v": 0.9},
            ],
        )
        self.assertEqual(len(result["eyes"]), 2)
        np.testing.assert_allclose(
            [eye["height_v"] for eye in result["eyes"]], [0.6, 0.9], atol=2e-15
        )
        np.testing.assert_allclose(result["receiver"]["thresholds_v"], [-0.3, 0.45], atol=2e-15)
        self.assertEqual(result["errors"]["observed_symbol_errors"], 0)
        self.assertEqual(result["errors"]["confusion_matrix"], [[100, 0, 0], [0, 100, 0], [0, 0, 100]])
        self.assertIn("no NRZ or PAM4 fallback", result["limitations"][0])

    def test_two_tap_symbol_spaced_fir_matches_hand_convolution(self):
        symbols = balanced_symbols(80)
        levels = np.asarray([-1.0, 0.0, 1.0])
        impulse = np.zeros(9)
        impulse[0] = 0.75
        impulse[8] = 0.25
        result = pam3_eye(
            symbols,
            symbol_to_level_v={0: -1.0, 1: 0.0, 2: 1.0},
            channel_impulse=impulse,
            channel_cursor_samples=0,
            symbol_rate_hz=1.0e9,
            samples_per_ui=8,
            sampling_phase_ui=0.5,
        )
        expected = [0.75 * levels[symbols[i]] + 0.25 * levels[symbols[i - 1]] for i in range(1, 33)]
        self.assertEqual(result["sampling"]["first_retained_symbol"], 1)
        np.testing.assert_allclose(result["noise"]["observed_sample_preview_v"], expected, atol=2e-15)
        self.assertEqual(result["channel"]["model"], "causal_sampled_lti_fir")

    def test_integer_sample_delay_preserves_levels_without_endpoint_extension(self):
        impulse = np.zeros(18)
        impulse[13] = 1.0
        result = identity_result(channel_impulse=impulse, channel_cursor_samples=13)
        self.assertEqual(result["sampling"]["channel_cursor_samples"], 13)
        self.assertEqual(result["sampling"]["first_retained_symbol"], 0)
        self.assertEqual(result["sampling"]["last_retained_symbol"], 297)
        np.testing.assert_allclose(
            [item["noiseless_mean_v"] for item in result["class_statistics"]],
            [-1.0, 0.0, 1.0],
            atol=2e-15,
        )
        self.assertTrue(result["resource_admission"]["full_fir_support_at_every_decision"])

    def test_explicit_bad_thresholds_produce_counted_symbol_errors(self):
        result = identity_result(decision_thresholds_v=[-1.5, 1.5])
        self.assertEqual(result["receiver"]["threshold_mode"], "explicit")
        self.assertEqual(result["errors"]["observed_symbol_errors"], 200)
        self.assertAlmostEqual(result["errors"]["observed_symbol_error_rate"], 2.0 / 3.0)
        self.assertAlmostEqual(result["errors"]["expected_symbol_error_rate_gaussian"], 2.0 / 3.0)
        self.assertEqual(result["errors"]["confusion_matrix"], [[0, 100, 0], [0, 100, 0], [0, 100, 0]])

    def test_gaussian_expected_ser_matches_three_level_threshold_integrals(self):
        sigma = 0.2
        result = pam3_eye(
            balanced_symbols(1000),
            symbol_to_level_v={0: -1.0, 1: 0.0, 2: 1.0},
            channel_impulse=[1.0],
            symbol_rate_hz=1.0e9,
            samples_per_ui=8,
            decision_thresholds_v=[-0.5, 0.5],
            voltage_noise_rms_v=sigma,
            noise_seed=20261023,
        )
        one_tail = 0.5 * erfc(0.5 / (sigma * sqrt(2.0)))
        self.assertAlmostEqual(
            result["errors"]["expected_symbol_error_rate_gaussian"],
            4.0 * one_tail / 3.0,
            places=15,
        )
        self.assertGreater(result["errors"]["observed_symbol_errors"], 0)
        self.assertLess(result["errors"]["observed_symbol_error_rate"], 0.05)

    def test_gaussian_rare_tail_uses_stable_survival_evaluation(self):
        sigma = 0.05
        result = identity_result(
            decision_thresholds_v=[-0.5, 0.5], voltage_noise_rms_v=sigma, noise_seed=9
        )
        one_tail = 0.5 * erfc(0.5 / (sigma * sqrt(2.0)))
        expected = 4.0 * one_tail / 3.0
        actual = result["errors"]["expected_symbol_error_rate_gaussian"]
        self.assertGreater(actual, 0.0)
        self.assertLess(abs(actual / expected - 1.0), 1.0e-12)

    def test_seeded_noise_is_reproducible_and_seed_local(self):
        first = identity_result(voltage_noise_rms_v=0.35, noise_seed=77)
        second = identity_result(voltage_noise_rms_v=0.35, noise_seed=77)
        third = identity_result(voltage_noise_rms_v=0.35, noise_seed=78)
        self.assertEqual(
            first["noise"]["observed_sample_sha256_float64_le"],
            second["noise"]["observed_sample_sha256_float64_le"],
        )
        self.assertEqual(
            first["noise"]["observed_sample_preview_v"],
            second["noise"]["observed_sample_preview_v"],
        )
        self.assertNotEqual(
            first["noise"]["observed_sample_sha256_float64_le"],
            third["noise"]["observed_sample_sha256_float64_le"],
        )

    def test_ternary_helper_is_reproducible_and_exercises_every_level(self):
        first = ternary_test_symbols(256, seed=11)
        np.testing.assert_array_equal(first, ternary_test_symbols(256, seed=11))
        self.assertFalse(np.array_equal(first, ternary_test_symbols(256, seed=12)))
        self.assertEqual(set(first.tolist()), {0, 1, 2})


class Pam3AdmissionTests(unittest.TestCase):
    def test_malformed_source_channel_sampling_and_thresholds_fail_closed(self):
        cases = [
            (balanced_symbols(10), {0: -1.0, 1: 0.0, 2: 1.0}, [1.0], {}, "64"),
            (balanced_symbols(), {0: -1.0, 1: -1.0, 2: 1.0}, [1.0], {}, "distinct"),
            ([0, 1, 3] * 100, {0: -1.0, 1: 0.0, 2: 1.0}, [1.0], {}, "absent"),
            (balanced_symbols(), {0: -1.0, 1: 0.0, 2: 1.0}, [float("nan")], {}, "finite"),
            (balanced_symbols(), {0: -1.0, 1: 0.0, 2: 1.0}, [0.0], {}, "all zero"),
            (balanced_symbols(), {0: -1.0, 1: 0.0, 2: 1.0}, [1.0], {"sampling_phase_ui": 1.0}, r"\[0, 1\)"),
            (balanced_symbols(), {0: -1.0, 1: 0.0, 2: 1.0}, [1.0], {"decision_thresholds_v": [0.5, -0.5]}, "increasing"),
            (balanced_symbols(), {0: -1.0, 1: 0.0, 2: 1.0}, [1.0], {"decision_thresholds_v": ["bad", 0.5]}, "finite real"),
            (balanced_symbols(), {0: -1.0, 1: 0.0, 2: 1.0}, [1.0 + 1.0j], {}, "real taps"),
        ]
        for symbols, mapping, impulse, extra, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(SiPam3Error, message):
                    pam3_eye(
                        symbols,
                        symbol_to_level_v=mapping,
                        channel_impulse=impulse,
                        symbol_rate_hz=1.0e9,
                        samples_per_ui=8,
                        **extra,
                    )

    def test_resource_limits_reject_before_large_fft(self):
        symbols = ([0, 1, 2] * 1400)[:4200]
        with self.assertRaisesRegex(SiPam3Error, "waveform needs"):
            pam3_eye(
                symbols,
                symbol_to_level_v={0: -1.0, 1: 0.0, 2: 1.0},
                channel_impulse=[1.0],
                symbol_rate_hz=1.0e9,
                samples_per_ui=256,
            )
        with self.assertRaisesRegex(SiPam3Error, "64"):
            pam3_eye(
                [0, 1, 2] * ((MAX_SYMBOLS + 3) // 3),
                symbol_to_level_v={0: -1.0, 1: 0.0, 2: 1.0},
                channel_impulse=[1.0],
                symbol_rate_hz=1.0e9,
                samples_per_ui=8,
            )

    def test_each_eye_requires_a_population_after_settling(self):
        symbols = [0] + [1, 2] * 40
        with self.assertRaisesRegex(SiPam3Error, "Each PAM3 level needs"):
            pam3_eye(
                symbols,
                symbol_to_level_v={0: -1.0, 1: 0.0, 2: 1.0},
                channel_impulse=[1.0],
                symbol_rate_hz=1.0e9,
                samples_per_ui=8,
            )

    def test_nonincreasing_received_means_require_explicit_receiver_handling(self):
        with self.assertRaisesRegex(SiPam3Error, "not strictly increasing"):
            pam3_eye(
                balanced_symbols(),
                symbol_to_level_v={0: -1.0, 1: 0.0, 2: 1.0},
                channel_impulse=[-1.0],
                symbol_rate_hz=1.0e9,
                samples_per_ui=8,
            )

    def test_cancellation_is_fail_closed(self):
        with self.assertRaisesRegex(SiPam3Error, "cancelled"):
            identity_result(cancel_check=lambda: True)


if __name__ == "__main__":
    unittest.main()
