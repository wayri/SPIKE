# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import math
import os
from pathlib import Path
import unittest

from python.spikes.fault_campaign import FaultCampaign, FaultEvent, NativeFaultTarget, event_from_hazard
from python.spikes.fault_injection import FaultSite
from python.spikes.reliability import BathtubHazard
from python.spikes.environment_faults import Exposure, ParameterResponse
from python.spikes.native_abi import load_native_library

SITE = FaultSite("gs", "RGS", "resistance_ohm", 1e9, 0.01, 1e9, "gate_source_short")
ROOT = Path(__file__).resolve().parents[2]
ENGINE = Path(os.environ.get("SPIKES_TEST_NATIVE_LIBRARY", ROOT / "build-spikes-faults-20261010/Release/spikes_c_api.dll"))


class Target:
    """Deterministic contract fixture; actual native comparisons are separate."""
    def __init__(self):
        self.time_s = 0
        self.value = SITE.healthy_value
        self.solutions = []
    def inject_fault(self, name, value):
        if name != SITE.name: raise ValueError("Unknown fault")
        self.value = SITE.validate(value)
    def step(self, dt):
        self.time_s += dt
        self.solutions.append((self.time_s, self.value))
    def save(self): self.saved = deepcopy((self.time_s, self.value, self.solutions))
    def restore(self): self.time_s, self.value, self.solutions = deepcopy(self.saved)


class FaultCampaignTests(unittest.TestCase):
    def test_boundary_injection_clear_and_checkpoint_cursor_replay(self):
        target = Target()
        campaign = FaultCampaign(target, [SITE], [FaultEvent(2.5e-5, "gs", 0.1), FaultEvent(4e-5, "gs", None)])
        campaign.advance_to(2e-5)
        campaign.save()
        trace = campaign.advance_to(6e-5)
        result = deepcopy(target.solutions)
        self.assertEqual(trace[0]["applied_time_s"], 2.5e-5)
        self.assertEqual(trace[1]["applied_time_s"], 4e-5)
        self.assertEqual(next(v for t, v in result if t > 2.5e-5), 0.1)
        self.assertEqual(next(v for t, v in result if t > 4e-5), SITE.healthy_value)
        campaign.restore()
        self.assertEqual(target.time_s, 2e-5)
        self.assertEqual(target.value, SITE.healthy_value)
        self.assertEqual(campaign.advance_to(6e-5), trace)
        self.assertEqual(target.solutions, result)

    def test_invalid_schedule_is_rejected_before_target_mutation(self):
        for events in ([FaultEvent(1, "unknown", 1)], [FaultEvent(1, "gs", 0)],
                       [FaultEvent(2, "gs", 1), FaultEvent(1, "gs", 1)],
                       [FaultEvent(1, "gs", 1), FaultEvent(1, "gs", 2)], [FaultEvent(1e-13, "gs", 1)]):
            target = Target()
            with self.assertRaises(ValueError): FaultCampaign(target, [SITE], events)
            self.assertEqual((target.time_s, target.value, target.solutions), (0, SITE.healthy_value, []))
        for bad in (True, float("inf"), -1):
            with self.assertRaises(ValueError): FaultEvent(bad, "gs", 1)

    def test_step_budget_and_rejected_step_preserve_cursor(self):
        target = Target()
        campaign = FaultCampaign(target, [SITE], [], maximum_steps=2)
        with self.assertRaisesRegex(RuntimeError, "step limit"): campaign.advance_to(1)
        self.assertEqual(len(target.solutions), 2)
        self.assertEqual(campaign.cursor, 0)
        class Rejecting(Target):
            def step(self, dt): raise RuntimeError("Solver rejected")
        target = Rejecting()
        campaign = FaultCampaign(target, [SITE], [FaultEvent(1e-5, "gs", 0.1)])
        with self.assertRaisesRegex(RuntimeError, "Solver rejected"): campaign.advance_to(2e-5)
        self.assertEqual(campaign.cursor, 0)
        self.assertEqual(target.time_s, 0)

    def test_start_event_and_roundoff_tail_do_not_require_zero_steps(self):
        target = Target()
        campaign = FaultCampaign(target, [SITE], [FaultEvent(0, "gs", 1)])
        campaign.advance_to(3e-5+1e-17)
        self.assertEqual(campaign.cursor, 1)
        self.assertEqual(target.value, 1)
        self.assertAlmostEqual(target.time_s, 3e-5+1e-17, delta=1e-20)
        with self.assertRaises(ValueError): campaign.advance_to(0)

    def test_nonfinite_post_step_clock_is_never_success(self):
        for value in (math.nan, math.inf, -1):
            class Broken(Target):
                def step(self, dt): self.time_s = value
            campaign = FaultCampaign(Broken(), [SITE], [])
            with self.assertRaises(ValueError): campaign.advance_to(1e-5)
            self.assertEqual(campaign.completed_steps, 0)

    def test_hazard_to_seconds_without_silent_aging_acceleration(self):
        # Forced quantile for a declared mode, not a claim that this event is likely.
        hazard = BathtubHazard(100)
        q = -math.expm1(-100e-9*(2e-5/3600))
        event = event_from_hazard(SITE, 1, hazard, age_hours=2000, quantile=q, start_time_s=1e-5, horizon_s=1)
        self.assertAlmostEqual(event.time_s, 3e-5, delta=1e-18)
        self.assertIsNone(event_from_hazard(SITE, 1, hazard, age_hours=0, quantile=0.5, start_time_s=0, horizon_s=1))


@unittest.skipUnless(ENGINE.is_file(), "Specified real fault-enabled engine unavailable")
class NativeCampaignTests(unittest.TestCase):
    def test_actual_native_schedule_and_checkpoint_replay_match_piecewise_rc(self):
        library = load_native_library(ENGINE)
        with library.circuit() as circuit:
            circuit.add_voltage_source("V1", "in", "0", 1)
            circuit.add_resistor("R1", "in", "out", 1000)
            circuit.add_capacitor("C1", "out", "0", 1e-6)
            site = FaultSite("series", "R1", "resistance_ohm", 1000, 1, 1e6, "resistance_degradation")
            with circuit.transient_session() as session:
                target = NativeFaultTarget(session, [site])
                self.addCleanup(target.close)
                hazard = BathtubHazard(100)
                event = event_from_hazard(site, 2000, hazard, age_hours=2000,
                    quantile=hazard.probability(2000, 1e-4/3600), start_time_s=0, horizon_s=1)
                campaign = FaultCampaign(target, [site], [event])
                campaign.advance_to(5e-5)
                campaign.save()
                trace = campaign.advance_to(2e-4)
                expected = 1 - (1.01**-10)*(1.005**-10)
                observed = session.node_voltage("out")
                self.assertAlmostEqual(observed, expected, delta=3e-12)
                campaign.restore()
                self.assertEqual(campaign.advance_to(2e-4), trace)
                self.assertEqual(session.node_voltage("out"), observed)

    def test_actual_native_dose_mapping_changes_nmos_current(self):
        library = load_native_library(ENGINE)
        with library.circuit() as circuit:
            circuit.add_voltage_source("VD", "d", "0", 5)
            circuit.add_voltage_source("VG", "g", "0", 3)
            circuit.add_mosfet_level1("M1", "d", "g", "0", "0",
                threshold_voltage_v=2, transconductance_a_per_v2=0.001)
            site = FaultSite("vto", "M1", "threshold_voltage_v", 2, -10, 10, "supplied_tid_threshold_shift")
            response = ParameterResponse("vto", "DEMO-A", "Synthetic", "dose_rad_si", 0,
                -1e-5, 2, 0, 1e5, "V", "original synthetic fixture", "specified synthetic conditions",
                "what-if only; no hardware evidence")
            with circuit.transient_session() as session:
                target = NativeFaultTarget(session, [site])
                self.addCleanup(target.close)
                target.step(1e-5)
                normal = session.element_current("M1")
                result = response.apply(target, Exposure(300, dose_rad_si=1e4),
                    part_number="DEMO-A", manufacturer="Synthetic")
                target.step(1e-5)
                self.assertEqual(result["model_status"], "unverified_scenario")
                self.assertGreater(session.element_current("M1"), normal)
                self.assertAlmostEqual(session.element_current("M1"), 0.5*0.001*1.1**2+5e-12, delta=1e-10)


if __name__ == "__main__": unittest.main()
