import contextlib
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from python.spikes.cli import EXIT_INPUT, EXIT_OK, main
from python.spikes.contracts import CircuitProject, ProbeDescriptor
from python.spikes.netlist import NetlistParseError, parse_netlist, parse_spice_number
from python.spikes.runner import compile_project, run_project


DIVIDER_OP = """Voltage divider
V1 in 0 DC 10V
R1 in out 1kOhm
R2 out 0 1K
.op
.end
"""


class SpikesNumberTests(unittest.TestCase):
    def test_spice_suffixes_are_case_insensitive_but_m_means_milli(self):
        self.assertEqual(parse_spice_number("1K", "resistor"), 1000.0)
        self.assertEqual(parse_spice_number("2megohm", "resistor"), 2e6)
        self.assertAlmostEqual(parse_spice_number("3mA", "current_source"), 0.003)
        self.assertEqual(parse_spice_number("5V", "voltage_source"), 5.0)

    def test_unknown_units_and_nonfinite_values_are_rejected(self):
        for value, quantity in (("1banana", "resistor"), ("nan", "voltage_source"), ("1e999", "current_source")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_spice_number(value, quantity)


class SpikesNetlistTests(unittest.TestCase):
    def test_parses_supported_subset_and_normalizes_names(self):
        project = parse_netlist(DIVIDER_OP, source_name="divider.cir")
        self.assertEqual(project.title, "Voltage divider")
        self.assertEqual([item.name for item in project.elements], ["V1", "R1", "R2"])
        self.assertEqual(project.elements[1].value, 1000.0)
        self.assertEqual(project.analysis.mode, "operating_point")
        self.assertEqual(len(project.source_sha256), 64)

    def test_explicit_title_and_inline_comments_are_supported(self):
        project = parse_netlist("""* full line comment
.title injection test
I1 0 OUT 1mA ; inject current
R1 out 0 1k $ load
.op
""")
        self.assertEqual(project.title, "injection test")
        self.assertEqual(project.elements[0].positive_node, "0")
        self.assertEqual(project.elements[0].negative_node, "out")

    def test_project_and_probe_contracts_round_trip_through_json(self):
        probes = (ProbeDescriptor.parse("V(out)"), ProbeDescriptor.parse("I(r1)"))
        project = parse_netlist(DIVIDER_OP, probes=probes)
        payload = json.loads(json.dumps(project.to_dict()))
        restored = CircuitProject.from_dict(payload)
        self.assertEqual(restored, project)

    def test_rejects_unsupported_or_ambiguous_syntax(self):
        cases = {
            "named_diode": "Dfast out 0 generic\nR1 out 0 1k\n.op\n",
            "directive": "R1 out 0 1k\n.ac dec 10 1 1k\n",
            "waveform": "V1 out 0 PULSE(0 1 1n)\nR1 out 0 1k\n.op\n",
            "continuation": "R1 out 0 1k\n+ tc=0.1\n.op\n",
            "after_end": "R1 out 0 1k\n.op\n.end\nR2 out 0 1k\n",
        }
        for label, source in cases.items():
            with self.subTest(label=label), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_requires_explicit_ground_unique_elements_and_one_analysis(self):
        cases = (
            "R1 a b 1k\n.op\n",
            "R1 out 0 1k\nr1 out 0 2k\n.op\n",
            "R1 out 0 1k\n",
            "R1 out 0 1k\n.op\n.dc V1 0 1 1\n",
        )
        for source in cases:
            with self.subTest(source=source), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_validates_dc_source_direction_and_point_limit(self):
        invalid = (
            "V1 out 0 0\nR1 out 0 1k\n.dc V1 0 1 0\n",
            "V1 out 0 0\nR1 out 0 1k\n.dc V1 0 1 -0.1\n",
            "V1 out 0 0\nR1 out 0 1k\n.dc V2 0 1 0.1\n",
            "V1 out 0 0\nR1 out 0 1k\n.dc V1 0A 1A 0.1A\n",
            "V1 out 0 0\nR1 out 0 1k\n.dc V1 0 2 1u\n",
        )
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(NetlistParseError):
                parse_netlist(source)


class SpikesRunnerTests(unittest.TestCase):
    def test_compile_translates_to_existing_native_mna_contract(self):
        compiled = compile_project(parse_netlist(DIVIDER_OP))
        self.assertEqual(compiled["contract"], "spikes/compiled-netlist/v1")
        self.assertEqual(compiled["status"], "ready")
        self.assertEqual(compiled["native_request_template"]["contract"], "spike/native-mna-request/v1")
        self.assertEqual(compiled["native_request_template"]["elements"][1]["resistance_ohm"], 1000.0)

    def test_operating_point_returns_voltage_current_power_and_probes(self):
        probes = (
            ProbeDescriptor.parse("V(out)"),
            ProbeDescriptor.parse("V(in,out)"),
            ProbeDescriptor.parse("I(R1)"),
            ProbeDescriptor.parse("P(R2)"),
        )
        result = run_project(parse_netlist(DIVIDER_OP, probes=probes)).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_status"], "experimental")
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 5.0)
        self.assertAlmostEqual(result["data"]["element_current_a"]["R1"], 0.005)
        self.assertAlmostEqual(result["data"]["element_power_w"]["R2"], 0.025)
        self.assertAlmostEqual(result["probes"]["V(out)"]["value"], 5.0)
        self.assertAlmostEqual(result["probes"]["V(in,out)"]["value"], 5.0)

    def test_current_source_sign_follows_positive_to_negative_convention(self):
        result = run_project(parse_netlist("I1 0 out 1m\nR1 out 0 1k\n.op\n")).to_dict()
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 1.0)
        self.assertAlmostEqual(result["data"]["element_current_a"]["I1"], 0.001)

    def test_dc_sweep_aggregates_independent_operating_points(self):
        source = """V1 in 0 0
R1 in out 1k
R2 out 0 1k
.dc V1 0 4 2
"""
        probes = (ProbeDescriptor.parse("V(out)"), ProbeDescriptor.parse("I(R1)"))
        result = run_project(parse_netlist(source, probes=probes)).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["data"]["sweep"]["values"], [0.0, 2.0, 4.0])
        self.assertEqual(result["data"]["node_voltage_v"]["out"], [0.0, 1.0, 2.0])
        self.assertEqual(result["probes"]["V(out)"]["values"], [0.0, 1.0, 2.0])
        self.assertEqual(result["diagnostics"]["points"], 3)

    def test_descending_dc_sweep_is_deterministic(self):
        project = parse_netlist("V1 out 0 0\nR1 out 0 1k\n.dc V1 2 0 -1\n")
        result = run_project(project).to_dict()
        self.assertEqual(result["data"]["sweep"]["values"], [2.0, 1.0, 0.0])
        self.assertEqual(result["data"]["node_voltage_v"]["out"], [2.0, 1.0, 0.0])


class SpikesCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *arguments: str):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def test_check_and_run_emit_json(self):
        path = self.root / "divider.cir"
        path.write_text(DIVIDER_OP, encoding="utf-8")
        code, checked = self.invoke("check", str(path), "--probe", "V(out)")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(checked["status"], "valid")
        code, result = self.invoke("run", str(path), "--probe", "V(out)")
        self.assertEqual(code, EXIT_OK)
        self.assertAlmostEqual(result["probes"]["V(out)"]["value"], 5.0)

    def test_compile_can_write_json_file(self):
        path = self.root / "divider.cir"
        output = self.root / "compiled.json"
        path.write_text(DIVIDER_OP, encoding="utf-8")
        sink = StringIO()
        with contextlib.redirect_stdout(sink):
            code = main(("compile", str(path), "-o", str(output)))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(sink.getvalue(), "")
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "ready")

    def test_parser_failure_is_a_structured_nonzero_exit(self):
        path = self.root / "bad.cir"
        path.write_text("D1 out 0 generic\nR1 out 0 1k\n.op\n", encoding="utf-8")
        code, result = self.invoke("run", str(path))
        self.assertEqual(code, EXIT_INPUT)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["issues"][0]["code"], "SPIKES_NETLIST_MODEL_UNKNOWN")
        self.assertEqual(result["issues"][0]["line"], 1)

    def test_output_cannot_overwrite_input_netlist(self):
        path = self.root / "divider.cir"
        path.write_text(DIVIDER_OP, encoding="utf-8")
        code, result = self.invoke("run", str(path), "-o", str(path))
        self.assertEqual(code, EXIT_INPUT)
        self.assertIn("must not overwrite", result["issues"][0]["message"])
        self.assertEqual(path.read_text(encoding="utf-8"), DIVIDER_OP)


if __name__ == "__main__":
    unittest.main()
