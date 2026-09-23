import contextlib
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from python.spikes.cli import EXIT_INPUT, EXIT_OK, main
from python.spikes.contracts import CircuitProject, ProbeDescriptor
from python.spikes.netlist import MAX_TRANSIENT_POINTS, NetlistParseError, parse_netlist
from python.spikes.runner import compile_project, run_project


RC = """RC transient reference
V1 in 0 1
R1 in out 1k
C1 out 0 1u
.tran 100u 1m
.end
"""

RL = """RL transient reference
V1 in 0 1
R1 in out 10
L1 out 0 1m
.tran 10u 100u
.end
"""


class TransientContractAndParserTests(unittest.TestCase):
    def test_rlc_and_tran_contract_round_trip(self):
        project = parse_netlist(RC, probes=(ProbeDescriptor.parse("V(out)"),))
        self.assertEqual([element.kind for element in project.elements], [
            "voltage_source", "resistor", "capacitor"
        ])
        self.assertAlmostEqual(project.elements[2].value, 1e-6)
        self.assertEqual(project.analysis.mode, "transient")
        self.assertAlmostEqual(project.analysis.time_step_s, 100e-6)
        self.assertAlmostEqual(project.analysis.stop_time_s, 1e-3)
        restored = CircuitProject.from_dict(json.loads(json.dumps(project.to_dict())))
        self.assertEqual(restored, project)

    def test_units_hierarchy_and_native_translation(self):
        source = """hierarchical LC
.subckt energy p n
Cstore p n 2uF
Lstore p n 3mH
.ends energy
V1 in 0 1V
Xtank in 0 energy
.tran 1us 10us
"""
        project = parse_netlist(source)
        self.assertEqual([element.name for element in project.elements], ["V1", "XTANK:CSTORE", "XTANK:LSTORE"])
        compiled = compile_project(project)
        self.assertEqual(compiled["status"], "ready")
        request = compiled["native_request_template"]
        self.assertEqual(request["analysis"]["mode"], "transient")
        self.assertAlmostEqual(request["analysis"]["time_step_s"], 1e-6)
        self.assertAlmostEqual(request["analysis"]["stop_time_s"], 10e-6)
        self.assertAlmostEqual(request["elements"][1]["capacitance_f"], 2e-6)
        self.assertAlmostEqual(request["elements"][2]["inductance_h"], 3e-3)
        self.assertFalse(any("C++ transient" in item and "not" not in item for item in compiled["limitations"]))

    def test_tran_is_strict_positive_and_bounded(self):
        invalid = (
            "V1 a 0 1\nR1 a 0 1k\n.tran 0 1m\n",
            "V1 a 0 1\nR1 a 0 1k\n.tran -1u 1m\n",
            "V1 a 0 1\nR1 a 0 1k\n.tran 2m 1m\n",
            "V1 a 0 1\nR1 a 0 1k\n.tran 1u 1m 0\n",
            f"V1 a 0 1\nR1 a 0 1k\n.tran 1p {MAX_TRANSIENT_POINTS + 1}p\n",
        )
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_source_waveforms_remain_fail_closed(self):
        for source_form in (
            "PULSE(0 1 0 1n 1n 1u 2u)",
            "SIN(0 1 1k)",
            "PWL(0 0 1m 1)",
        ):
            source = f"V1 in 0 {source_form}\nR1 in 0 1k\n.tran 1u 10u\n"
            with self.subTest(source_form=source_form), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_ac_qualified_source_keeps_its_transient_dc_value(self):
        project = parse_netlist("V1 in 0 DC 1 AC 2 90\nR1 in 0 1k\n.tran 1u 10u\n")
        source = project.elements[0]
        self.assertEqual(source.value, 1.0)
        self.assertEqual(source.ac_magnitude, 2.0)
        self.assertEqual(source.ac_phase_deg, 90.0)


class TransientRunnerTests(unittest.TestCase):
    def test_rc_backward_euler_response_and_series_probes(self):
        probes = (
            ProbeDescriptor.parse("V(out)"), ProbeDescriptor.parse("I(C1)"),
            ProbeDescriptor.parse("P(C1)"),
        )
        result = run_project(parse_netlist(RC, probes=probes)).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["analysis"]["mode"], "transient")
        self.assertEqual(result["data"]["integration"], "backward_euler")
        self.assertEqual(len(result["data"]["time_s"]), 11)
        output = result["data"]["node_voltage_v"]["out"]
        self.assertAlmostEqual(output[0], 1.0 / 11.0)
        self.assertGreater(output[-1], output[0])
        self.assertLess(output[-1], 1.0)
        self.assertEqual(result["probes"]["V(out)"]["values"], output)
        self.assertEqual(len(result["probes"]["I(C1)"]["values"]), 11)
        self.assertFalse(result["provenance"]["transient_engine"]["owned_cpp_transient"])

    def test_rl_backward_euler_response(self):
        result = run_project(parse_netlist(RL, probes=(ProbeDescriptor.parse("I(L1)"),))).to_dict()
        current = result["data"]["element_current_a"]["L1"]
        self.assertEqual(len(current), 11)
        self.assertGreater(current[0], 0.0)
        self.assertGreater(current[-1], current[0])
        self.assertLess(current[-1], 0.1)
        self.assertEqual(result["probes"]["I(L1)"]["values"], current)


class TransientCliTests(unittest.TestCase):
    def test_cli_runs_rc_and_reports_invalid_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / "rc.cir"
            bad = root / "bad.cir"
            good.write_text(RC, encoding="utf-8")
            bad.write_text("V1 a 0 1\nC1 a 0 1u\n.tran 1u 10u 0\n", encoding="utf-8")
            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main(("run", str(good), "--probe", "V(out)"))
            payload = json.loads(output.getvalue())
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(payload["diagnostics"]["points"], 11)
            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main(("run", str(bad)))
            payload = json.loads(output.getvalue())
            self.assertEqual(code, EXIT_INPUT)
            self.assertEqual(payload["issues"][0]["code"], "SPIKES_NETLIST_TRAN_ARITY")


if __name__ == "__main__":
    unittest.main()
