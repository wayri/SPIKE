# SPDX-License-Identifier: Apache-2.0
"""Original constitutive-equation oracles for passive PDN PWL consistency.

These supplied lumped fixtures validate algebraic voltages and refinement,
not extraction, nonlinear switching, regulator models or physical boards.
"""

import math
import unittest

import numpy as np
from scipy.linalg import expm

from python.spike_core.pdn_network import PdnNetworkError, evaluate_pdn_network


def element(identifier, kind, **values):
    return {"id": identifier, "type": kind,
            "provenance": {"kind": "supplied", "source_id": "independent-PWL-equations"},
            **values}


def request(elements, nodes, period, divisions, *, ports=None):
    return {"contract": "spike/pdn-network-request/v1", "reference": "GND",
            "nodes": nodes, "elements": elements,
            "ports": ports or [{"id": "load", "mode": "single", "positive": nodes[0], "negative": "GND"}],
            "frequencies_hz": [1 / period],
            "load_transient": {"port_id": "load", "points": [
                {"time_s": 0., "current_a": 0.},
                {"time_s": period, "current_a": 1.},
                {"time_s": 2 * period, "current_a": 1.},
                {"time_s": 3 * period, "current_a": 0.}],
                "output_times_s": [i * period / 2 for i in range(7)],
                "max_step_s": period / divisions}}


def waveform(time, period):
    """Current, right-sided interior slope, and independently integrated charge.

    The final endpoint uses its left slope because the request ends there.
    """
    t = time / period
    if t < 1:
        return t, 1 / period, period * t * t / 2
    if t < 2:
        return 1., 0., period * (t - .5)
    return 3 - t, -1 / period, period * (1.5 + (t - 2) - (t - 2)**2 / 2)


class PdnTransientConsistencyTests(unittest.TestCase):
    def test_rl_ramp_hold_fall_exact_at_all_refinements(self):
        # Before correction every refinement returned -.5 V at T/2 instead
        # of -1.5 V, while reporting zero energy error.
        period = 1 / 1024
        for divisions in (4, 8, 16, 32, 64):
            with self.subTest(divisions=divisions):
                req = request([element("source", "source_output_impedance", positive="V",
                                       negative="GND", resistance_ohm=1., inductance_h=period)],
                              ["V"], period, divisions)
                result = evaluate_pdn_network(req)["load_transient"]
                for point in result["points"]:
                    current, slope, _ = waveform(point["time_s"], period)
                    self.assertAlmostEqual(point["port_voltage_v"]["load"],
                                           -current - period * slope, delta=2e-12)
                    self.assertAlmostEqual(point["stored_energy_j"],
                                           .5 * period * current**2, delta=2e-15)
                self.assertLess(result["energy_balance_relative_error"], 1e-12)

    def test_rl_consistency_across_si_time_scales(self):
        for period in (2**-30, 2**-10, 2**10):
            with self.subTest(period=period):
                req = request([element("source", "source_output_impedance", positive="V",
                                       negative="GND", resistance_ohm=.25, inductance_h=2 * period)],
                              ["V"], period, 8)
                for point in evaluate_pdn_network(req)["load_transient"]["points"]:
                    current, slope, _ = waveform(point["time_s"], period)
                    self.assertAlmostEqual(point["node_voltage_v"]["V"],
                                           -.25 * current - 2 * period * slope, delta=2e-12)

    def test_series_rlc_preserves_charge_and_energy_at_voltage_jumps(self):
        period, resistance, inductance, capacitance = 1 / 1024, .25, 1 / 2048, 1 / 512
        req = request([
            element("R", "resistor", positive="V", negative="M", resistance_ohm=resistance),
            element("L", "inductor", positive="M", negative="C", inductance_h=inductance, resistance_ohm=0.),
            element("C", "capacitor", positive="C", negative="GND", capacitance_f=capacitance)],
            ["V", "M", "C"], period, 8)
        result = evaluate_pdn_network(req)["load_transient"]
        for point in result["points"]:
            current, slope, charge = waveform(point["time_s"], period)
            voltage = -charge / capacitance
            self.assertAlmostEqual(point["node_voltage_v"]["C"], voltage, delta=2e-12)
            self.assertAlmostEqual(point["node_voltage_v"]["M"], voltage - inductance * slope, delta=2e-12)
            self.assertAlmostEqual(point["node_voltage_v"]["V"],
                                   voltage - inductance * slope - resistance * current, delta=2e-12)
            self.assertAlmostEqual(point["stored_energy_j"],
                                   .5 * inductance * current**2 + .5 * charge**2 / capacitance,
                                   delta=2e-15)
        self.assertLess(result["energy_balance_relative_error"], 1e-12)

    def test_signed_mutual_inductance_and_unexcited_winding_voltage(self):
        period, la, lb, coupling = 1 / 1024, 1 / 2048, 1 / 512, .75
        for polarity, sign in (("a_positive_to_b_positive", 1), ("opposing", -1)):
            with self.subTest(polarity=polarity):
                req = request([element("CM", "cm_choke",
                    winding_a={"positive": "A", "negative": "GND", "inductance_h": la, "resistance_ohm": .25},
                    winding_b={"positive": "B", "negative": "GND", "inductance_h": lb, "resistance_ohm": .5},
                    coupling_coefficient=coupling, polarity=polarity)], ["A", "B"], period, 8)
                mutual = sign * coupling * math.sqrt(la * lb)
                for point in evaluate_pdn_network(req)["load_transient"]["points"]:
                    current, slope, _ = waveform(point["time_s"], period)
                    self.assertAlmostEqual(point["node_voltage_v"]["A"], -.25 * current - la * slope, delta=2e-12)
                    self.assertAlmostEqual(point["node_voltage_v"]["B"], -mutual * slope, delta=2e-12)
                    self.assertAlmostEqual(point["stored_energy_j"], .5 * la * current**2, delta=2e-15)

    def test_floating_capacitor_island_keeps_its_differential_state(self):
        # Series L followed by parallel RC: the island common voltage jumps
        # with the load slope, but capacitor voltage follows RC convolution.
        req = request([
            element("R", "resistor", positive="V", negative="M", resistance_ohm=1.),
            element("C", "capacitor", positive="V", negative="M", capacitance_f=1.),
            element("L", "inductor", positive="M", negative="GND", inductance_h=.5, resistance_ohm=0.)],
            ["V", "M"], 1., 128)
        for point in evaluate_pdn_network(req)["load_transient"]["points"]:
            time = point["time_s"]
            current, slope, _ = waveform(time, 1.)
            # The RC response to a unit ramp is -(t-1+exp(-t)). Superpose
            # ramps starting at 0, 1, 2 s with slopes +1, -1, -1 A/s.
            differential = -sum(weight * (time - start + math.expm1(-(time - start)))
                                for start, weight in ((0., 1.), (1., -1.), (2., -1.)) if time >= start)
            actual = point["node_voltage_v"]
            # This floating-C descriptor reaches equilibrated condition
            # 1.32e5 at h=1/128; bound absolute algebraic roundoff separately
            # from the finite-step error in the dynamic capacitor voltage.
            self.assertAlmostEqual(actual["M"], -.5 * slope, delta=1e-8)
            self.assertAlmostEqual(actual["V"] - actual["M"], differential, delta=3e-6)
            self.assertAlmostEqual(point["stored_energy_j"], .25 * current**2 + .5 * differential**2,
                                   delta=3e-6)

    def test_rc_retains_second_order_transient_convergence(self):
        errors = []
        for divisions in (4, 8, 16):
            req = request([
                element("R", "resistor", positive="V", negative="GND", resistance_ohm=1.),
                element("C", "capacitor", positive="V", negative="GND", capacitance_f=1.)],
                ["V"], 1., divisions)
            point = evaluate_pdn_network(req)["load_transient"]["points"][4]
            exact = -(1 - math.exp(-1) + math.exp(-2))
            errors.append(abs(point["port_voltage_v"]["load"] - exact))
        self.assertGreater(errors[0] / errors[1], 3.9)
        self.assertGreater(errors[1] / errors[2], 3.9)
        self.assertLess(errors[2], 2e-4)

    def test_parallel_damped_rlc_converges_to_independent_state_exponential(self):
        resistance, inductance, capacitance = 2., 1., .5
        # Independent two-state ODE from KCL and v=L di/dt. Appending
        # current and its slope makes each PWL segment an exact autonomous
        # linear ODE; matrix exponentials avoid the descriptor/trapezoid path.
        matrix = np.array([[-1 / (resistance * capacitance), -1 / capacitance, -1 / capacitance, 0.],
                           [1 / inductance, 0., 0., 0.], [0., 0., 0., 1.], [0., 0., 0., 0.]])
        exact = []
        state = np.array([0., 0., 0., 1.])
        previous = 0.
        for time in np.arange(0., 3.01, .5):
            state = expm((time - previous) * matrix) @ state
            exact.append((float(state[0]), .5 * capacitance * state[0]**2 + .5 * inductance * state[1]**2))
            state[3] = waveform(time, 1.)[1]
            previous = time
        errors = []
        for divisions in (4, 8, 16, 32, 64):
            req = request([
                element("R", "resistor", positive="V", negative="GND", resistance_ohm=resistance),
                element("L", "inductor", positive="V", negative="GND", inductance_h=inductance, resistance_ohm=0.),
                element("C", "capacitor", positive="V", negative="GND", capacitance_f=capacitance)],
                ["V"], 1., divisions)
            result = evaluate_pdn_network(req)["load_transient"]
            errors.append(max(abs(point["node_voltage_v"]["V"] - voltage)
                              for point, (voltage, _) in zip(result["points"], exact)))
            if divisions == 64:
                for point, (_, energy) in zip(result["points"], exact):
                    self.assertAlmostEqual(point["stored_energy_j"], energy, delta=2e-4)
            self.assertLess(result["energy_balance_relative_error"], 1e-12)
        for coarse, fine in zip(errors, errors[1:]):
            self.assertGreater(coarse / fine, 3.8)
        self.assertLess(errors[-1], 2e-4)

    def test_nonzero_initial_current_and_nonfinite_slopes_rejected(self):
        for initial, period in ((1., 1.), (0., 1e-308)):
            req = request([element("L", "inductor", positive="V", negative="GND",
                                   inductance_h=1., resistance_ohm=0.)], ["V"], period, 4)
            req["frequencies_hz"] = [1.]
            req["load_transient"]["points"][0]["current_a"] = initial
            if initial == 0:
                req["load_transient"]["points"][1]["current_a"] = 1e308
            with self.subTest(initial=initial), self.assertRaises(PdnNetworkError) as caught:
                evaluate_pdn_network(req)
            self.assertEqual(caught.exception.code, "PDN_INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
