# SPDX-License-Identifier: Apache-2.0
"""Original analytical oracles and native-execution fixtures for passive models."""

import math
import os
from pathlib import Path
import unittest

from python.spikes.passive_models import build_model, impedance
from python.spikes.netlist import parse_netlist
from python.spikes.native_runner import run_native_project


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get("SPIKES_TEST_LIBRARY", os.environ.get(
    "SPIKES_TEST_NATIVE_LIBRARY", os.environ.get("SPIKES_NATIVE_LIBRARY",
    ROOT / "build-peec-native" / "spikes_c_api.dll"))))


class PassiveModelTests(unittest.TestCase):
    def test_ideal_limits(self):
        self.assertEqual(impedance(build_model("resistor", 100), 0), 100 + 0j)
        self.assertEqual(impedance(build_model("inductor", 1e-3), 0), 0j)
        self.assertTrue(math.isinf(impedance(build_model("capacitor", 1e-6), 0).real))
        self.assertEqual(impedance(build_model("capacitor", 1e-6, leakage_resistance_ohm=1e6), 0), 1e6 + 0j)
        f = 1 / (2 * math.pi)
        self.assertAlmostEqual(impedance(build_model("inductor", 3), f).imag, 3)
        self.assertAlmostEqual(impedance(build_model("capacitor", 0.25), f).imag, -4)

    def test_zero_parasitics_are_absent(self):
        for kind in ("resistor", "capacitor", "inductor"):
            model = build_model(kind, 1)
            project = parse_netlist(model["source"] + f"X1 a 0 {model['name']}\nV1 a 0 1\n.op\n")
            self.assertEqual(len(project.elements), 2)
            self.assertEqual(project.elements[0].positive_node, "a")
            self.assertEqual(project.elements[0].negative_node, "0")
            self.assertNotIn("INT", model["source"])

    def test_all_parasitics_parse_and_have_expected_topology(self):
        model = build_model("capacitor", 1e-6, series_resistance_ohm=0.1,
                            series_inductance_h=1e-9, parallel_capacitance_f=1e-12,
                            leakage_resistance_ohm=1e7)
        project = parse_netlist(model["source"] + "X1 a 0 SPK_PASSIVE\nV1 a 0 1\n.op\n")
        self.assertEqual([x.kind for x in project.elements[:5]],
                         ["resistor", "inductor", "capacitor", "capacitor", "resistor"])
        self.assertEqual(project.elements[3].positive_node, "a")
        self.assertEqual(project.elements[3].negative_node, "0")
        self.assertEqual(project.elements[2].negative_node, "0")

    def test_static_corner_and_temperature_only_change_primary(self):
        model = build_model("resistor", 100, tolerance_percent=5, corner=-1,
                            temperature_c=125, tc1_per_k=0.001, tc2_per_k2=1e-6,
                            series_resistance_ohm=2)
        self.assertAlmostEqual(model["effective_value"], 105.45)
        self.assertAlmostEqual(impedance(model, 0).real, 107.45)
        self.assertEqual(model["parameters"]["series_resistance_ohm"], 2)

    def test_capacitor_series_resonance(self):
        capacitance, inductance, esr = 1e-9, 1e-9, 0.2
        model = build_model("capacitor", capacitance, series_inductance_h=inductance,
                            series_resistance_ohm=esr)
        frequency = 1 / (2 * math.pi * math.sqrt(capacitance * inductance))
        self.assertAlmostEqual(frequency, 159154943.09189534, delta=1e-6)
        self.assertAlmostEqual(impedance(model, frequency).real, esr)
        self.assertAlmostEqual(impedance(model, frequency).imag, 0, delta=1e-14)
        self.assertLess(impedance(model, frequency / 10).imag, 0)
        self.assertGreater(impedance(model, frequency * 10).imag, 0)

    def test_parallel_resonance_and_loss(self):
        lossless = build_model("inductor", 1, parallel_capacitance_f=1)
        self.assertTrue(math.isinf(impedance(lossless, 1 / (2 * math.pi)).real))
        damped = build_model("inductor", 1, parallel_capacitance_f=1, leakage_resistance_ohm=50)
        self.assertAlmostEqual(impedance(damped, 1 / (2 * math.pi)).real, 50)
        self.assertAlmostEqual(impedance(damped, 1 / (2 * math.pi)).imag, 0)

    def test_parallel_resistor_capacitor_independent_oracle(self):
        # At wRC=1, multiply R/(1+j) by (1-j)/(1-j): R/2-jR/2.
        model = build_model("resistor", 20, parallel_capacitance_f=0.01)
        self.assertAlmostEqual(impedance(model, 5 / (2 * math.pi)), 10 - 10j)

    def test_kelvin_ideal_contacts_are_exact_voltage_branches(self):
        model = build_model("kelvin_shunt", 0.01)
        self.assertEqual(model["pins"], ["FP", "FN", "SP", "SN"])
        project = parse_netlist(model["source"] + "X1 a 0 sp sn SPK_PASSIVE\nI1 0 a 1\n.op\n")
        self.assertEqual([x.kind for x in project.elements[:3]],
                         ["voltage_source", "resistor", "voltage_source"])
        self.assertEqual(project.elements[0].value, 0)
        self.assertEqual(project.elements[2].value, 0)
        with self.assertRaisesRegex(ValueError, "four-terminal"):
            impedance(model, 1)

    def test_invalid_inputs_rejected(self):
        invalid = [dict(value=x) for x in (0, -1, math.inf, math.nan, True, "1")]
        invalid += [{key: bad} for key in ("series_resistance_ohm", "series_inductance_h",
                    "parallel_capacitance_f", "contact_resistance_ohm") for bad in (-1, math.nan)]
        invalid += [dict(leakage_resistance_ohm=x) for x in (0, -1, math.inf)]
        invalid += [dict(tolerance_percent=x) for x in (-1, 100)]
        invalid += [dict(corner=x) for x in (-1.1, 1.1, math.inf)]
        invalid += [dict(temperature_c=-273.15), dict(reference_temperature_c=-274),
                    dict(tc1_per_k=math.nan), dict(tc2_per_k2=math.inf),
                    dict(temperature_c=125, tc1_per_k=-0.01),
                    dict(temperature_c=1e308, tc2_per_k2=1e308),
                    dict(name="bad\nR1 a 0 1"), dict(kind="unknown")]
        for override in invalid:
            args = {"kind": "resistor", "value": 1, **override}
            with self.subTest(args=args), self.assertRaises(ValueError):
                build_model(**args)
        with self.assertRaises(ValueError):
            build_model("kelvin_shunt", 1, series_inductance_h=1e-9)
        with self.assertRaises(ValueError):
            build_model("resistor", 1, contact_resistance_ohm=1)
        for frequency in (-1, math.nan, math.inf, True):
            with self.subTest(frequency=frequency), self.assertRaises(ValueError):
                impedance(build_model("resistor", 1), frequency)
        with self.assertRaises(ValueError):
            impedance(build_model("inductor", 1e308), 1e308)
        with self.assertRaises(ValueError):
            impedance(build_model("capacitor", 1e308), 1e100)
        with self.assertRaises(ValueError):
            impedance(build_model("inductor", 1e-300), 1e-300)


@unittest.skipUnless(LIBRARY.is_file(), "Owned native SPIKES library is unavailable")
class NativePassiveModelTests(unittest.TestCase):
    def solve(self, model, body):
        project = parse_netlist(model["source"] + body, native_extensions=True)
        result = run_native_project(project, LIBRARY, integration_method="backward_euler")
        self.assertEqual(result.status, "completed", result.issues)
        return result.data

    def test_kelvin_contacts_and_finite_sense_load(self):
        for contact in (0, 0.02):
            for load in (None, 0.03):
                with self.subTest(contact=contact, load=load):
                    body = "I1 0 force 2\nX1 force 0 sp sn SPK_PASSIVE\n"
                    if load is not None:
                        body += f"RLOAD sp sn {load}\n"
                    data = self.solve(build_model("kelvin_shunt", 0.01,
                                      contact_resistance_ohm=contact), body + ".op\n")
                    equivalent = 0.01 if load is None else 0.01 * load / (0.01 + load)
                    nodes = data["node_voltage_v"]
                    self.assertAlmostEqual(nodes["sp"] - nodes["sn"], 2 * equivalent, delta=1e-10)
                    self.assertAlmostEqual(nodes["force"], 2 * (equivalent + 2 * contact), delta=1e-10)

    def test_native_capacitor_step_backward_euler_and_refinement(self):
        model = build_model("capacitor", 1e-6)
        errors = []
        for step in (1e-5, 5e-6):
            data = self.solve(model, "V1 supply 0 1\nR1 supply out 1000\n"
                              f"X1 out 0 SPK_PASSIVE\n.tran {step} 0.001 UIC\n")
            for t, voltage in zip(data["time_s"], data["node_voltage_v"]["out"], strict=True):
                expected = 1 - (1 + step / 0.001) ** (-round(t / step))
                self.assertAlmostEqual(voltage, expected, delta=1e-9)
            errors.append(abs(data["node_voltage_v"]["out"][-1] - (1 - math.exp(-1))))
        self.assertLess(errors[1], errors[0] * 0.51)

    def test_native_inductor_step_backward_euler(self):
        model = build_model("inductor", 1e-3, series_resistance_ohm=1)
        data = self.solve(model, "V1 supply 0 1\nX1 supply 0 SPK_PASSIVE\n.tran 10u 100u UIC\n")
        for t, current in zip(data["time_s"], data["element_current_a"]["X1:LBODY"], strict=True):
            self.assertAlmostEqual(current, 1 - 1.01 ** (-round(t / 1e-5)), delta=1e-9)


if __name__ == "__main__":
    unittest.main()
