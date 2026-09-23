import unittest

from python.spikes import (
    compile_behavioral_expression,
    parse_nonlinear_analysis_deck,
    run_nonlinear_analysis_deck,
)


class BehavioralGrammarWave6Tests(unittest.TestCase):
    def test_table_interpolates_and_propagates_analytic_gradient(self):
        expression = compile_behavioral_expression(
            "TABLE(V(x), -2, V(y), 0, 1, 4, 9)"
        )
        result = expression.evaluate((2.0, 3.0))
        self.assertEqual(result.value, 5.0)
        self.assertEqual(result.gradient, (2.0, 0.0))

        clamped = expression.evaluate((-3.0, 7.0))
        self.assertEqual(clamped.value, 7.0)
        self.assertEqual(clamped.gradient, (0.0, 1.0))

    def test_spice_discontinuous_helpers_and_modulo_fail_at_boundaries(self):
        expression = compile_behavioral_expression(
            "URAMP(V(x)) + U(V(y)) + SGN(V(z)) + FLOOR(V(w)) + (V(q)%2)"
        )
        result = expression.evaluate((2.5, -1.0, -4.0, 1.25, 3.5))
        self.assertEqual(result.value, 4.0)
        self.assertEqual(result.gradient, (1.0, 0.0, 0.0, 0.0, 1.0))

        boundary_cases = (
            ("U(V(x))", (0.0,)),
            ("FLOOR(V(x))", (2.0,)),
            ("V(x)%2", (4.0,)),
            ("TABLE(V(x),0,0,1,1)", (1.0,)),
        )
        for source, values in boundary_cases:
            with self.subTest(source=source), self.assertRaises(ValueError):
                compile_behavioral_expression(source).evaluate(values)

    def test_table_rejects_dynamic_or_unsorted_breakpoints(self):
        with self.assertRaisesRegex(ValueError, "breakpoints must be constant"):
            compile_behavioral_expression(
                "TABLE(V(x), V(y), 0, 1, 1)"
            ).evaluate((0.5, 0.0))
        with self.assertRaisesRegex(ValueError, "increase strictly"):
            compile_behavioral_expression("TABLE(V(x),1,0,0,1)").evaluate((0.5,))


class SemiconductorNoiseWave6Tests(unittest.TestCase):
    def test_diode_kf_af_produce_frequency_dependent_biased_noise(self):
        deck = parse_nonlinear_analysis_deck(
            "flicker diode\nV1 in 0 1\nR1 in out 1k\nD1 out 0 DM\n"
            ".model DM D(IS=1e-12 N=1 TNOM=27 KF=1e-12 AF=1)\n"
            ".noise V(out) V1 DEC 2 1 100\n.end"
        )
        result = run_nonlinear_analysis_deck(deck)["result"]["data"]
        spectrum = result["output_noise_psd_v2_hz"]
        self.assertEqual(len(spectrum), 5)
        self.assertGreater(spectrum[0], spectrum[-1])
        self.assertGreater(result["integrated_output_noise_v_rms"], 0.0)
        diode = result["spectral_contributions"]["D1"]
        self.assertGreater(diode[0], diode[-1])


if __name__ == "__main__":
    unittest.main()
