import math
import unittest

from python.spikes.contracts import CircuitProject, ProbeDescriptor
from python.spikes.netlist import NetlistParseError, parse_netlist
from python.spikes.runner import run_project


class AcDeckGrammarTests(unittest.TestCase):
    def test_spice_ac_source_and_decade_directive_execute_through_owned_cli(self):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist(
            "ac-lowpass\n"
            "V1 in 0 DC 0 AC 2 30\n"
            "R1 in out 1k\n"
            "C1 out 0 1u\n"
            ".ac DEC 10 10 10k\n"
            ".end\n",
            probes=(probe,),
        )
        self.assertEqual(project.analysis.mode, "ac")
        self.assertEqual(project.analysis.source, "V1")
        self.assertEqual(project.analysis.frequency_scale, "dec")
        self.assertEqual(project.analysis.frequency_points, 31)
        source = project.elements[0]
        self.assertEqual(source.value, 0.0)
        self.assertEqual(source.ac_magnitude, 2.0)
        self.assertEqual(source.ac_phase_deg, 30.0)
        self.assertEqual(CircuitProject.from_dict(project.to_dict()), project)

        result = run_project(project).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["data"]["frequency_hz"]), 31)
        first = result["probes"]["V(out)"]["values"]
        expected = 2.0 / math.sqrt(1.0 + (2.0 * math.pi * 10.0 * 1000.0e-6) ** 2)
        self.assertAlmostEqual(first["magnitude"][0], expected, places=12)

    def test_lin_and_oct_counts_follow_spice_point_density_semantics(self):
        linear = parse_netlist(
            "V1 a 0 AC 1\nR1 a 0 1k\n.ac LIN 7 1 10\n.end\n"
        )
        octave = parse_netlist(
            "V1 a 0 0 AC 1\nR1 a 0 1k\n.ac OCT 4 1 8\n.end\n"
        )
        self.assertEqual(linear.analysis.frequency_points, 7)
        self.assertEqual(octave.analysis.frequency_points, 13)

    def test_ac_route_rejects_missing_multiple_and_malformed_excitations(self):
        decks = (
            "V1 a 0 0\nR1 a 0 1k\n.ac DEC 10 1 1k\n",
            "V1 a 0 AC 1\nI1 0 a AC 1\nR1 a 0 1k\n.ac DEC 10 1 1k\n",
            "V1 a 0 AC -1\nR1 a 0 1k\n.ac DEC 10 1 1k\n",
            "V1 a 0 AC 1\nR1 a 0 1k\n.ac BAN 10 1 1k\n",
        )
        for deck in decks:
            with self.subTest(deck=deck), self.assertRaises(NetlistParseError):
                parse_netlist(deck)


class UserFunctionGrammarTests(unittest.TestCase):
    def test_func_expands_parameter_and_nonlinear_behavioral_expressions(self):
        project = parse_netlist(
            ".func scale(x,y) {x*y}\n"
            ".func curve(x) {scale(x,x)+1}\n"
            ".param load=scale(1k,2)\n"
            "V1 in 0 3\n"
            "B1 out 0 V={curve(V(in))}\n"
            "R1 out 0 {load}\n"
            ".op\n.end\n"
        )
        self.assertEqual(project.elements[2].value, 2000.0)
        self.assertIn("V(in)", project.elements[1].behavioral_expression)
        from python.spikes.nonlinear_analyses import run_nonlinear_operating_point

        result = run_nonlinear_operating_point(project)
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 10.0, places=12)

    def test_func_rejects_bad_arity_and_direct_or_mutual_recursion(self):
        decks = (
            ".func f(x) {x+1}\n.param a=f(1,2)\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".func f(x) {f(x)}\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".func f(x) {g(x)}\n.func g(x) {f(x)}\nV1 a 0 1\nR1 a 0 1k\n.op\n",
        )
        for deck in decks:
            with self.subTest(deck=deck), self.assertRaises(NetlistParseError):
                parse_netlist(deck)


class TemperatureAndInitialConditionGrammarTests(unittest.TestCase):
    def test_temp_updates_device_temperature_and_roundtrips(self):
        project = parse_netlist(
            "thermal diode\n.temp 125\nV1 in 0 1\nD1 in 0 DM\n"
            ".model DM D(IS=1e-12 N=1 TNOM=27)\n.op\n.end\n"
        )
        self.assertEqual(project.temperature_c, 125.0)
        diode = next(element for element in project.elements if element.name == "D1")
        self.assertAlmostEqual(diode.diode_model.temperature_k, 398.15, places=12)
        self.assertEqual(CircuitProject.from_dict(project.to_dict()), project)

    def test_capacitor_and_inductor_inline_ic_are_preserved(self):
        project = parse_netlist(
            "initial state\nR1 a 0 1k\nC1 a 0 1u IC=3\n"
            "L1 b 0 1m IC=-2m\nR2 b 0 1\n.tran 1u 10u UIC\n.end\n"
        )
        values = {element.name: element.initial_condition for element in project.elements}
        self.assertEqual(values["C1"], 3.0)
        self.assertEqual(values["L1"], -2.0e-3)
        self.assertTrue(project.analysis.use_initial_conditions)
        self.assertEqual(CircuitProject.from_dict(project.to_dict()), project)

    def test_temp_and_ic_malformed_forms_fail_closed(self):
        decks = (
            "R1 a 0 1k\n.temp 25 50\n.op\n",
            "R1 a 0 1k IC=1\n.op\n",
            "R1 a 0 1k\nC1 a 0 1u BAD=1\n.tran 1u 2u\n",
        )
        for deck in decks:
            with self.subTest(deck=deck), self.assertRaises(NetlistParseError):
                parse_netlist(deck)


if __name__ == "__main__":
    unittest.main()
