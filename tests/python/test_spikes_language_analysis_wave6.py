import math
import os
from pathlib import Path
import unittest

from python.spikes import (
    compile_behavioral_expression,
    parse_nonlinear_analysis_deck,
    run_nonlinear_analysis_deck,
)


class BehavioralGrammarWave6Tests(unittest.TestCase):
    def test_tan_atanh_values_and_derivatives(self):
        for function, oracle, slope in (
            ("TAN", math.tan, lambda x: 1 + math.tan(x)**2),
            ("ATANH", math.atanh, lambda x: 1 / (1-x*x)),
        ):
            expression = compile_behavioral_expression(f"{function}(V(x))")
            for x in (-.75, -.25, 0., .25, .75):
                with self.subTest(function=function, x=x):
                    result = expression.evaluate((x,))
                    self.assertAlmostEqual(result.value, oracle(x), places=13)
                    self.assertAlmostEqual(result.gradient[0], slope(x), places=13)
                    numerical = (oracle(x+1e-6)-oracle(x-1e-6))/2e-6
                    self.assertAlmostEqual(result.gradient[0], numerical, places=8)
        for x in (-2., -1., 1., 2.):
            with self.assertRaisesRegex(ValueError, "atanh"):
                compile_behavioral_expression("atanh(V(x))").evaluate((x,))

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


@unittest.skipUnless(os.environ.get("SPIKES_TEST_NATIVE_LIBRARY"), "explicit native DLL required")
class NativeBehavioralParityTests(unittest.TestCase):
    def test_smooth_sources_against_native_and_ngspice(self):
        from python.spikes.competitive_benchmark import shared_behavioral_cases, _ngspice_observer
        from python.spike_core.ngspice_plugin import NgspicePlugin
        from python.spikes.native_runner import run_native_project
        from python.spikes.netlist import parse_netlist
        plugin = NgspicePlugin()
        self.assertTrue(plugin.executable, "ngspice must be installed for this opt-in parity test")
        observer = _ngspice_observer(plugin)
        library = Path(os.environ["SPIKES_TEST_NATIVE_LIBRARY"])
        for case in shared_behavioral_cases():
            with self.subTest(case=case.case_id):
                result = run_native_project(parse_netlist(case.netlist), library)
                self.assertEqual(result.status, "completed")
                native = result.data["node_voltage_v"]["out"]
                external = observer(case)
                self.assertAlmostEqual(native, case.expected, delta=case.absolute_tolerance)
                self.assertAlmostEqual(external, case.expected, delta=case.absolute_tolerance)
                self.assertAlmostEqual(native, external, delta=case.absolute_tolerance)


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
