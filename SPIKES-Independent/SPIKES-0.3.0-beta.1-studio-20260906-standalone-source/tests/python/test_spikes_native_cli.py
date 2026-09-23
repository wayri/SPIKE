import contextlib
import json
import math
import os
from io import StringIO
from pathlib import Path
import unittest

from python.spikes.cli import EXIT_OK, main
from python.spikes.contracts import CircuitProject
from python.spikes.contracts import ProbeDescriptor
from python.spikes.netlist import NetlistParseError, parse_netlist
from python.spikes.native_runner import run_native_project


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get(
    "SPIKES_TEST_NATIVE_LIBRARY",
    ROOT / "build-peec-native" / "spikes_c_api.dll",
))
EXAMPLE = ROOT / "examples" / "spikes" / "native_pwm_switch.cir"


class NativeExtensionParserTests(unittest.TestCase):
    def test_standard_diode_model_resolves_forward_and_round_trips(self):
        source = """diode model compatibility
I1 0 out 1m
D1 out 0 fast
.model fast D(IS = 2p, N=1.5 TNOM=27)
.op
"""
        project = parse_netlist(source)
        diode = next(item for item in project.elements if item.kind == "diode")
        self.assertEqual(diode.model_name, "FAST")
        self.assertEqual(diode.diode_model.saturation_current_a, 2.0e-12)
        self.assertEqual(diode.diode_model.emission_coefficient, 1.5)
        self.assertAlmostEqual(diode.diode_model.temperature_k, 300.15)
        restored = CircuitProject.from_dict(json.loads(json.dumps(project.to_dict())))
        self.assertEqual(restored, project)

    def test_top_level_model_is_visible_to_hierarchical_diodes(self):
        source = """hierarchical diode
.subckt rectifier p n
Dlocal p n rect
.ends rectifier
I1 0 out 1m
X1 out 0 rectifier
.model rect D(IS=1p N=1.2)
.op
"""
        project = parse_netlist(source)
        diode = next(item for item in project.elements if item.kind == "diode")
        self.assertEqual(diode.name, "X1:DLOCAL")
        self.assertEqual(diode.model_name, "RECT")

    def test_diode_models_fail_closed_outside_the_bounded_slice(self):
        invalid = {
            "unknown_model": "I1 0 out 1m\nD1 out 0 absent\n.op\n",
            "unsupported_parameter": ".model d D(IS=1p BV=20)\nI1 0 out 1m\nD1 out 0 d\n.op\n",
            "duplicate_parameter": ".model d D(IS=1p IS=2p)\nI1 0 out 1m\nD1 out 0 d\n.op\n",
            "invalid_temperature": ".model d D(TNOM=-300)\nI1 0 out 1m\nD1 out 0 d\n.op\n",
            "unsupported_model_type": ".model q NPN(IS=1p)\nI1 0 out 1m\nD1 out 0 q\n.op\n",
            "instance_parameter": ".model d D(IS=1p)\nI1 0 out 1m\nD1 out 0 d AREA=2\n.op\n",
            "scoped_model": ".subckt x p n\n.model d D(IS=1p)\nD1 p n d\n.ends\nI1 0 out 1m\nX1 out 0 x\n.op\n",
        }
        for label, source in invalid.items():
            with self.subTest(label=label), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_native_waveforms_switch_and_hierarchy_round_trip(self):
        source = """native hierarchy
.subckt stage supply output gate
S1 supply output gate 0 1 1meg 2.5 100m
R1 output 0 10
.ends stage
Vs in 0 10
Vg gate 0 PULSE(0 5 100u 100u 100u 200u 500u)
Xpower in out gate stage
.tran 300u 500u
"""
        project = parse_netlist(source, native_extensions=True)
        switch = next(item for item in project.elements if item.kind == "voltage_controlled_switch")
        self.assertEqual(switch.control_positive_node, "gate")
        self.assertEqual(switch.control_negative_node, "0")
        self.assertAlmostEqual(switch.switch_model.transition_voltage_v, 0.1)
        gate = next(item for item in project.elements if item.name == "VG")
        self.assertEqual(gate.waveform.kind, "pulse")
        restored = CircuitProject.from_dict(json.loads(json.dumps(project.to_dict())))
        self.assertEqual(restored, project)

    def test_pwl_is_bounded_and_native_extensions_remain_explicit(self):
        source = "V1 out 0 PWL(0 0, 1u 2, 2u -1)\nR1 out 0 1k\n.tran 1u 2u\n"
        project = parse_netlist(source, native_extensions=True)
        self.assertEqual(project.elements[0].waveform.points, (
            (0.0, 0.0), (1.0e-6, 2.0), (2.0e-6, -1.0)
        ))
        with self.assertRaises(NetlistParseError):
            parse_netlist(source)
        with self.assertRaises(NetlistParseError):
            parse_netlist(
                "V1 out 0 PWL(1u 1 1u 2)\nR1 out 0 1k\n.tran 1u 2u\n",
                native_extensions=True,
            )
        with self.assertRaises(NetlistParseError):
            parse_netlist(
                "V1 out 0 1 unexpected tokens\nR1 out 0 1k\n.op\n",
                native_extensions=True,
            )


@unittest.skipUnless(LIBRARY.is_file(), "built SPIKES C ABI library is unavailable")
class NativeCliExecutionTests(unittest.TestCase):
    def test_owned_native_execution_uses_elaborated_parameters_and_globals(self):
        project = parse_netlist(
            """.param supply=10 base=1k
.global reference
V1 in reference {supply}
Vref reference 0 0
R1 in out {base}
R2 out reference {base}
.op
""",
            probes=(ProbeDescriptor.parse("V(out,reference)"),),
        )
        result = run_native_project(project, LIBRARY).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["probes"]["V(out,reference)"]["value"], 5.0)

    def test_owned_native_diode_operating_point_and_dc_sweep(self):
        model = ".model fast D(IS=1p N=1.5 TNOM=27)"
        operating_point = parse_netlist(
            f"I1 0 out 1m\nD1 out 0 fast\n{model}\n.op\n",
            probes=(ProbeDescriptor.parse("V(out)"), ProbeDescriptor.parse("I(D1)")),
        )
        result = run_native_project(operating_point, LIBRARY).to_dict()
        thermal_voltage = 1.380649e-23 * 300.15 / 1.602176634e-19
        expected = 1.5 * thermal_voltage * math.log1p(1.0e-3 / 1.0e-12)
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["probes"]["V(out)"]["value"], expected, places=10)
        self.assertAlmostEqual(result["probes"]["I(D1)"]["value"], 1.0e-3, delta=2.0e-12)

        sweep = parse_netlist(
            f"I1 0 out 0\nD1 out 0 fast\n{model}\n.dc I1 100u 1m 450u\n",
            probes=(ProbeDescriptor.parse("V(out)"),),
        )
        swept = run_native_project(sweep, LIBRARY).to_dict()
        axis = swept["data"]["sweep"]["values"]
        expected_values = [
            1.5 * thermal_voltage * math.log1p(current / 1.0e-12)
            for current in axis
        ]
        self.assertEqual(swept["status"], "completed")
        self.assertEqual(len(axis), 3)
        for observed, expected_voltage in zip(
            swept["probes"]["V(out)"]["values"], expected_values, strict=True
        ):
            self.assertAlmostEqual(observed, expected_voltage, delta=1.0e-9)

    def test_owned_native_dc_sweep_uses_independent_operating_points(self):
        source = """* owned native dc sweep
V1 in 0 0
R1 in out 1k
R2 out 0 1k
.dc V1 -2 2 1
.end
"""
        project = parse_netlist(
            source, probes=(ProbeDescriptor.parse("V(out)"),),
            native_extensions=True,
        )
        result = run_native_project(project, LIBRARY).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["data"]["sweep"]["values"], [-2.0, -1.0, 0.0, 1.0, 2.0])
        self.assertEqual(result["probes"]["V(out)"]["values"], [-1.0, -0.5, 0.0, 0.5, 1.0])
        self.assertEqual(result["provenance"]["implementation"], "independent_native_operating_points")

    def test_native_cli_runs_pwm_switch_and_reports_owned_provenance(self):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main((
                "native-run", str(EXAMPLE), "--library", str(LIBRARY),
                "--probe", "V(out)", "--probe", "I(Smain)",
            ))
        payload = json.loads(output.getvalue())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["provenance"]["owned_cpp_transient"])
        self.assertEqual(
            payload["provenance"]["integration"], "hybrid_trapezoidal"
        )
        self.assertGreaterEqual(payload["diagnostics"]["source_breakpoint_steps"], 3)
        self.assertGreater(payload["diagnostics"]["backward_euler_steps"], 0)
        self.assertGreater(payload["diagnostics"]["trapezoidal_steps"], 0)
        self.assertGreater(
            payload["diagnostics"]["factorization_reuses"],
            payload["diagnostics"]["matrix_factorizations"],
        )
        times = payload["data"]["time_s"]
        for edge in (0.0, 100e-6, 200e-6, 400e-6, 500e-6):
            self.assertTrue(any(abs(time - edge) < 2.0e-15 for time in times))
        high = next(index for index, time in enumerate(times) if abs(time - 200e-6) < 2.0e-15)
        self.assertAlmostEqual(
            payload["probes"]["V(out)"]["values"][high], 10.0 * 10.0 / 11.0
        )

    def test_native_cli_can_select_backward_euler(self):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main((
                "native-run", str(EXAMPLE), "--library", str(LIBRARY),
                "--method", "be",
            ))
        payload = json.loads(output.getvalue())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["provenance"]["integration"], "backward_euler")
        self.assertEqual(payload["diagnostics"]["trapezoidal_steps"], 0)
        self.assertGreater(payload["diagnostics"]["backward_euler_steps"], 0)

    def test_native_cli_refuses_to_overwrite_the_selected_library(self):
        original_size = LIBRARY.stat().st_size
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main((
                "native-run", str(EXAMPLE), "--library", str(LIBRARY),
                "--output", str(LIBRARY),
            ))
        payload = json.loads(output.getvalue())
        self.assertNotEqual(code, EXIT_OK)
        self.assertIn("must not overwrite", payload["issues"][0]["message"])
        self.assertEqual(LIBRARY.stat().st_size, original_size)


if __name__ == "__main__":
    unittest.main()
