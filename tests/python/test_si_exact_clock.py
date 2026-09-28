# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Exact physical symbol timing, independently checked on a matched channel."""
import unittest
import math
import numpy as np
from python.spike_core.si_workflow import REQUEST, run_si_workflow
from python.spike_core.sparameters import touchstone_text, parse_touchstone_text
from python.spike_core.si_symbol_clock import sample_nrz_clock
from python.spike_core.si_channel import _prbs7, normalized_nrz_eye


def through(rate=10.3125e9, samples=15.7, points=513):
    f = np.arange(points) * (rate * samples / (2*points-1))
    s = np.tile(np.array([[0, 1], [1, 0]], dtype=complex), (points, 1, 1))
    return {"contract": REQUEST, "channel": {"kind": "touchstone", "name": "clock.s2p",
            "text": touchstone_text(f, s)}, "bit_rate_hz": rate, "bit_count": 1024,
            "sources": [{"port": 0, "low_v": 0, "high_v": 1, "rise_time_s": 0, "fall_time_s": 0}],
            "receivers": [{"port": 1, "resistance_ohm": 50, "capacitance_f": 0}],
            "run_time_domain": True}


class ExactClockTests(unittest.TestCase):
    def test_ramp_events_and_fractional_delay_match_piecewise_law(self):
        source = {"low_v": 0., "high_v": 1., "delay_s": .13,
                  "rise_time_s": .4, "fall_time_s": .4}
        times = np.array([0, .13, .33, .53, .83, 1.13, 1.33, 1.53, 1.83])
        actual = sample_nrz_clock([1, 0], times, 1., source)
        np.testing.assert_allclose(actual, [0, 0, .4, .8, 1, 1, .6, .2, 0], atol=1e-14)

    def test_slow_ramp_state_uses_physical_ui_end(self):
        source = {"low_v": 0., "high_v": 1., "delay_s": 0.,
                  "rise_time_s": 1.6, "fall_time_s": 1.6}
        times = np.array([.3, .9, 1.2, 1.8, 2.1, 2.7])
        np.testing.assert_allclose(sample_nrz_clock([1, 0, 1], times, 1., source),
                                   [.15, .45, .4, .1, .05, .35], atol=1e-14)

    def test_nonintegral_samples_do_not_change_physical_rate(self):
        request = through()
        result = run_si_workflow(request)["time_domain"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["represented_bit_rate_hz"], request["bit_rate_hz"])
        self.assertAlmostEqual(result["receivers"][0]["eye_height_v"], .5, delta=1e-10)
        self.assertAlmostEqual(result["actual_samples_per_ui"], 15.7, places=8)

    def test_normalized_eye_uses_same_exact_clock(self):
        q = through()
        network = parse_touchstone_text(q["channel"]["text"], "clock.s2p")
        r = normalized_nrz_eye(network, bit_rate_hz=q["bit_rate_hz"], bit_count=1024)
        self.assertEqual(r["represented_bit_rate_hz"], q["bit_rate_hz"])
        self.assertAlmostEqual(r["eye_height_normalized"], 1., delta=1e-12)

    def test_fixed_bandwidth_grid_changes_never_change_rate(self):
        for points in (257, 513, 1025, 2049):
            samples = (2*points-1) * (82e9/(points-1)) / 10.3125e9
            r = run_si_workflow(through(points=points, samples=samples))["time_domain"]
            self.assertEqual(r["represented_bit_rate_hz"], 10.3125e9)
            self.assertAlmostEqual(r["receivers"][0]["eye_height_v"], .5, delta=1e-10)

    def test_insufficient_samples_blocked(self):
        self.assertEqual(run_si_workflow(through(samples=7.9))["time_domain"]["status"], "blocked")

    def test_dense_touchstone_roundtrip_preserves_uniform_grid(self):
        self.assertEqual(run_si_workflow(through(samples=16, points=2049))["time_domain"]["status"], "completed")

    def test_rc_eye_converges_to_independent_continuous_time_ode(self):
        # tau*y'+y = u/2, tau=(50||50)*1.2pF. On each constant bit,
        # y(t)=u/2+(y(0)-u/2)*exp(-t/tau), with exact carried state.
        rate, tau, points = 10.3125e9, 30e-12, 2049
        errors = []
        for samples in (16, 32, 64, 128):
            q = through(samples=samples)
            q["channel"] = {"kind": "rlgc", "coupled": False, "length_m": 1e-9,
                "resistance_ohm_per_m": 0, "inductance_h_per_m": 250e-9,
                "capacitance_f_per_m": 100e-12, "loss_tangent": 0,
                "frequency_points": points, "frequency_stop_hz": rate*samples*(points-1)/(2*points-1),
                "reference_impedance_ohm": 50}
            # One-nanometre matched line: delay=5e-18s, negligible against
            # the 5mV oracle tolerance; no lossy-line reference is assumed.
            q["passives"] = [{"id": "rc", "port": 1, "connection": "shunt", "model": {
                "kind": "capacitor", "grade": "C0G", "capacitance_f": 1.2e-12,
                "esr_ohm": 0, "esl_h": 0, "leakage_ohm": 1e15}}]
            rx = run_si_workflow(q)["time_domain"]["receivers"][0]
            state, high, low = 0., [], []
            for index, bit in enumerate(_prbs7(1024)):
                value = .5*bit + (state-.5*bit)*math.exp(-(.5/rate+rx["cursor_delay_s"])/tau)
                if 16 <= index < 1022:
                    (high if bit else low).append(value)
                state = .5*bit + (state-.5*bit)*math.exp(-1/rate/tau)
            errors.append(abs(rx["eye_height_v"]-(min(high)-max(low))))
        self.assertTrue(all(b < a for a, b in zip(errors, errors[1:])), errors)
        self.assertLess(errors[-1], .005)  # 1% of matched 0.5V full swing.
