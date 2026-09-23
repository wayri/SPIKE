import math
import unittest

from python.spikes import (
    ADJOINT_SENSITIVITY_CONTRACT,
    BIASED_NOISE_CONTRACT,
    FREQUENCY_VOLTERRA_CONTRACT,
    MULTITONE_VOLTERRA_CONTRACT,
    LOCAL_DISTORTION_CONTRACT,
    NONLINEAR_OP_CONTRACT,
    NONLINEAR_SMALL_SIGNAL_CONTRACT,
    NoiseCorrelation,
    VolterraTone,
    AcExcitation,
    CircuitProject,
    ProbeDescriptor,
    compile_behavioral_expression,
    parse_netlist,
    run_biased_noise,
    run_frequency_dependent_volterra,
    run_multitone_volterra,
    run_local_distortion,
    run_nonlinear_adjoint_sensitivity,
    run_nonlinear_operating_point,
    run_nonlinear_small_signal,
)


class DifferentiableBehavioralExpressionTests(unittest.TestCase):
    def test_safe_expression_value_and_gradient_match_analytic_result(self):
        compiled = compile_behavioral_expression("exp(V(a)) + sin(V(b,0)) + tanh(I(Vsense))")
        evaluated = compiled.evaluate((0.2, -0.3, 0.4))
        self.assertAlmostEqual(evaluated.value, math.exp(0.2) + math.sin(-0.3) + math.tanh(0.4), places=14)
        self.assertAlmostEqual(evaluated.gradient[0], math.exp(0.2), places=14)
        self.assertAlmostEqual(evaluated.gradient[1], math.cos(-0.3), places=14)
        self.assertAlmostEqual(evaluated.gradient[2], 1.0 - math.tanh(0.4) ** 2, places=14)

    def test_parser_preserves_safe_nonlinear_multi_control_source(self):
        project = parse_netlist(
            "nonlinear\nV1 a 0 2\nV2 b 0 1\nB1 out 0 V={V(a)**2+V(b)}\nR1 out 0 1k\n.op\n.end"
        )
        self.assertEqual(project.elements[2].kind, "behavioral_voltage_source")
        restored = CircuitProject.from_dict(project.to_dict())
        self.assertEqual(restored.elements[2].kind, "behavioral_voltage_source")
        result = run_nonlinear_operating_point(restored)
        self.assertEqual(result["contract"], NONLINEAR_OP_CONTRACT)
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 5.0, places=12)

    def test_compiler_rejects_bare_functions_and_nonnumeric_constants(self):
        for expression in ("exp", "'not numeric'", "V(a).__class__", "V(a) if V(a) else 0"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                compile_behavioral_expression(expression)

    def test_nonlinear_expression_is_scoped_through_subcircuit_hierarchy(self):
        project = parse_netlist(
            "scope\n.subckt sq input output\nB1 output 0 V={V(input)**2}\nR1 output 0 1k\n.ends\n"
            "V1 in 0 3\nX1 in out sq\n.op\n.end"
        )
        behavioral = next(element for element in project.elements if element.kind == "behavioral_voltage_source")
        self.assertIn("V(in)", behavioral.behavioral_expression)
        result = run_nonlinear_operating_point(project)
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 9.0, places=12)

    def test_nonlinear_behavioral_current_source_stamps_value_and_jacobian(self):
        project = parse_netlist(
            "current-b\nV1 in 0 1\nB1 out 0 I={V(out)+0.1*V(out)**3-V(in)}\n.op\n.end"
        )
        result = run_nonlinear_operating_point(project)
        output = result["data"]["node_voltage_v"]["out"]
        self.assertAlmostEqual(output + 0.1 * output ** 3, 1.0, places=11)
        self.assertLessEqual(result["diagnostics"]["residual_inf"], 1e-11)


class NonlinearAnalysisTests(unittest.TestCase):
    def polynomial_project(self, bias: float = 0.0):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist(
            f"poly\nV1 in 0 {bias}\n"
            "B1 out 0 V={V(in)+0.1*V(in)**2+0.01*V(in)**3}\n"
            "R1 out 0 1k\n.op\n.end",
            probes=(probe,),
        )
        return project, probe

    def test_bias_linearized_small_signal_uses_exact_behavioral_jacobian(self):
        project, probe = self.polynomial_project(2.0)
        result = run_nonlinear_small_signal(project, AcExcitation("V1", phase_deg=30.0), probe)
        expected_gain = 1.0 + 0.2 * 2.0 + 0.03 * 4.0
        self.assertEqual(result["contract"], NONLINEAR_SMALL_SIGNAL_CONTRACT)
        self.assertAlmostEqual(result["data"]["output"]["magnitude"], expected_gain, places=12)
        self.assertAlmostEqual(result["data"]["output"]["phase_deg"], 30.0, places=12)

    def test_local_distortion_recovers_polynomial_derivatives_and_harmonics(self):
        project, probe = self.polynomial_project()
        result = run_local_distortion(project, "V1", probe, amplitude=0.1, derivative_step=0.01)
        derivatives = result["data"]["derivatives"]
        harmonics = result["data"]["harmonic_amplitudes"]
        self.assertEqual(result["contract"], LOCAL_DISTORTION_CONTRACT)
        self.assertAlmostEqual(derivatives["first"], 1.000001, places=10)
        self.assertAlmostEqual(derivatives["second"], 0.2, places=10)
        self.assertAlmostEqual(derivatives["third"], 0.06, places=9)
        self.assertAlmostEqual(harmonics["second"], 0.0005, places=12)
        self.assertAlmostEqual(harmonics["third"], 0.0000025, places=12)

    def test_frequency_volterra_preserves_rlc_harmonic_loading(self):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist(
            "dynamic-volterra\nI1 out 0 0\nR1 out 0 1\nC1 out 0 1\n"
            "B1 out 0 I={0.1*V(out)**2+0.01*V(out)**3}\n.op\n.end",
            probes=(probe,),
        )
        low = run_frequency_dependent_volterra(
            project, AcExcitation("I1"), probe,
            fundamental_frequency_hz=0.01, amplitude=0.1,
        )
        high = run_frequency_dependent_volterra(
            project, AcExcitation("I1"), probe,
            fundamental_frequency_hz=1.0, amplitude=0.1,
        )
        self.assertEqual(low["contract"], FREQUENCY_VOLTERRA_CONTRACT)
        self.assertGreater(low["data"]["volterra_kernel"]["h2"]["magnitude"], 0.0)
        self.assertGreater(
            low["data"]["volterra_kernel"]["h2"]["magnitude"],
            100.0 * high["data"]["volterra_kernel"]["h2"]["magnitude"],
        )

    def test_multitone_volterra_resolves_sum_difference_and_im3_products(self):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist(
            "multitone\nV1 a 0 0\nV2 b 0 0\n"
            "B1 out 0 V={V(a)+V(b)+0.1*(V(a)+V(b))**2+0.01*(V(a)+V(b))**3}\n"
            "R1 out 0 1k\n.op\n.end",
            probes=(probe,),
        )
        result = run_multitone_volterra(
            project,
            (
                VolterraTone("V1", 1000.0, 0.2),
                VolterraTone("V2", 1300.0, 0.3),
            ),
            probe,
            derivative_step=1.0e-3,
        )
        self.assertEqual(result["contract"], MULTITONE_VOLTERRA_CONTRACT)
        products = {
            (item["order"], round(item["frequency_hz"])):
                item["real_signal_peak_phasor"]["magnitude"]
            for item in result["data"]["products"]
        }
        self.assertAlmostEqual(products[(2, 300)], 0.1 * 0.2 * 0.3, places=8)
        self.assertAlmostEqual(products[(2, 2300)], 0.1 * 0.2 * 0.3, places=8)
        self.assertAlmostEqual(
            products[(3, 700)], 0.01 * 3.0 * 0.2 * 0.2 * 0.3 / 4.0,
            places=8,
        )
        self.assertAlmostEqual(
            products[(3, 1600)], 0.01 * 3.0 * 0.3 * 0.3 * 0.2 / 4.0,
            places=8,
        )

    def test_multitone_volterra_is_resource_bounded_and_validates_sources(self):
        project, probe = self.polynomial_project()
        with self.assertRaisesRegex(ValueError, "1 to 4"):
            run_multitone_volterra(project, (), probe)
        with self.assertRaisesRegex(ValueError, "unknown source"):
            run_multitone_volterra(
                project, (VolterraTone("VMISSING", 1.0, 1.0),), probe
            )

    def test_nonlinear_adjoint_matches_resistor_divider_derivative(self):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist(
            "divider\nV1 in 0 10\nR1 in out 1k\nR2 out 0 1k\n.op\n.end", probes=(probe,)
        )
        result = run_nonlinear_adjoint_sensitivity(project, probe, ("R1", "R2"))
        self.assertEqual(result["contract"], ADJOINT_SENSITIVITY_CONTRACT)
        self.assertAlmostEqual(result["data"]["elements"]["R1"]["derivative"], -0.0025, places=12)
        self.assertAlmostEqual(result["data"]["elements"]["R2"]["derivative"], 0.0025, places=12)
        self.assertAlmostEqual(result["data"]["elements"]["R1"]["normalized"], -0.5, places=12)

    def test_biased_diode_noise_matches_shot_noise_through_small_signal_impedance(self):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist(
            "diode\nV1 in 0 1\nR1 in out 1k\nD1 out 0 DM\n"
            ".model DM D(IS=1e-12 N=1 TNOM=27)\n.op\n.end",
            probes=(probe,),
        )
        op = run_nonlinear_operating_point(project)
        result = run_biased_noise(project, probe, temperature_k=300.15)
        current = op["data"]["diode_current_a"]["D1"]
        voltage = op["data"]["node_voltage_v"]["out"]
        model = next(element for element in project.elements if element.name == "D1").diode_model
        assert model is not None
        vt = 1.380649e-23 * model.temperature_k / 1.602176634e-19
        gd = (current + model.saturation_current_a) / (model.emission_coefficient * vt)
        impedance = 1.0 / (1.0 / 1000.0 + gd)
        expected_diode_psd = 2.0 * 1.602176634e-19 * abs(current) * impedance * impedance
        self.assertGreater(voltage, 0.0)
        self.assertEqual(result["contract"], BIASED_NOISE_CONTRACT)
        self.assertAlmostEqual(result["data"]["contributions"]["D1"], expected_diode_psd, delta=expected_diode_psd * 1e-10)

    def test_correlated_noise_uses_psd_covariance_and_rejects_indefinite_matrix(self):
        probe = ProbeDescriptor.parse("V(out)")
        project = parse_netlist(
            "correlated\nR1 out 0 1k\nR2 out 0 1k\n.op\n.end",
            probes=(probe,),
        )
        uncorrelated = run_biased_noise(project, probe)
        correlated = run_biased_noise(
            project, probe,
            correlations=(NoiseCorrelation("R1", "R2", 1.0),),
        )
        cancelled = run_biased_noise(
            project, probe,
            correlations=(NoiseCorrelation("R1", "R2", -1.0),),
        )
        self.assertAlmostEqual(
            correlated["data"]["output_noise_psd"],
            2.0 * uncorrelated["data"]["output_noise_psd"], places=24,
        )
        self.assertAlmostEqual(cancelled["data"]["output_noise_psd"], 0.0, places=30)
        self.assertEqual(len(correlated["data"]["correlations"]), 1)

        three = parse_netlist(
            "invalid-covariance\nR1 out 0 1k\nR2 out 0 1k\nR3 out 0 1k\n.op\n.end",
            probes=(probe,),
        )
        with self.assertRaisesRegex(ValueError, "positive semidefinite"):
            run_biased_noise(
                three, probe,
                correlations=(
                    NoiseCorrelation("R1", "R2", 1.0),
                    NoiseCorrelation("R1", "R3", 1.0),
                    NoiseCorrelation("R2", "R3", -1.0),
                ),
            )


if __name__ == "__main__":
    unittest.main()
