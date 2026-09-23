import math
import unittest

from python.spike_core.native_mna import run_native_mna
from python.spikes.advanced_analyses import (
    NOISE_RESULT_CONTRACT,
    POLE_ZERO_RESULT_CONTRACT,
    SENSITIVITY_RESULT_CONTRACT,
    run_ac_sensitivity,
    run_linear_noise_analysis,
    run_linear_pole_zero,
)
from python.spikes.analyses import AcExcitation, AcSweep
from python.spikes.contracts import CircuitProject, ProbeDescriptor
from python.spikes.netlist import NetlistParseError, parse_netlist
from python.spikes.runner import native_request


def solve(text: str) -> dict:
    project = parse_netlist(text)
    result = run_native_mna(native_request(project))
    if result["status"] != "completed":
        raise AssertionError(result)
    return result


class ControlledAndBehavioralSourceTests(unittest.TestCase):
    def test_standard_e_g_f_h_sources_execute_in_owned_linear_mna(self):
        e = solve("e\nV1 in 0 1\nE1 out 0 in 0 2\nR1 out 0 1k\n.op\n.end")
        self.assertAlmostEqual(e["data"]["node_voltage_v"]["out"], 2.0)

        g = solve("g\nV1 in 0 1\nG1 out 0 in 0 2m\nR1 out 0 1k\n.op\n.end")
        self.assertAlmostEqual(g["data"]["node_voltage_v"]["out"], -2.0)

        f = solve("f\nV1 in 0 1\nR1 in 0 1k\nF1 out 0 V1 2\nR2 out 0 1k\n.op\n.end")
        self.assertAlmostEqual(f["data"]["node_voltage_v"]["out"], 2.0)

        h = solve("h\nV1 in 0 1\nR1 in 0 1k\nH1 out 0 V1 1k\nR2 out 0 1k\n.op\n.end")
        self.assertAlmostEqual(h["data"]["node_voltage_v"]["out"], -1.0)

    def test_affine_b_sources_lower_to_exact_controlled_or_independent_sources(self):
        result = solve(
            "behavior\nV1 in 0 1\nBGAIN out 0 V={3*V(in,0)}\n"
            "R1 out 0 1k\nBCONST bias 0 I={2m}\nR2 bias 0 1k\n.op\n.end"
        )
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 3.0)
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["bias"], -2.0)
        project = parse_netlist("x\nV1 in 0 1\nB1 out 0 V={2*V(in)}\nR1 out 0 1k\n.op\n.end")
        restored = CircuitProject.from_dict(project.to_dict())
        self.assertEqual(restored.elements[1].behavioral_expression, "V={2.0*V(in)}")

    def test_b_source_fails_closed_on_code_and_unsafe_syntax(self):
        invalid = (
            "V={__import__('os').system('echo bad')}",
            "V={(lambda x: x)(V(in))}",
            "V={V(in)[0]}",
        )
        for expression in invalid:
            with self.subTest(expression=expression), self.assertRaises(NetlistParseError):
                parse_netlist(
                    f"x\nV1 in 0 1\nV2 other 0 2\nB1 out 0 {expression}\nR1 out 0 1k\n.op\n.end"
                )

    def test_current_control_reference_is_checked_after_hierarchy_elaboration(self):
        with self.assertRaisesRegex(ValueError, "unknown voltage-defined branch"):
            parse_netlist("x\nF1 out 0 Vmissing 2\nR1 out 0 1k\n.op\n.end")


class LinearAdvancedAnalysisTests(unittest.TestCase):
    def test_resistor_noise_matches_johnson_nyquist_density(self):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist("noise\nR1 out 0 1k\n.op\n.end", probes=(probe,))
        result = run_linear_noise_analysis(
            project, AcSweep(10.0, 10.0, 1, "linear"), probe, temperature_k=300.15
        )
        expected = math.sqrt(4.0 * 1.380649e-23 * 300.15 * 1000.0)
        self.assertEqual(result["contract"], NOISE_RESULT_CONTRACT)
        self.assertAlmostEqual(result["data"]["output_noise_density_v_sqrt_hz"][0], expected, delta=expected * 1e-12)
        self.assertIn("semiconductor shot and flicker noise", result["provenance"]["omissions"])

    def test_rc_sensitivity_matches_analytic_log_derivative(self):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist(
            "rc\nV1 in 0 1\nR1 in out 1k\nC1 out 0 1u\n.op\n.end", probes=(probe,)
        )
        corner = 1.0 / (2.0 * math.pi * 1000.0 * 1e-6)
        result = run_ac_sensitivity(
            project, AcSweep(corner, corner, 1, "linear"), AcExcitation("V1"), probe, ("R1",)
        )
        sensitivity = result["data"]["elements"]["R1"]["normalized_log_sensitivity"]
        self.assertEqual(result["contract"], SENSITIVITY_RESULT_CONTRACT)
        self.assertAlmostEqual(sensitivity["real"][0], -0.5, places=7)
        self.assertAlmostEqual(sensitivity["imaginary"][0], -0.5, places=7)

    def test_rc_descriptor_pole_is_exact_and_has_no_finite_zero(self):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist(
            "rc\nV1 in 0 1\nR1 in out 1k\nC1 out 0 1u\n.op\n.end", probes=(probe,)
        )
        result = run_linear_pole_zero(project, AcExcitation("V1"), probe)
        self.assertEqual(result["contract"], POLE_ZERO_RESULT_CONTRACT)
        self.assertEqual(result["data"]["pole_count"], 1)
        self.assertEqual(result["data"]["zero_count"], 0)
        self.assertAlmostEqual(result["data"]["poles_rad_s"]["real"][0], -1000.0, places=9)
        self.assertEqual(result["model_status"], "experimental_linear_descriptor")


if __name__ == "__main__":
    unittest.main()
