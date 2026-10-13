# SPDX-License-Identifier: Apache-2.0
"""Original analytical and differential oracles, not hardware qualification."""
import json
import math
import unittest

import numpy as np
from numpy.polynomial import polynomial as poly

from python.spikes.smps_stability import analyze, default_config, validate, TOPOLOGIES


class SmpsStabilityTests(unittest.TestCase):
    def test_equilibrium_dc_gain_and_energy(self):
        for topology in TOPOLOGIES:
            with self.subTest(topology=topology):
                n = 2. if topology == "flyback" else 1.
                cfg = dict(topology=topology, turns_ratio=n, duty_cycle=.4)
                report = analyze(cfg)
                point = report["operating_point"]
                d, vin, r = .4, 24., 6.
                expected = vin * d if topology == "buck" else (
                    vin / (1-d) if topology == "boost" else n * vin * d / (1-d))
                self.assertAlmostEqual(point["output_voltage_v"], expected)
                gain = vin if topology == "buck" else n * vin / (1-d)**2
                self.assertAlmostEqual(report["plant_dc_gain_v_per_duty"], gain)
                current_in = point["inductor_current_a"] * (1 if topology == "boost" else d)
                self.assertAlmostEqual(current_in * vin, point["output_power_w"])
                self.assertEqual(point["output_polarity"], -1 if topology == "buck_boost" else 1)

    def test_poles_and_rhp_zero_oracles(self):
        for topology in TOPOLOGIES:
            n = 1.5 if topology == "flyback" else 1.
            report = analyze(dict(topology=topology, turns_ratio=n))
            poles = [complex(*p) for p in report["plant_poles_rad_s"]]
            k = 1 if topology == "buck" else .5/n
            self.assertAlmostEqual(sum(poles).real, -1/(6*470e-6), places=9)
            self.assertAlmostEqual((poles[0]*poles[1]).real, k*k/(100e-6*470e-6), delta=1e-7)
            zeros = report["plant_zeros_rad_s"]
            if topology == "buck":
                self.assertEqual(zeros, [])
            else:
                expected = 6*.5**2/(100e-6*n*n)
                if topology != "boost":
                    expected /= .5
                self.assertAlmostEqual(zeros[0][0], expected, places=7)
                self.assertEqual(zeros[0][1], 0)

    def test_finite_difference_of_original_averaged_equations(self):
        for topology in TOPOLOGIES:
            n = .7 if topology == "flyback" else 1.
            cfg = dict(topology=topology, turns_ratio=n, duty_cycle=.37)
            report = analyze(cfg)
            op = report["operating_point"]
            state = np.array([op["inductor_current_a"], op["output_voltage_v"]])

            def derivative(x, d):
                i, v = x
                # Independently state the on/off equations, then time-weight.
                on_l = (24-v)/100e-6 if topology == "buck" else 24/100e-6
                off_l = (-v if topology == "buck" else 24-v if topology == "boost" else -v/n)/100e-6
                on_c = (i-v/6)/470e-6 if topology == "buck" else -v/(6*470e-6)
                off_c = (i/n-v/6)/470e-6
                return d*np.array([on_l, on_c])+(1-d)*np.array([off_l, off_c])

            np.testing.assert_allclose(derivative(state, .37), [0, 0], atol=1e-9)
            h = 1e-5
            jacobian = np.column_stack([(derivative(state+np.eye(2)[j]*h, .37)
                                        -derivative(state-np.eye(2)[j]*h, .37))/(2*h) for j in range(2)])
            bd = (derivative(state, .37+h)-derivative(state, .37-h))/(2*h)
            np.testing.assert_allclose(jacobian, report["state_space"]["a_per_s"], rtol=1e-8, atol=1e-6)
            np.testing.assert_allclose(bd, report["state_space"]["b_duty_per_s"], rtol=1e-9, atol=1e-6)
            plus, minus = analyze(dict(cfg, duty_cycle=.37+h)), analyze(dict(cfg, duty_cycle=.37-h))
            dc_derivative = (plus["operating_point"]["output_voltage_v"]-minus["operating_point"]["output_voltage_v"])/(2*h)
            self.assertAlmostEqual(dc_derivative, report["plant_dc_gain_v_per_duty"], delta=1e-6)

    def test_controller_transfer_and_state_response(self):
        for controller in ("pi", "type_ii", "type_iii"):
            report = analyze(dict(controller_type=controller, feedback_gain=.2, pwm_gain=.4))
            a = np.array(report["state_space"]["a_per_s"])
            b = np.array(report["state_space"]["b_duty_per_s"])
            for idx in (0, 170, 400):
                s = 2j*math.pi*report["frequency_hz"][idx]
                expected_plant = np.linalg.solve(s*np.eye(2)-a, b)[1]
                expected_controller = 100/s*(1+s/(2*math.pi*100))
                if controller != "pi":
                    expected_controller /= 1+s/(2*math.pi*10000)
                if controller == "type_iii":
                    expected_controller *= (1+s/(2*math.pi*1000))/(1+s/(2*math.pi*20000))
                np.testing.assert_allclose(complex(*report["plant"][idx]), expected_plant, rtol=1e-12)
                np.testing.assert_allclose(complex(*report["loop"][idx]), expected_plant*expected_controller*.08, rtol=1e-12)

    def test_pi_closed_loop_against_independent_routh_cubic(self):
        for gain in (.1, 1., 100.):
            report = analyze(dict(controller_type="pi", controller_gain=gain))
            a, b = 1/(6*470e-6), 1/(100e-6*470e-6)
            original = np.array([24*b*gain, b+24*b*gain/(2*math.pi*100), a, 1.])
            expected_stable = a*original[1] > original[0]
            self.assertEqual(report["stability"], "stable" if expected_stable else "unstable")
            for re, im in report["closed_loop_poles_rad_s"]:
                pole = complex(re, im)
                self.assertLess(abs(poly.polyval(pole, original))/poly.polyval(abs(pole), abs(original)), 1e-12)

    def test_all_crossings_grid_independent_and_residuals(self):
        fine = analyze(dict(controller_gain=5, points=10000))
        coarse = analyze(dict(controller_gain=5, points=3, start_hz=1e4, stop_hz=1e5))
        self.assertEqual(fine["stability"], "stable")
        self.assertEqual(len(fine["margins"]["gain_crossings"]), 3)
        for kind in ("gain_crossings", "phase_crossings"):
            self.assertEqual([p["frequency_hz"] for p in fine["margins"][kind]],
                             [p["frequency_hz"] for p in coarse["margins"][kind]])
            for crossing in fine["margins"][kind]:
                model = fine["rational_model"]
                x = 2j*math.pi*crossing["frequency_hz"]/model["omega_scale_rad_s"]
                response = poly.polyval(x, model["loop_numerator"])/poly.polyval(x, model["loop_denominator"])
                if kind == "gain_crossings":
                    self.assertAlmostEqual(abs(response), 1, places=10)
                else:
                    self.assertAlmostEqual(response.imag, 0, places=10)
                    self.assertLess(response.real, 0)
        self.assertTrue(coarse["warnings"])

    def test_invalid_inputs_and_mode_boundary(self):
        for config in (dict(inductance_h=0), dict(points=True), dict(points=10001),
                       dict(points=2), dict(input_voltage_v=float("inf")),
                       dict(controller_gain=float("nan")), dict(duty_cycle=1),
                       dict(start_hz=100, stop_hz=1), dict(topology="forward"),
                       dict(controller_type="current_mode"), dict(turns_ratio=2),
                       dict(esr_ohm=.1), dict(load_resistance_ohm=1e9),
                       dict(inductance_h=15e-6), dict(input_voltage_v=True),
                       dict(capacitance_f=1e-100)):
            with self.subTest(config=config), self.assertRaises(ValueError):
                analyze(config)
        self.assertEqual(validate(dict(points=3))["points"], 3)

    def test_power_scaling_is_mathematical_only(self):
        for power in (5., 1000., 1e6):
            resistance = 12**2/power
            report = analyze(dict(load_resistance_ohm=resistance,
                                  inductance_h=100e-6*resistance/6,
                                  capacitance_f=470e-6*6/resistance))
            self.assertAlmostEqual(report["operating_point"]["output_power_w"], power, delta=1e-8)
            self.assertEqual(report["model_status"], "approximate")
            self.assertTrue(any("power-level" in text for text in report["limitations"]))
            json.dumps(report, allow_nan=False)

    def test_default_is_not_mutated_and_stability_does_not_depend_on_sweep(self):
        config = default_config()
        saved = dict(config)
        report = analyze(config)
        self.assertEqual(config, saved)
        self.assertEqual(report["stability"], "unstable")
        narrow = analyze(dict(start_hz=1e-3, stop_hz=1e-2))
        self.assertEqual(narrow["closed_loop_poles_rad_s"], report["closed_loop_poles_rad_s"])
        self.assertFalse(any(p["in_sweep"] for p in narrow["margins"]["gain_crossings"]))


if __name__ == "__main__":
    unittest.main()
