# SPDX-License-Identifier: Apache-2.0
"""ACC01 exact amplitude-oracle and frozen-floor regression checks."""
import math
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.benchmark_circuit_timestep_accuracy import (
    ABSOLUTE_TOLERANCES,
    RISE_TIME_S,
    STOP_TIME_S,
    assess_waveforms,
    exact_observables,
    ramp_response_all_times,
    _run_amplitude_stratum,
    run_amplitude,
)


class CircuitAmplitudeAccuracyTests(unittest.TestCase):
    TIMES = (0.0, RISE_TIME_S / 2.0, RISE_TIME_S, 1.0e-4, STOP_TIME_S)

    @staticmethod
    def _exact(case_id, scale):
        references = [exact_observables(case_id, time_s, scale)
                      for time_s in CircuitAmplitudeAccuracyTests.TIMES]
        return (
            [reference["voltage_v"] for reference in references],
            [reference["current_a"] for reference in references],
        )

    def test_piecewise_ramp_oracle_covers_every_requested_time(self):
        tau = 1.0e-3
        at_zero = ramp_response_all_times(0.0, RISE_TIME_S, tau)
        at_rise = ramp_response_all_times(RISE_TIME_S, RISE_TIME_S, tau)
        expected_rise = 1.0 + tau / RISE_TIME_S * math.expm1(-RISE_TIME_S / tau)
        self.assertEqual(at_zero, 0.0)
        self.assertAlmostEqual(at_rise, expected_rise, places=15)
        self.assertGreater(ramp_response_all_times(STOP_TIME_S, RISE_TIME_S, tau), at_rise)

    def test_signed_and_zero_references_are_not_rescaled_or_fitted(self):
        for case_id in ("rc", "rl"):
            with self.subTest(case_id=case_id):
                positive_v, positive_i = self._exact(case_id, 1.0e-6)
                negative_v, negative_i = self._exact(case_id, -1.0e-6)
                zero_v, zero_i = self._exact(case_id, 0.0)
                self.assertEqual(negative_v, [-value for value in positive_v])
                self.assertEqual(negative_i, [-value for value in positive_i])
                self.assertEqual(zero_v, [0.0] * len(self.TIMES))
                self.assertEqual(zero_i, [0.0] * len(self.TIMES))

    def test_wrong_interior_sample_fails_even_with_exact_endpoint(self):
        voltage, current = self._exact("rc", 1.0)
        voltage[2] += 1.0e-4
        result = assess_waveforms("rc", 1.0, self.TIMES, voltage, current)
        self.assertEqual(result["gate_status"], "failed")
        self.assertFalse(result["observables"]["voltage"]["passed"])
        self.assertTrue(result["observables"]["current"]["passed"])
        self.assertEqual(result["observables"]["voltage"]["worst_time_s"], RISE_TIME_S)

    def test_zero_input_uses_frozen_voltage_and_current_floors(self):
        count = len(self.TIMES)
        voltage = [0.0] * count
        current = [0.0] * count
        voltage[1] = 0.9 * ABSOLUTE_TOLERANCES["voltage"]
        current[2] = 0.9 * ABSOLUTE_TOLERANCES["current"]
        passing = assess_waveforms("rl", 0.0, self.TIMES, voltage, current)
        self.assertEqual(passing["gate_status"], "passed")
        self.assertIsNone(passing["observables"]["voltage"]["normalization_scale"])
        self.assertIsNone(passing["observables"]["current"]["maximum_normalized_error"])

        voltage[1] = 1.1 * ABSOLUTE_TOLERANCES["voltage"]
        current[2] = 1.1 * ABSOLUTE_TOLERANCES["current"]
        failing = assess_waveforms("rl", 0.0, self.TIMES, voltage, current)
        self.assertFalse(failing["observables"]["voltage"]["passed"])
        self.assertFalse(failing["observables"]["current"]["passed"])

    def test_sign_reversal_cannot_pass_with_positive_waveforms(self):
        positive_v, positive_i = self._exact("rl", 1.0e-3)
        result = assess_waveforms("rl", -1.0e-3, self.TIMES, positive_v, positive_i)
        self.assertEqual(result["gate_status"], "failed")
        self.assertFalse(result["observables"]["voltage"]["passed"])
        self.assertFalse(result["observables"]["current"]["passed"])

    def test_current_normalization_uses_the_physical_case_scale(self):
        voltage, current = self._exact("rc", 1.0e-6)
        rc = assess_waveforms("rc", 1.0e-6, self.TIMES, voltage, current)
        self.assertEqual(rc["observables"]["voltage"]["normalization_scale"], 1.0e-6)
        self.assertAlmostEqual(rc["observables"]["current"]["normalization_scale"], 1.0e-9)
        voltage, current = self._exact("rl", -1.0e-6)
        rl = assess_waveforms("rl", -1.0e-6, self.TIMES, voltage, current)
        self.assertEqual(rl["observables"]["current"]["normalization_scale"], 1.0e-6)

    def test_malformed_or_nonfinite_waveforms_fail_closed(self):
        voltage, current = self._exact("rc", 1.0)
        invalid = (
            (self.TIMES, voltage[:-1], current),
            ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
            ((0.0, math.nan), (0.0, 0.0), (0.0, 0.0)),
        )
        for times, volts, amps in invalid:
            with self.subTest(times=times), self.assertRaises(ValueError):
                assess_waveforms("rc", 1.0, times, volts, amps)

    def test_explicit_method_mismatch_is_not_accepted_as_bound_evidence(self):
        # A synthetic wrong-backend response tests admission, not solver accuracy.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root/'fixture.dll'
            times = [0., STOP_TIME_S]
            reference = [exact_observables('rc', t, 1.) for t in times]
            payload = {'status': 'completed', 'data': {'time_s': times}, 'probes': {
                'V(out)': {'values': [r['voltage_v'] for r in reference]},
                'I(R1)': {'values': [r['current_a'] for r in reference]}}, 'provenance': {
                'solver': 'SPIKES owned C++ kernel', 'owned_cpp_transient': True,
                'library': str(library), 'integration': 'bdf2'}}
            completed = subprocess.CompletedProcess([], 0, json.dumps(payload).encode(), b'')
            with patch('scripts.benchmark_circuit_timestep_accuracy.subprocess.run', return_value=completed) as child:
                result = _run_amplitude_stratum(library, root, 'rc', 1., 2.5e-7, 2, 1, {}, 'radau_iia3')
            self.assertEqual(result['gate_status'], 'passed')
            self.assertEqual(result['backend_identity_status'], 'inconclusive')
            self.assertEqual(result['status'], 'inconclusive')
            self.assertIn('radau_iia3', child.call_args.args[0])

    def test_unknown_method_fails_before_artifact_or_native_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'new'
            with self.assertRaisesRegex(ValueError, 'method'):
                run_amplitude(Path(directory)/'missing.dll', output, integration_method='shell text')
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
