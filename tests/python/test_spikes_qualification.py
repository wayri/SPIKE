import contextlib
import json
import os
from io import StringIO
from pathlib import Path
import unittest

from python.spikes.cli import EXIT_OK, main
from python.spikes.qualification import (
    QUALIFICATION_REPORT_CONTRACT,
    run_qualification_suite,
)


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get(
    "SPIKES_TEST_NATIVE_LIBRARY",
    ROOT / "build-peec-native" / "spikes_c_api.dll",
))


@unittest.skipUnless(LIBRARY.is_file(), "built SPIKES C ABI library is unavailable")
class SpikesQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_qualification_suite(LIBRARY, repetitions=1, wall_steps=3)

    def test_complex_native_and_interactive_corpus_passes(self):
        report = self.report
        self.assertEqual(report["contract"], QUALIFICATION_REPORT_CONTRACT)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"], {"total": 14, "passed": 14, "failed": 0})
        case_ids = {item["case_id"] for item in report["cases"]}
        self.assertEqual(case_ids, {
            "dc.balanced_bridge", "dc.large_resistor_ladder",
            "dc.threaded_cg_ladder",
            "dc.sparse_solver_ladder",
            "dc.gmres_controlled_switch",
            "dc.shockley_diode", "transient.series_rlc",
            "rf.series_resonator", "motor.fixed_speed_armature",
            "switching.pwm_resistive", "switching.synchronous_buck",
            "interactive.native_control_replay", "realtime.continuous_pacing",
            "realtime.deadline_trip",
        })
        self.assertTrue(all(item["timing_ns"] for item in report["cases"]))

    def test_report_keeps_hard_realtime_hil_and_speed_claims_blocked(self):
        qualification = self.report["qualification"]
        self.assertTrue(qualification["soft_realtime_functionally_tested"])
        self.assertFalse(qualification["hard_realtime_qualified"])
        self.assertFalse(qualification["hil_qualified"])
        self.assertFalse(qualification["competitive_speed_claim_eligible"])
        self.assertEqual(self.report["claims"], [])

    def test_interaction_is_next_step_and_checkpoint_replay_is_exact(self):
        case = next(
            item for item in self.report["cases"]
            if item["case_id"] == "interactive.native_control_replay"
        )
        observation = case["observations"][0]
        self.assertEqual(observation["control_to_effect_steps"], 1)
        self.assertTrue(observation["momentary_released"])
        self.assertTrue(observation["checkpoint_replay_bit_exact"])
        self.assertEqual(
            observation["native_session_diagnostics"]["completed_steps"], 16
        )

    def test_cli_emits_the_same_bounded_contract(self):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main((
                "qualification", "--library", str(LIBRARY),
                "--repetitions", "1", "--wall-steps", "2",
            ))
        payload = json.loads(output.getvalue())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["contract"], QUALIFICATION_REPORT_CONTRACT)
        self.assertEqual(payload["status"], "passed")

    def test_bounds_fail_closed(self):
        with self.assertRaises(ValueError):
            run_qualification_suite(LIBRARY, repetitions=0)
        with self.assertRaises(ValueError):
            run_qualification_suite(LIBRARY, wall_steps=0)


if __name__ == "__main__":
    unittest.main()
