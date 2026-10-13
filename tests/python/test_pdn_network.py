# SPDX-License-Identifier: Apache-2.0
"""Independent analytic passive-network fixtures; no board-validation claim."""

import copy
import math
import unittest
from unittest.mock import patch

from python.spike_core import pdn_network
from python.spike_core.pdn_network import PdnNetworkError, evaluate_pdn_network, validate_pdn_network


PROV = {"kind": "supplied", "source_id": "analytic-fixture"}


def element(identifier, kind, **values):
    return {"id": identifier, "type": kind, "provenance": dict(PROV), **values}


def basic(elements, nodes=None, ports=None, frequencies=None, transient=None):
    return {"contract": "spike/pdn-network-request/v1", "reference": "GND",
            "nodes": nodes or ["V"], "elements": elements,
            "ports": ports or [{"id": "load", "mode": "single", "positive": "V", "negative": "GND"}],
            "frequencies_hz": frequencies or [1000.], "load_transient": transient}


def z(result, row=0, col=0, index=0):
    value = result["ac"][index]["impedance_ohm"][row][col]
    return complex(value["real"], value["imag"])


class PdnNetworkTests(unittest.TestCase):
    def test_rc_ac_and_finite_rise_transient(self):
        resistance = 2.
        capacitance = 1e-3
        transient = {"port_id": "load", "points": [{"time_s": 0., "current_a": 0.},
                                                      {"time_s": 1e-5, "current_a": 1.},
                                                      {"time_s": .01, "current_a": 1.}],
                     "output_times_s": [0., 1e-5, .002, .01], "max_step_s": 2e-6}
        req = basic([element("R", "resistor", positive="V", negative="GND", resistance_ohm=resistance),
                     element("C", "net_ground_capacitance", node="V", capacitance_f=capacitance)], transient=transient)
        result = evaluate_pdn_network(req)
        expected = 1 / (1 / resistance + 2j * math.pi * 1000 * capacitance)
        self.assertAlmostEqual(z(result).real, expected.real, delta=1e-10)
        self.assertAlmostEqual(z(result).imag, expected.imag, delta=1e-10)
        self.assertEqual(result["diagnostics"]["provenance_counts"]["supplied"], 2)
        # After the ramp, convolution against the RC impulse response gives
        # R[1 - (RC/tr)(exp(-(t-tr)/RC)-exp(-t/RC))].
        tau, rise = resistance * capacitance, 1e-5
        for observation in result["load_transient"]["points"][2:]:
            t = observation["time_s"]
            droop = resistance * (1 - (tau / rise) *
                                  (math.exp(-(t-rise)/tau) - math.exp(-t/tau)))
            self.assertAlmostEqual(-observation["port_voltage_v"]["load"], droop, delta=2e-5)
        self.assertLess(result["load_transient"]["energy_balance_error_j"], 1e-9)

    def test_series_rlc_and_decap_equivalence(self):
        r, l, c = .05, 2e-6, 10e-6
        frequency = 10000.
        base = [element("decap", "decap", positive="V", negative="GND",
                        capacitance_f=c, esr_ohm=r, esl_h=l)]
        actual = evaluate_pdn_network(basic(base, frequencies=[frequency]))
        expected = r + 1j * (2 * math.pi * frequency * l - 1 / (2 * math.pi * frequency * c))
        self.assertAlmostEqual(z(actual).real, expected.real, delta=1e-10)
        self.assertAlmostEqual(z(actual).imag, expected.imag, delta=1e-10)

    def test_coupled_choke_sign_and_dm_cm(self):
        # Two coils to reference have Z = [[R+jwL,jwM],[jwM,R+jwL]].
        # DM I=[I,-I] gives Vdm/I=2R+jw(2L-2M).
        r, l, k, f = .2, 1e-3, .8, 1000.
        choke = element("CM1", "cm_choke",
                        winding_a={"positive": "A", "negative": "GND", "inductance_h": l, "resistance_ohm": r},
                        winding_b={"positive": "B", "negative": "GND", "inductance_h": l, "resistance_ohm": r},
                        coupling_coefficient=k, polarity="a_positive_to_b_positive")
        ports = [{"id": "dm", "mode": "differential", "positive": "A", "negative": "B"},
                 {"id": "a", "mode": "single", "positive": "A", "negative": "GND"},
                 {"id": "b", "mode": "single", "positive": "B", "negative": "GND"},
                 {"id": "cm", "mode": "common", "positive_nodes": ["A", "B"],
                  "negative_nodes": ["GND", "GND"]}]
        req = basic([choke], nodes=["A", "B"], ports=ports, frequencies=[f])
        result = evaluate_pdn_network(req)
        self.assertAlmostEqual(z(result).imag, 2 * (1-k) * 2 * math.pi * f * l, delta=1e-10)
        self.assertAlmostEqual(z(result, 1, 2).imag, k * 2 * math.pi * f * l, delta=1e-10)
        self.assertAlmostEqual(z(result, 3, 3).imag, .5 * (1+k) * 2 * math.pi * f * l, delta=1e-10)
        req["elements"][0]["polarity"] = "opposing"
        opposite = evaluate_pdn_network(req)
        self.assertAlmostEqual(z(opposite).imag, 2 * (1+k) * 2 * math.pi * f * l, delta=1e-10)

    def test_source_rl_and_transfer(self):
        req = basic([element("Zout", "source_output_impedance", positive="V", negative="GND",
                             resistance_ohm=.1, inductance_h=1e-6)], frequencies=[1000.])
        self.assertEqual(validate_pdn_network(req)["status"], "structurally_admitted")
        result = evaluate_pdn_network(req)
        self.assertAlmostEqual(z(result).real, .1, delta=1e-10)
        self.assertAlmostEqual(z(result).imag, 2 * math.pi * 1000 * 1e-6, delta=1e-10)

    def test_original_node_ac_transfer_and_transient_voltages(self):
        # Current enters IN, crosses 1-ohm R to OUT and charges 1-mF C.
        # KCL: Vout/I = 1/(jwC), Vin/I = R + Vout/I.
        c = 1e-3
        f = 1000.
        ramp = 1e-3
        req = basic([element("R", "resistor", positive="IN", negative="OUT", resistance_ohm=1.),
                     element("C", "capacitor", positive="OUT", negative="GND", capacitance_f=c)],
                    nodes=["IN", "OUT"],
                    ports=[{"id": "in", "mode": "single", "positive": "IN", "negative": "GND"},
                           {"id": "out", "mode": "single", "positive": "OUT", "negative": "GND"}],
                    frequencies=[f],
                    transient={"port_id": "in", "points": [{"time_s": 0., "current_a": 0.},
                                                               {"time_s": ramp, "current_a": 1.}],
                               "output_times_s": [0., ramp], "max_step_s": ramp / 100})
        result = evaluate_pdn_network(req)
        transfer = result["ac"][0]["node_transfer_impedance_ohm"]
        self.assertEqual(set(transfer), {"IN", "OUT"})
        zout = complex(**transfer["OUT"][0])
        zin = complex(**transfer["IN"][0])
        self.assertAlmostEqual(zout.imag, -1 / (2 * math.pi * f * c), delta=1e-10)
        self.assertAlmostEqual(zin.real, 1., delta=1e-10)
        self.assertAlmostEqual(zin.imag, zout.imag, delta=1e-10)
        self.assertAlmostEqual(z(result, 1, 0).imag, zout.imag, delta=1e-10)
        last = result["load_transient"]["points"][-1]
        self.assertEqual(result["load_transient"]["points"][0]["node_voltage_v"],
                         {"IN": 0., "OUT": 0.})
        self.assertAlmostEqual(last["node_voltage_v"]["OUT"], -.5 * ramp / c, delta=1e-10)
        self.assertAlmostEqual(last["node_voltage_v"]["IN"], last["node_voltage_v"]["OUT"] - 1., delta=1e-10)
        self.assertAlmostEqual(last["port_voltage_v"]["out"], last["node_voltage_v"]["OUT"], delta=1e-12)

    def test_return_to_zero_pulse_keeps_strict_energy_gate(self):
        pulse = {"port_id": "load", "points": [
            {"time_s": 0., "current_a": 0.}, {"time_s": 2e-6, "current_a": .1},
            {"time_s": .0005, "current_a": .1}, {"time_s": .000502, "current_a": 0.},
            {"time_s": .001, "current_a": 0.}],
            "output_times_s": [0., .0005, .000502, .001], "max_step_s": 2e-6}
        req = basic([
            element("source", "source_output_impedance", positive="IN", negative="GND",
                    resistance_ohm=.1, inductance_h=10e-9),
            element("choke", "dm_choke", positive="IN", negative="V",
                    resistance_ohm=.05, inductance_h=1e-6),
            element("decap", "decap", positive="V", negative="GND",
                    capacitance_f=10e-6, esr_ohm=.03, esl_h=5e-9),
            element("plane", "net_ground_capacitance", node="V", capacitance_f=1e-9)],
            nodes=["IN", "V"], frequencies=[100., 1000.], transient=pulse)
        result = evaluate_pdn_network(req)
        energy = result["load_transient"]
        self.assertLess(energy["energy_balance_relative_error"], 1e-10)
        self.assertLess(energy["energy_balance_error_j"], 1e-15)
        self.assertGreater(energy["energy_balance_scale_j"], energy["energy_balance_error_j"])

        original = pdn_network._solve_linear

        def corrupt_transient_state(system, rhs, where):
            state, residual, condition = original(system, rhs, where)
            if where.startswith("transient"):
                state = state * 1.05
            return state, residual, condition

        with patch.object(pdn_network, "_solve_linear", side_effect=corrupt_transient_state):
            with self.assertRaises(PdnNetworkError) as caught:
                evaluate_pdn_network(req)
        self.assertEqual(caught.exception.code, "PDN_ENERGY_FAILURE")

    def test_strict_failures(self):
        req = basic([element("R", "resistor", positive="V", negative="GND", resistance_ohm=1.)])
        cases = []
        bad = copy.deepcopy(req); bad["surprise"] = 1; cases.append((bad, "invalid_request"))
        bad = copy.deepcopy(req); bad["elements"][0]["provenance"]["kind"] = "assumed"; cases.append((bad, "invalid_request"))
        bad = copy.deepcopy(req); bad["elements"][0]["negative"] = "V"; cases.append((bad, "invalid_topology"))
        bad = copy.deepcopy(req); bad["frequencies_hz"] = [1000., 999.]; cases.append((bad, "invalid_request"))
        bad = basic([element("C", "capacitor", positive="V", negative="GND", capacitance_f=1e-6)])
        bad["nodes"] = ["V", "floating"]; cases.append((bad, "singular_network"))
        bad = copy.deepcopy(req); bad["nodes"] = [["V"]]; cases.append((bad, "invalid_request"))
        bad = copy.deepcopy(req); bad["elements"][0]["resistance_ohm"] = True; cases.append((bad, "invalid_request"))
        bad = copy.deepcopy(req); bad["elements"][0]["resistance_ohm"] = 10**10000; cases.append((bad, "invalid_request"))
        bad = copy.deepcopy(req); bad["frequencies_hz"] = [1e308]; cases.append((bad, "invalid_request"))
        for item, code in cases:
            with self.subTest(code=code), self.assertRaises(PdnNetworkError) as caught:
                evaluate_pdn_network(item)
            self.assertEqual(caught.exception.code, "PDN_" + code.upper())

    def test_cancellation_and_preflight_bounds(self):
        req = basic([element("R", "resistor", positive="V", negative="GND", resistance_ohm=1.)])
        calls = 0

        def cancel_at_ac():
            nonlocal calls
            calls += 1
            return calls == 4

        with self.assertRaises(PdnNetworkError) as caught:
            evaluate_pdn_network(req, cancel_check=cancel_at_ac)
        self.assertEqual(caught.exception.code, "PDN_CANCELLED")
        self.assertEqual(calls, 4)

        transient = {"port_id": "load", "points": [{"time_s": 0., "current_a": 0.},
                                                      {"time_s": 1e-3, "current_a": 1.}],
                     "output_times_s": [0., 1e-3], "max_step_s": 1e-4}
        req["load_transient"] = transient
        calls = 0

        def cancel_at_step():
            nonlocal calls
            calls += 1
            return calls == 5

        with self.assertRaises(PdnNetworkError) as caught:
            evaluate_pdn_network(req, cancel_check=cancel_at_step)
        self.assertEqual(caught.exception.code, "PDN_CANCELLED")
        self.assertEqual(calls, 5)
        self.assertEqual(validate_pdn_network(req)["transient_steps"], 10)

        req = basic([element(f"R{i}", "resistor", positive=f"N{i}", negative="GND",
                             resistance_ohm=1.) for i in range(64)],
                    nodes=[f"N{i}" for i in range(64)],
                    ports=[{"id": "p", "mode": "single", "positive": "N0", "negative": "GND"}],
                    frequencies=[float(i+1) for i in range(512)])
        with self.assertRaises(PdnNetworkError) as caught:
            validate_pdn_network(req)
        self.assertEqual(caught.exception.code, "PDN_RESOURCE_LIMIT")

        oversized = basic([element("R", "resistor", positive="V", negative="GND", resistance_ohm=1.)])
        oversized["elements"][0]["provenance"]["source_id"] = "x" * (8 * 1024 * 1024)
        with self.assertRaises(PdnNetworkError) as caught:
            validate_pdn_network(oversized)
        self.assertEqual(caught.exception.code, "PDN_RESOURCE_LIMIT")


if __name__ == "__main__":
    unittest.main()
