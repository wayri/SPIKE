# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Independent DC nodal circuit and analytic constant-transfer checks."""
import unittest
import numpy as np
from python.spike_core.si_crosstalk import analyze_crosstalk, validate_model
from python.spike_core.sparameters import NetworkData

MAP = {"aggressor_near": 0, "aggressor_far": 2, "victim_near": 1, "victim_far": 3}


def network(matrix, z=None, frequencies=None):
    f = np.linspace(0, 8e9, 65) if frequencies is None else np.asarray(frequencies)
    return NetworkData(f, np.tile(matrix, (len(f), 1, 1)), np.ones(4) * 50 if z is None else z)


def trace(result, name):
    return np.array([row["real"] + 1j * row["imag"] for row in result["frequency_response"][name]["trace"]])


class CrosstalkTests(unittest.TestCase):
    def test_matched_offdiagonal_voltage_is_half_s(self):
        matrix = np.array([[0, .1, .5, .05], [.1, 0, .02, .5], [.5, .02, 0, .1], [.05, .5, .1, 0]])
        wave = [0, 0, 1, 1, .25, 0]
        result = analyze_crosstalk(network(matrix), port_map=MAP, termination_ohm=[50]*4, waveform_v=wave)
        np.testing.assert_allclose(trace(result, "next"), .05, atol=1e-14)
        np.testing.assert_allclose(trace(result, "fext"), .025, atol=1e-14)
        np.testing.assert_allclose(result["time_domain"]["next_v"], np.array(wave)*.05, atol=1e-14)
        self.assertFalse(result["production_qualified"])

    def test_unequal_reference_and_load_nodal_resistor_oracle(self):
        # Four conductors shunted to ground with three independent bridge resistors.
        y = np.diag([.01, .02, .03, .04])
        for a, b, resistance in ((0, 1, 200), (0, 3, 300), (1, 2, 400)):
            g = 1/resistance
            y[a,a] += g; y[b,b] += g; y[a,b] -= g; y[b,a] -= g
        refs = np.array([30., 60., 75., 100.])
        normalized = np.diag(np.sqrt(refs)) @ y @ np.diag(np.sqrt(refs))
        s = np.linalg.solve(np.eye(4)+normalized, np.eye(4)-normalized)
        loads = np.array([23., 100., 1000., 300.])
        rhs = np.array([1/loads[0], 0, 0, 0])
        expected = np.linalg.solve(y + np.diag(1/loads), rhs)
        result = analyze_crosstalk(network(s, refs), port_map=MAP, termination_ohm=loads.tolist())
        np.testing.assert_allclose(trace(result, "next"), expected[1], atol=1e-14)
        np.testing.assert_allclose(trace(result, "fext"), expected[3], atol=1e-14)

    def test_explicit_port_permutation(self):
        s = np.array([[0,.1,.5,.05],[.1,0,.02,.5],[.5,.02,0,.1],[.05,.5,.1,0]])
        a = analyze_crosstalk(network(s), port_map=MAP, termination_ohm=[50]*4)
        permutation = [3, 1, 0, 2]
        ports = {name: permutation.index(port) for name, port in MAP.items()}
        b = analyze_crosstalk(network(s[np.ix_(permutation,permutation)]), port_map=ports, termination_ohm=[50]*4)
        np.testing.assert_allclose(trace(a,"next"), trace(b,"next"), atol=1e-14)
        np.testing.assert_allclose(trace(a,"fext"), trace(b,"fext"), atol=1e-14)

    def test_uncoupled_network_zero_and_wave_superposition(self):
        s = np.array([[0,.1,.5,.05],[.1,0,.02,.5],[.5,.02,0,.1],[.05,.5,.1,0]])
        a = np.array([0,1,0,2,0,0]); b = np.array([0,0,1,0,-1,0])
        def solve(wave):
            return np.array(analyze_crosstalk(network(s), port_map=MAP, termination_ohm=[50]*4, waveform_v=wave.tolist())["time_domain"]["fext_v"])
        np.testing.assert_allclose(solve(a+b), solve(a)+solve(b), atol=1e-14)
        uncoupled = np.zeros((4,4)); uncoupled[0,2]=uncoupled[2,0]=1; uncoupled[1,3]=uncoupled[3,1]=1
        result = analyze_crosstalk(network(uncoupled), port_map=MAP, termination_ohm=[50]*4, waveform_v=a.tolist())
        np.testing.assert_allclose(result["time_domain"]["next_v"], 0, atol=1e-14)

    def test_no_invented_dc(self):
        result = analyze_crosstalk(network(np.zeros((4,4)), frequencies=[1e6, 2e6, 3e6]), port_map=MAP, termination_ohm=[50]*4, waveform_v=[0,1])
        self.assertEqual(result["time_domain"]["status"], "unsupported_grid")
        self.assertEqual(len(trace(result,"next")), 3)

    def test_downsample_preserves_peak_and_cancellation(self):
        s = np.zeros((4,4)); s[1,0]=s[0,1]=.1
        wave = [0.0]*2000; wave[897] = 1
        result = analyze_crosstalk(network(s), port_map=MAP, termination_ohm=[50]*4, waveform_v=wave, trace_limit=16)
        self.assertLessEqual(len(result["time_domain"]["next_v"]), 16)
        self.assertAlmostEqual(max(result["time_domain"]["next_v"]), .05)
        with self.assertRaisesRegex(ValueError, "cancelled"):
            analyze_crosstalk(network(s), port_map=MAP, termination_ohm=[50]*4, cancel_check=lambda: True)

    def test_bad_models_rejected(self):
        valid = {"port_map": MAP, "termination_ohm": [50]*4}
        for update in ({"extra": 1}, {"port_map": {**MAP,"victim_near":0}}, {"termination_ohm":[0]*4},
                       {"termination_ohm":[float("nan")]*4}, {"waveform_v":[True,0]}, {"trace_limit":True}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_model({**valid, **update})

    def test_singular_loaded_network_rejected(self):
        with self.assertRaisesRegex(ValueError,"singular"):
            analyze_crosstalk(network(np.eye(4)*3), port_map=MAP, termination_ohm=[100]*4)


if __name__ == "__main__":
    unittest.main()
