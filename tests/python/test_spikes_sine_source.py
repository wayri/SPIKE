# SPDX-License-Identifier: Apache-2.0

import math
import os
from dataclasses import replace
from pathlib import Path
import unittest

from python.spikes.contracts import AnalysisDirective, CircuitProject, ProbeDescriptor
from python.spikes.native_runner import _populate, run_native_project
from python.spikes.native_abi import NativeABIError, load_native_library
from python.spikes.netlist import NetlistParseError, parse_netlist
from python.spikes.runner import run_project


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get(
    "SPIKES_TEST_NATIVE_LIBRARY",
    ROOT / "build-peec-native" / "spikes_c_api.dll",
))


def expected_sine(time_s):
    offset, amplitude = 0.75, 2.0
    frequency_hz, delay_s, damping_per_s, phase_deg = 1000.0, 0.0002, 250.0, 30.0
    elapsed = max(0.0, time_s - delay_s)
    return offset + amplitude * math.exp(-damping_per_s * elapsed) * math.sin(
        2.0 * math.pi * frequency_hz * elapsed + math.radians(phase_deg)
    )


DECK = """damped delayed sinusoid
V1 out 0 SIN(750m 2 1k 200u 250 30)
R1 out 0 1k
.tran 100u 1m
.end
"""


class SineSourceParserTests(unittest.TestCase):
    def test_full_form_round_trips_and_optional_terms_default_to_zero(self):
        project = parse_netlist(DECK, native_extensions=True)
        source = project.elements[0]
        self.assertEqual(source.waveform.kind, "sin")
        self.assertEqual(source.waveform.sine[:3], (0.75, 2.0, 1000.0))
        self.assertAlmostEqual(source.waveform.sine[3], 0.0002)
        self.assertEqual(source.waveform.sine[4:], (250.0, 30.0))
        self.assertAlmostEqual(source.value, 1.75)
        self.assertEqual(CircuitProject.from_dict(project.to_dict()), project)

        minimal = parse_netlist(
            "V1 out 0 SIN(1 2 1k)\nR1 out 0 1k\n.tran 100u 1m\n",
            native_extensions=True,
        ).elements[0].waveform
        self.assertEqual(minimal.sine, (1.0, 2.0, 1000.0, 0.0, 0.0, 0.0))

    def test_unsupported_or_unbounded_forms_fail_closed(self):
        invalid = (
            "SIN(0 1)",
            "SIN(0 1 0)",
            "SIN(0 1 -1k)",
            "SIN(0 1 1k -1u)",
            "SIN(0 1 1k 0 -1)",
            "SIN(0 1 1k 0 0 0 7)",
        )
        for form in invalid:
            deck = f"V1 out 0 {form}\nR1 out 0 1k\n.tran 100u 1m\n"
            with self.subTest(form=form), self.assertRaises(NetlistParseError):
                parse_netlist(deck, native_extensions=True)

    def test_standard_parser_still_requires_explicit_native_extension_opt_in(self):
        with self.assertRaises(NetlistParseError):
            parse_netlist(DECK)


class SineSourceReferenceExecutionTests(unittest.TestCase):
    def test_reference_mna_matches_closed_form_at_every_sample(self):
        project = parse_netlist(
            DECK, probes=(ProbeDescriptor.parse("V(out)"),), native_extensions=True
        )
        result = run_project(project).to_dict()
        self.assertEqual(result["status"], "completed")
        times = result["data"]["time_s"]
        values = result["probes"]["V(out)"]["values"]
        self.assertEqual(len(times), 11)
        for time_s, observed in zip(times, values, strict=True):
            self.assertAlmostEqual(observed, expected_sine(time_s), delta=2.0e-12)

    def test_native_sine_construction_does_not_allocate_an_output_grid(self):
        class CapturingCircuit:
            def __init__(self):
                self.values = None

            def add_sine_voltage_source(self, _name, _positive, _negative, values):
                self.values = tuple(values)

            def add_resistor(self, *_args):
                pass

        project = parse_netlist(DECK, native_extensions=True)
        huge = replace(
            project,
            analysis=AnalysisDirective(
                mode="transient", time_step_s=1.0e-300, stop_time_s=1.0e300
            ),
        )
        captured = CapturingCircuit()
        _populate(captured, huge)
        self.assertEqual(captured.values, project.elements[0].waveform.sine)

        tiny = replace(
            project,
            analysis=AnalysisDirective(
                mode="transient", time_step_s=100.0e-15, stop_time_s=1.0e-12
            ),
        )
        circuit = CapturingCircuit()
        _populate(circuit, tiny)
        self.assertEqual(circuit.values, project.elements[0].waveform.sine)


@unittest.skipUnless(LIBRARY.is_file(), "built SPIKES C ABI library is unavailable")
class SineSourceOwnedNativeExecutionTests(unittest.TestCase):
    def test_adaptive_rc_refines_against_closed_form_at_internal_points(self):
        library = load_native_library(LIBRARY)
        errors, counts = [], []
        omega, tau = 2 * math.pi * 1000, 1e-4
        # Startup BE has no embedded estimate, so refine its maximum step too.
        for maximum_step, tolerance in ((2e-5, 1e-2), (5e-6, 1e-4)):
            with library.circuit() as circuit:
                circuit.add_sine_voltage_source("V1", "in", "0", (0, 1, 1000, 0, 0, 0))
                circuit.add_resistor("R1", "in", "out", 1000)
                circuit.add_capacitor("C1", "out", "0", 1e-7)
                with circuit.solve_transient(time_step_s=maximum_step, stop_time_s=0.002,
                        integration_method="bdf2", adaptive_time_step=True,
                        lte_relative_tolerance=tolerance,
                        lte_absolute_tolerance=tolerance * 1e-2) as result:
                    self.assertEqual(result.status, "converged")
                    discrepancies = []
                    for index in range(result.point_count):
                        time = result.time(index)
                        expected = (math.sin(omega * time) - omega * tau * math.cos(omega * time)
                                    + omega * tau * math.exp(-time / tau)) / (1 + (omega * tau) ** 2)
                        discrepancies.append(abs(result.node_voltage(index, "out") - expected))
                        self.assertAlmostEqual(result.node_voltage(index, "in"),
                                               math.sin(omega * time), delta=2e-12)
                    errors.append(max(discrepancies))
                    counts.append(result.point_count)
        self.assertLess(errors[1], errors[0] / 4)
        self.assertLess(errors[1], 2e-3)
        self.assertGreater(counts[1], counts[0])

    def test_direct_abi_phase_delay_current_source_and_validation(self):
        library = load_native_library(LIBRARY)
        with library.circuit() as circuit:
            circuit.add_sine_current_source("I1", "0", "out", (0.75, 2, 1000, 0.0002, 250, 30))
            circuit.add_resistor("R1", "out", "0", 1)
            for values in ((0, 1, -1, 0, 0, 0), (0, 1, 1, -1, 0, 0),
                           (0, 1, 1, 0, -1, 0), (0, 1, math.inf, 0, 0, 0)):
                with self.subTest(values=values), self.assertRaises((ValueError, NativeABIError)):
                    circuit.add_sine_voltage_source("bad", "bad", "0", values)
            with circuit.solve_transient(time_step_s=0.00013, stop_time_s=0.001) as result:
                self.assertEqual(result.status, "converged")
                self.assertGreaterEqual(result.diagnostics()["source_breakpoint_steps"], 1)
                for index in range(result.point_count):
                    self.assertAlmostEqual(result.node_voltage(index, "out"),
                                           expected_sine(result.time(index)), delta=2e-12)

    def test_missing_analytic_abi_fails_instead_of_silently_sampling(self):
        library = load_native_library(LIBRARY)
        library.sine_sources_available = False
        with library.circuit() as circuit:
            with self.assertRaisesRegex(NativeABIError, "lacks analytic SIN"):
                circuit.add_sine_voltage_source("V1", "out", "0", (0, 1, 1000, 0, 0, 0))

    @unittest.skipUnless(os.environ.get("SPIKES_TEST_NGSPICE"), "explicit ngspice executable required")
    def test_same_deck_against_ngspice_for_delayed_phase_and_loaded_rc(self):
        from python.spikes.compatibility_qualification import _reference_case
        for body, signal in (
            ("V1 out 0 SIN(750m 2 1k 230u 250 30)\nR1 out 0 1k", "out"),
            ("I1 0 out SIN(750u 2m 1k 230u 250 30)\nR1 out 0 1k", "out"),
            ("V1 in 0 SIN(0 1 1k)\nR1 in out 1k\nC1 out 0 100n", "out"),
        ):
            # ngspice may straddle the derivative kink at TD; 100 ns bounds
            # reference interpolation there without relaxing the 50 uV gate.
            deck = f"Analytic SIN qualification\n{body}\n.tran 100n 1m uic\n.end\n"
            with self.subTest(body=body):
                project = parse_netlist(deck, native_extensions=True)
                result = run_native_project(project, LIBRARY, integration_method="bdf2").to_dict()
                self.assertEqual(result["status"], "completed")
                compared = _reference_case(Path(os.environ["SPIKES_TEST_NGSPICE"]), deck,
                    "node_voltage_v", signal, result["data"]["time_s"],
                    result["data"]["node_voltage_v"][signal], 5e-5)
                self.assertEqual(compared["status"], "passed", compared["maximum_absolute_error"])

    def test_owned_kernel_matches_closed_form_on_requested_tran_grid(self):
        project = parse_netlist(
            DECK, probes=(ProbeDescriptor.parse("V(out)"),), native_extensions=True
        )
        result = run_native_project(
            project, LIBRARY, integration_method="backward_euler"
        ).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            result["provenance"]["sin_source_lowering"], "native_analytic"
        )
        times = result["data"]["time_s"]
        values = result["probes"]["V(out)"]["values"]
        for time_s, observed in zip(times, values, strict=True):
            self.assertAlmostEqual(observed, expected_sine(time_s), delta=2.0e-12)

    def test_reactive_load_converges_to_independent_rc_solution(self):
        resistance = 1000.0
        capacitance = 100.0e-9
        frequency = 1000.0
        tau = resistance * capacitance
        omega = 2.0 * math.pi * frequency
        denominator = 1.0 + (omega * tau) ** 2

        def maximum_tail_error(step):
            deck = f"""RC sine response
V1 in 0 SIN(0 1 {frequency})
R1 in out {resistance}
C1 out 0 {capacitance}
.tran {step} 5m
.end
"""
            project = parse_netlist(
                deck, probes=(ProbeDescriptor.parse("V(out)"),), native_extensions=True
            )
            result = run_native_project(
                project, LIBRARY, integration_method="backward_euler"
            ).to_dict()
            self.assertEqual(result["status"], "completed")
            errors = []
            for time_s, observed in zip(
                result["data"]["time_s"],
                result["probes"]["V(out)"]["values"],
                strict=True,
            ):
                if time_s < 1.0e-3:
                    continue
                expected = (
                    math.sin(omega * time_s)
                    - omega * tau * math.cos(omega * time_s)
                    + omega * tau * math.exp(-time_s / tau)
                ) / denominator
                errors.append(abs(observed - expected))
            return max(errors)

        coarse_error = maximum_tail_error(20.0e-6)
        fine_error = maximum_tail_error(10.0e-6)
        self.assertLess(fine_error, coarse_error)
        self.assertLess(fine_error, 0.035)


if __name__ == "__main__":
    unittest.main()
