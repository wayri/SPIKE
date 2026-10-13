# SPDX-License-Identifier: Apache-2.0

import math
import os
from pathlib import Path
import unittest

from python.spikes.contracts import CircuitProject, ProbeDescriptor
from python.spikes.native_runner import run_native_project
from python.spikes.netlist import NetlistParseError, parse_netlist
from python.spikes.runner import native_request, run_project
from python.spike_core.native_mna import validate_native_mna_request


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get(
    "SPIKES_TEST_NATIVE_LIBRARY",
    ROOT / "build-spikes-current-vs18-20260906" / "Release" / "spikes_c_api.dll",
))

EXP_DECK = """* explicit exponential source
V1 out 0 EXP(200m 1.7 2u 1.5u 7u 2u)
R1 out 0 1k
.tran 1u 10u
.end
"""

SFFM_DECK = """* delayed phase shifted single frequency FM source
V1 out 0 SFFM(400m 1.2 1k 2 200 200u 30 -20)
R1 out 0 1k
.tran 100u 1m
.end
"""


def expected_exp(time_s: float) -> float:
    initial, pulsed = 0.2, 1.7
    rise_delay, rise_tau, fall_delay, fall_tau = 2.0e-6, 1.5e-6, 7.0e-6, 2.0e-6
    if time_s < rise_delay:
        return initial
    rise = (pulsed - initial) * (1.0 - math.exp(-(time_s - rise_delay) / rise_tau))
    if time_s < fall_delay:
        return initial + rise
    fall = (initial - pulsed) * (1.0 - math.exp(-(time_s - fall_delay) / fall_tau))
    return initial + rise + fall


def expected_sffm(time_s: float) -> float:
    delay = 200.0e-6
    if time_s <= delay:
        return 0.0
    elapsed = time_s - delay
    modulation_phase = 2.0 * math.pi * 200.0 * elapsed + math.radians(30.0)
    carrier_phase = (
        2.0 * math.pi * 1000.0 * elapsed
        + 2.0 * math.sin(modulation_phase)
        + math.radians(-20.0)
    )
    return 0.4 + 1.2 * math.sin(carrier_phase)


class ExpAndSffmParserTests(unittest.TestCase):
    def test_exp_and_modern_sffm_round_trip(self):
        exp_project = parse_netlist(EXP_DECK, native_extensions=True)
        exponential = exp_project.elements[0].waveform
        self.assertEqual(exponential.kind, "exp")
        self.assertEqual(exponential.exponential, (0.2, 1.7, 2e-6, 1.5e-6, 7e-6, 2e-6))
        self.assertEqual(CircuitProject.from_dict(exp_project.to_dict()), exp_project)

        sffm_project = parse_netlist(SFFM_DECK, native_extensions=True)
        sffm = sffm_project.elements[0].waveform
        self.assertEqual(sffm.kind, "sffm")
        self.assertEqual(sffm.sffm[:5], (0.4, 1.2, 1000.0, 2.0, 200.0))
        self.assertAlmostEqual(sffm.sffm[5], 0.0002)
        self.assertEqual(sffm.sffm[6:], (30.0, -20.0))
        self.assertEqual(CircuitProject.from_dict(sffm_project.to_dict()), sffm_project)

        legacy_five = parse_netlist(
            "V1 out 0 SFFM(0 1 1k 2 100)\nR1 out 0 1k\n.tran 100u 1m\n",
            native_extensions=True,
        ).elements[0].waveform
        self.assertEqual(legacy_five.sffm, (0.0, 1.0, 1000.0, 2.0, 100.0, 0.0, 0.0, 0.0))

    def test_unsafe_or_analysis_dependent_forms_fail_closed(self):
        invalid = (
            "EXP(0 1 1u 1u 5u)",
            "EXP(0 1 1u 0 5u 1u)",
            "EXP(0 1 5u 1u 1u 1u)",
            "SFFM(0 1 1k 2)",
            "SFFM(0 1 1k -1 100)",
            "SFFM(0 1 1k 11 100)",
            "SFFM(0 1 0 0 100)",
            "SFFM(0 1 1k 2 100 -1u)",
            "SFFM(0 1 1k 2 100 0 0 0 0)",
        )
        for form in invalid:
            deck = f"V1 out 0 {form}\nR1 out 0 1k\n.tran 1u 10u\n"
            with self.subTest(form=form), self.assertRaises(NetlistParseError):
                parse_netlist(deck, native_extensions=True)

    def test_standard_parser_requires_native_extension_opt_in(self):
        for deck in (EXP_DECK, SFFM_DECK):
            with self.subTest(deck=deck.splitlines()[0]), self.assertRaises(NetlistParseError):
                parse_netlist(deck)


class ExpAndSffmReferenceExecutionTests(unittest.TestCase):
    def test_native_request_contract_requires_complete_waveforms(self):
        for deck, missing_key in ((EXP_DECK, "rise_time_constant_s"), (SFFM_DECK, "modulation_index")):
            with self.subTest(missing=missing_key):
                request = native_request(parse_netlist(deck, native_extensions=True))
                del request["elements"][0]["waveform"][missing_key]
                validation = validate_native_mna_request(request)
                self.assertFalse(validation["valid"])
                self.assertIn(
                    "MNA_WAVEFORM_FIELD_REQUIRED",
                    {issue["code"] for issue in validation["issues"]},
                )

    def test_python_mna_matches_independent_equations_at_every_sample(self):
        for deck, expected in ((EXP_DECK, expected_exp), (SFFM_DECK, expected_sffm)):
            with self.subTest(source=deck.splitlines()[0]):
                project = parse_netlist(
                    deck, probes=(ProbeDescriptor.parse("V(out)"),), native_extensions=True
                )
                result = run_project(project).to_dict()
                self.assertEqual(result["status"], "completed")
                for time_s, observed in zip(
                    result["data"]["time_s"], result["probes"]["V(out)"]["values"], strict=True
                ):
                    self.assertAlmostEqual(observed, expected(time_s), delta=3.0e-12)


@unittest.skipUnless(LIBRARY.is_file(), "specified owned SPIKES C ABI library is unavailable")
class ExpAndSffmOwnedNativeExecutionTests(unittest.TestCase):
    def test_owned_dll_lowering_matches_equations_on_requested_grid(self):
        for kind, deck, expected in (
            ("exp", EXP_DECK, expected_exp),
            ("sffm", SFFM_DECK, expected_sffm),
        ):
            with self.subTest(kind=kind):
                project = parse_netlist(
                    deck, probes=(ProbeDescriptor.parse("V(out)"),), native_extensions=True
                )
                result = run_native_project(
                    project, LIBRARY, integration_method="backward_euler"
                ).to_dict()
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["provenance"][f"{kind}_source_lowering"], "fixed_step_pwl_samples")
                self.assertEqual(
                    result["provenance"]["analytic_source_sample_semantics"],
                    "exact_at_requested_tran_times",
                )
                for time_s, observed in zip(
                    result["data"]["time_s"], result["probes"]["V(out)"]["values"], strict=True
                ):
                    self.assertAlmostEqual(observed, expected(time_s), delta=3.0e-12)

    def test_exp_driven_rc_error_decreases_under_step_refinement(self):
        resistance = 1000.0
        capacitance = 100.0e-9
        circuit_tau = resistance * capacitance
        source_tau = 300.0e-6
        delay = 200.0e-6

        def exact(time_s: float) -> float:
            if time_s <= delay:
                return 0.0
            elapsed = time_s - delay
            return 1.0 - (
                source_tau * math.exp(-elapsed / source_tau)
                - circuit_tau * math.exp(-elapsed / circuit_tau)
            ) / (source_tau - circuit_tau)

        def maximum_error(step_s: float) -> float:
            deck = f"""* EXP RC refinement
V1 in 0 EXP(0 1 {delay} {source_tau} 10m 1m)
R1 in out {resistance}
C1 out 0 {capacitance}
.tran {step_s} 2m
.end
"""
            project = parse_netlist(
                deck, probes=(ProbeDescriptor.parse("V(out)"),), native_extensions=True
            )
            result = run_native_project(
                project, LIBRARY, integration_method="backward_euler"
            ).to_dict()
            self.assertEqual(result["status"], "completed")
            return max(
                abs(observed - exact(time_s))
                for time_s, observed in zip(
                    result["data"]["time_s"], result["probes"]["V(out)"]["values"], strict=True
                )
                if time_s >= delay
            )

        coarse_error = maximum_error(40.0e-6)
        fine_error = maximum_error(20.0e-6)
        self.assertLess(fine_error, coarse_error)
        self.assertLess(fine_error, 0.04)


if __name__ == "__main__":
    unittest.main()
