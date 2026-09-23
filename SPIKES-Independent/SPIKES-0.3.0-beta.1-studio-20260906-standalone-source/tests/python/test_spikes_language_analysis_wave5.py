import math
import unittest

from python.spikes import (
    NONLINEAR_DECK_RESULT_CONTRACT,
    compile_behavioral_expression,
    parse_nonlinear_analysis_deck,
    run_nonlinear_analysis_deck,
)


class ExtendedBehavioralGrammarTests(unittest.TestCase):
    def test_spice_power_case_insensitive_functions_and_two_argument_gradients(self):
        compiled = compile_behavioral_expression(
            "HYPOT(V(x),2)^2 + atan2(V(y),V(x)) + LOG10(V(z))"
        )
        evaluated = compiled.evaluate((3.0, 4.0, 100.0))
        self.assertAlmostEqual(evaluated.value, 13.0 + math.atan2(4.0, 3.0) + 2.0, places=13)
        self.assertAlmostEqual(evaluated.gradient[0], 6.0 - 4.0 / 25.0, places=13)
        self.assertAlmostEqual(evaluated.gradient[1], 3.0 / 25.0, places=13)
        self.assertAlmostEqual(evaluated.gradient[2], 1.0 / (100.0 * math.log(10.0)), places=13)

    def test_piecewise_if_limit_min_max_have_selected_branch_derivatives(self):
        compiled = compile_behavioral_expression(
            "IF(V(c)>0, limit(V(x),-2,2), min(V(x),V(y))) + max(V(y),-3)"
        )
        evaluated = compiled.evaluate((1.0, 4.0, -1.0))
        self.assertEqual(evaluated.value, 1.0)
        self.assertEqual(evaluated.gradient, (0.0, 0.0, 1.0))

    def test_nondifferentiable_boundaries_and_unsafe_forms_fail_closed(self):
        cases = (
            ("abs(V(x))", (0.0,)),
            ("min(V(x),V(y))", (1.0, 1.0)),
            ("IF(V(x)>0,1,2)", (0.0,)),
            ("limit(V(x),0,1)", (1.0,)),
        )
        for expression, values in cases:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                compile_behavioral_expression(expression).evaluate(values)
        for expression in ("V(x)==1", "V(x) and V(y)", "open('x')"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                compile_behavioral_expression(expression)

    def test_if_uses_lazy_guarded_branch_evaluation(self):
        compiled = compile_behavioral_expression("IF(V(x)>0,log(V(x)),0)")
        evaluated = compiled.evaluate((-2.0,))
        self.assertEqual(evaluated.value, 0.0)
        self.assertEqual(evaluated.gradient, (0.0,))


class NonlinearDeckIntegrationTests(unittest.TestCase):
    def test_noise_card_runs_biased_diode_noise_and_bounded_frequency_reduction(self):
        deck = parse_nonlinear_analysis_deck(
            "noise deck\nV1 in 0 1\nR1 in out 1k\nD1 out 0 DM\n"
            ".model DM D(IS=1e-12 N=1 TNOM=27)\n"
            ".noise V(out) V1 DEC 2 1 100\n.end"
        )
        result = run_nonlinear_analysis_deck(deck)
        self.assertEqual(result["contract"], NONLINEAR_DECK_RESULT_CONTRACT)
        self.assertEqual(result["analysis"]["mode"], "biased_noise")
        data = result["result"]["data"]
        self.assertEqual(data["frequency_hz"], [1.0, math.sqrt(10.0), 10.0, math.sqrt(1000.0), 100.0])
        self.assertGreater(data["integrated_output_noise_v_rms"], 0.0)
        self.assertGreater(data["input_referred_noise_density_v_sqrt_hz"], 0.0)

    def test_sensitivity_card_defaults_to_all_supported_parameters(self):
        deck = parse_nonlinear_analysis_deck(
            "sens deck\nV1 in 0 10\nR1 in out 1k\nR2 out 0 1k\n.sens V(out)\n.end"
        )
        result = run_nonlinear_analysis_deck(deck)["result"]
        elements = result["data"]["elements"]
        self.assertEqual(set(elements), {"V1", "R1", "R2"})
        self.assertAlmostEqual(elements["R1"]["derivative"], -0.0025, places=12)

    def test_distortion_and_nonlinear_small_signal_cards_execute(self):
        body = (
            "poly\nV1 in 0 2\nB1 out 0 V={{V(in)+0.1*V(in)^2+0.01*V(in)^3}}\n"
            "R1 out 0 1k\n{card}\n.end"
        )
        distortion = run_nonlinear_analysis_deck(parse_nonlinear_analysis_deck(
            body.format(card=".disto V(out) V1 0.1 0.01")
        ))["result"]
        self.assertAlmostEqual(distortion["data"]["derivatives"]["second"], 0.32, places=9)
        small_signal = run_nonlinear_analysis_deck(parse_nonlinear_analysis_deck(
            body.format(card=".nlss V(out) V1 2 30")
        ))["result"]
        self.assertAlmostEqual(small_signal["data"]["output"]["magnitude"], 3.04, places=12)
        self.assertAlmostEqual(small_signal["data"]["output"]["phase_deg"], 30.0, places=12)
        two_tone = run_nonlinear_analysis_deck(parse_nonlinear_analysis_deck(
            body.format(card=".disto2 V(out) V1 0.1 0.2 0.01")
        ))["result"]
        products = two_tone["data"]["signed_peak_amplitudes"]
        self.assertAlmostEqual(products["f1_plus_f2"], 0.0032, places=10)
        self.assertAlmostEqual(products["2f1_minus_f2"], 0.000015, places=10)
        self.assertAlmostEqual(products["2f2_minus_f1"], 0.00003, places=10)

    def test_ambiguous_or_unsupported_deck_forms_fail_closed(self):
        base = "bad\nV1 in 0 1\nR1 in 0 1k\n{card}\n.end"
        cards = (
            ".disto DEC 10 1 1Meg",
            ".noise V(in) V1 DEC 10 1",
            ".nlss V(missing) V1",
            ".sens V(in) MISSING",
        )
        for card in cards:
            with self.subTest(card=card), self.assertRaises(ValueError):
                parse_nonlinear_analysis_deck(base.format(card=card))
        with self.assertRaises(ValueError):
            parse_nonlinear_analysis_deck(base.format(card=".noise V(in) V1 LIN 2 1 2") + "\n.sens V(in)")


if __name__ == "__main__":
    unittest.main()
