# SPDX-License-Identifier: Apache-2.0
"""Owned fixtures for capacitor-state directives and existing source support."""

import math
import os
from pathlib import Path
import unittest

from python.spikes.contracts import CircuitProject
from python.spikes.netlist import NetlistParseError, parse_netlist
from python.spikes.native_runner import run_native_project


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get("SPIKES_TEST_NATIVE_LIBRARY", os.environ.get(
    "SPIKES_NATIVE_LIBRARY", ROOT / "build-peec-native" / "spikes_c_api.dll")))


class InitialDirectiveTests(unittest.TestCase):
    def parse(self, body, analysis=".tran 10u 30u UIC"):
        return parse_netlist(body + "\n" + analysis + "\n", native_extensions=True)

    def test_grounded_state_is_lowered_and_roundtrips(self):
        project = self.parse("R1 out 0 1k\nC1 out 0 1u\n.ic V(OUT) = 3V")
        self.assertEqual(project.elements[1].initial_condition, 3.0)
        self.assertEqual(CircuitProject.from_dict(project.to_dict()), project)

    def test_both_nodes_and_reversed_orientation(self):
        project = self.parse("C1 a b 1u\nC2 0 a 1u\nR1 a 0 1k\nR2 b 0 1k\n.ic V(a)=3 V(b)=-2 V(0)=0")
        self.assertEqual([item.initial_condition for item in project.elements[:2]], [5.0, -3.0])

    def test_inline_initial_state_has_precedence_including_zero(self):
        project = self.parse("C1 a 0 1u IC=0\nC2 a 0 2u IC=7\nC3 a 0 3u\nR1 a 0 1k\n.ic V(a)=3")
        self.assertEqual([item.initial_condition for item in project.elements[:3]], [0.0, 7.0, 3.0])

    def test_hierarchical_nodes_and_inline_precedence(self):
        project = self.parse(".subckt cell p\nC1 p 0 1u IC=0\nC2 internal 0 1u\nR1 internal 0 1k\n.ends\nX1 a cell\nR1 a 0 1k\n.ic V(a)=3 V(x1:internal)=4")
        values = {item.name: item.initial_condition for item in project.elements}
        self.assertEqual(values["X1:C1"], 0.0)
        self.assertEqual(values["X1:C2"], 4.0)

    def test_parameter_dependency_is_reevaluated_per_step(self):
        project = self.parse(".param a=2\n.param b={2*a}\n.step param a list 1 3\nR1 out 0 1k\nC1 out 0 1u\n.ic V(out)={b + 1}")
        self.assertEqual(project.elements[1].initial_condition, 5.0)
        self.assertEqual([variant.elements[1].initial_condition for variant in project.step_variants], [3.0, 7.0])

    def test_analysis_requires_native_uic(self):
        body = "R1 a 0 1k\nC1 a 0 1u\n.ic V(a)=2"
        for analysis in (".op", ".tran 10u 30u"):
            with self.subTest(analysis=analysis), self.assertRaisesRegex(NetlistParseError, "UIC"):
                self.parse(body, analysis)
        with self.assertRaisesRegex(NetlistParseError, "native route"):
            parse_netlist(body + "\n.tran 10u 30u UIC\n")

    def test_unsupported_or_malformed_initial_states_fail_closed(self):
        bodies = (
            "C1 a b 1u\nR1 a 0 1k\nR2 b 0 1k\n.ic V(a)=3",
            "R1 a 0 1k\n.ic V(a)=3",
            "C1 a 0 1u\n.ic V(missing)=3",
            "C1 a 0 1u\n.ic V(a)=3 V(0)=1",
            "C1 a 0 1u\n.ic V(a)=3 V(A)=3",
            "C1 a 0 1u\n.ic V(a)=3\n.ic V(a)=4",
            "C1 a 0 1u\n.ic I(L1)=1m",
            "C1 a 0 1u\n.ic V(a)=nan",
            "C1 a 0 1u\n.ic V(a)=1e309",
            "C1 a 0 1u\n.ic nonsense V(a)=3",
            "C1 a 0 1u\n.ic",
            ".subckt cell a\nC1 a 0 1u\n.ic V(a)=3\n.ends\nX1 out cell",
        )
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(NetlistParseError):
                self.parse(body)

    def test_scalar_temperature_and_unsupported_list_remain_explicit(self):
        for value in (-273.15, 2001, "25 50", "nan"):
            with self.subTest(value=value), self.assertRaises(NetlistParseError):
                self.parse(f"R1 a 0 1k\n.temp {value}", ".op")
        project = self.parse(".param t=125\n.temp {t}\nR1 a 0 1k\nD1 a 0 dm\n.model dm D(IS=1p)", ".op")
        self.assertEqual(project.temperature_c, 125.0)
        self.assertAlmostEqual(project.elements[1].diode_model.temperature_k, 398.15)

    def test_unknown_behavioral_operator_stays_rejected(self):
        with self.assertRaises(NetlistParseError):
            self.parse("V1 in 0 1\nB1 out 0 V={ddt(V(in))}\nR1 out 0 1k", ".op")


@unittest.skipUnless(LIBRARY.is_file(), "Owned native SPIKES C ABI library is not installed")
class NativeDirectiveTests(unittest.TestCase):
    def run_deck(self, deck):
        project = parse_netlist(deck, native_extensions=True)
        result = run_native_project(project, LIBRARY, integration_method="backward_euler")
        self.assertEqual(result.status, "completed", result.issues)
        return result

    def test_actual_native_rc_initial_decay_and_inline_equivalence(self):
        directive = self.run_deck("R1 out 0 1k\nC1 out 0 1u\n.ic V(out)=3\n.tran 10u 30u UIC\n")
        inline = self.run_deck("R1 out 0 1k\nC1 out 0 1u IC=3\n.tran 10u 30u UIC\n")
        self.assertEqual(directive.data, inline.data)
        times = directive.data["time_s"]
        voltages = directive.data["node_voltage_v"]["out"]
        for time, value in zip(times, voltages, strict=True):
            # UIC reports accepted steps, starting at dt, not a fabricated t=0 solve.
            expected = 3.0 / 1.01 ** round(time / 1.0e-5)
            self.assertAlmostEqual(value, expected, delta=1.0e-10)
        self.assertGreater(times[0], 0.0)
        self.assertAlmostEqual(voltages[-1], 3.0 * math.exp(-times[-1] / 1.0e-3), delta=5.0e-4)

    def test_actual_native_dependent_and_behavioral_source_values(self):
        sources = (
            ("E1 out 0 in 0 3", 6.0),
            ("G1 out 0 in 0 1m", -2.0),
            ("F1 out 0 V1 3", 6.0),
            ("H1 out 0 V1 1k", -2.0),
            ("B1 out 0 V={3*V(in)}", 6.0),
            ("B1 out 0 I={1m*V(in)}", -2.0),
            ("B1 out 0 V={V(in)*V(in)+1}", 5.0),
        )
        for source, expected in sources:
            with self.subTest(source=source):
                result = self.run_deck("V1 in 0 2\nR1 in 0 1k\nR2 out 0 1k\n" + source + "\n.op\n")
                self.assertAlmostEqual(result.data["node_voltage_v"]["out"], expected, delta=1.0e-9)

    def test_actual_native_temperature_enters_diode_thermal_voltage(self):
        result = self.run_deck(".temp 125\nI1 0 out 1m\nD1 out 0 dm\n.model dm D(IS=1p N=1)\n.op\n")
        expected = 1.380649e-23 * 398.15 / 1.602176634e-19 * math.log1p(1.0e-3 / 1.0e-12)
        self.assertAlmostEqual(result.data["node_voltage_v"]["out"], expected, delta=1.0e-9)


if __name__ == "__main__":
    unittest.main()
