# SPDX-License-Identifier: Apache-2.0
"""Stopping-evidence cases for the retained openEMS adapter."""
import unittest

from python.spike_core.openems_stopping import parse_openems_stopping


RUNTIME = {"engine": "openEMS", "python_package_version": "0.0.36"}


def parse(log, **execution):
    return parse_openems_stopping(
        log,
        requested_end_criteria=1e-9,
        requested_max_timesteps=80000,
        execution={"returncode": 0, "timed_out": False, "quota_exceeded": False,
                   "log_truncated": False, **execution},
        runtime_identity=RUNTIME,
    )


class OpenemsStoppingTests(unittest.TestCase):
    def test_requested_decay_reached_is_distinct_from_execution(self):
        result = parse("""| openEMS 64bit -- version v0.0.36
Max. number of timesteps: 80000
[@ 3m] Timestep: 17000 || Energy: ~2.46e-23 (- 96.36dB)
Time for 17000 iterations with 405224.00 cells : 163.10 sec
""")
        self.assertEqual(result["execution_status"], "completed")
        self.assertTrue(result["did_reach_requested_decay"])
        self.assertFalse(result["timestep_cap_hit"])
        self.assertEqual(result["actual_final_timestep_count"], 17000)
        self.assertEqual(result["stopping_reason"], "requested_decay_observed")
        self.assertEqual(result["runtime_identity"]["python_package_version"], "0.0.36")
        self.assertEqual(result["runtime_identity"]["native_engine_version"], "0.0.36")

    def test_cap_hit_preserves_failed_decay_and_actual_count(self):
        result = parse("""Max. number of timesteps: 80000
[@ 3m] Timestep: 78524 || Energy: ~3.63e-23 (-81.74dB)
RunFDTD: Warning: Max. number of timesteps was reached before the end-criteria of -90dB was reached...
Time for 80000 iterations with 97336.00 cells : 206.45 sec
""")
        self.assertEqual(result["execution_status"], "completed")
        self.assertFalse(result["did_reach_requested_decay"])
        self.assertTrue(result["timestep_cap_hit"])
        self.assertEqual(result["actual_final_timestep_count"], 80000)
        self.assertEqual(result["observed_energy_decay_db"], -81.74)
        self.assertEqual(result["stopping_reason"], "timestep_cap_before_requested_decay")

    def test_timeout_does_not_promote_observed_sample(self):
        result = parse("[@ 1m] Timestep: 12000 || Energy: ~1e-24 (-95.0dB)\n",
                       returncode=-1, timed_out=True)
        self.assertEqual(result["execution_status"], "timed_out")
        self.assertIsNone(result["did_reach_requested_decay"])
        self.assertIsNone(result["actual_final_timestep_count"])
        self.assertEqual(result["last_observed_timestep"], 12000)
        self.assertEqual(result["stopping_reason"], "execution_timeout")

    def test_malformed_stopping_lines_remain_unknown(self):
        result = parse("Timestep: potato || Energy: definitely-low\nTime for many iterations\n")
        self.assertEqual(result["evidence_status"], "malformed")
        self.assertIsNone(result["did_reach_requested_decay"])
        self.assertIsNone(result["actual_final_timestep_count"])
        self.assertEqual(result["stopping_reason"], "malformed_stopping_evidence")

    def test_missing_evidence_is_not_success(self):
        result = parse("openEMS setup complete\n")
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["evidence_status"], "missing")
        self.assertIsNone(result["did_reach_requested_decay"])
        self.assertIsNone(result["timestep_cap_hit"])
        self.assertEqual(result["stopping_reason"], "requested_decay_unconfirmed")

    def test_nonfinite_energy_token_is_malformed_not_reached(self):
        result = parse("""Max. number of timesteps: 80000
[@ 1m] Timestep: 17000 || Energy: ~1e999 (-95dB)
Time for 17000 iterations with 1 cells : 1 sec
""")
        self.assertEqual(result["evidence_status"], "malformed")
        self.assertEqual(result["malformed_relevant_line_count"], 1)
        self.assertIsNone(result["observed_energy_decay_db"])
        self.assertIsNone(result["did_reach_requested_decay"])

    def test_cap_at_final_count_wins_over_stale_reached_sample(self):
        result = parse("""Max. number of timesteps: 80000
[@ 1m] Timestep: 17000 || Energy: ~1e-23 (-95dB)
Time for 80000 iterations with 1 cells : 1 sec
""")
        self.assertTrue(result["timestep_cap_hit"])
        self.assertFalse(result["did_reach_requested_decay"])
        self.assertEqual(result["stopping_reason"], "timestep_cap_without_requested_decay")

    def test_later_malformed_progress_withholds_earlier_good_sample(self):
        result = parse("""Max. number of timesteps: 80000
[@ 1m] Timestep: 17000 || Energy: ~1e-23 (-95dB)
[@ 2m] Timestep: 18000 || Energy: ~nan (-95dB)
Time for 18000 iterations with 1 cells : 1 sec
""")
        self.assertEqual(result["observed_energy_timestep"], 17000)
        self.assertEqual(result["actual_final_timestep_count"], 18000)
        self.assertEqual(result["evidence_status"], "malformed")
        self.assertIsNone(result["did_reach_requested_decay"])

    def test_native_cap_mismatch_is_explicit_and_withholds_success(self):
        result = parse("""Max. number of timesteps: 17000
[@ 1m] Timestep: 17000 || Energy: ~1e-23 (-95dB)
Time for 17000 iterations with 1 cells : 1 sec
""")
        self.assertEqual(result["native_reported_max_timesteps"], 17000)
        self.assertFalse(result["native_timestep_cap_matches_request"])
        self.assertTrue(result["timestep_cap_hit"])
        self.assertEqual(result["evidence_status"], "inconsistent")
        self.assertIsNone(result["did_reach_requested_decay"])
        self.assertEqual(result["stopping_reason"], "runtime_configuration_mismatch")

    def test_oversized_count_and_repeated_markers_are_bounded_malformed_lines(self):
        oversized = "9" * 5000
        repeated = ("Timestep: 1 || Energy: ~1e-3 (-1dB) " * 1000)
        result = parse(f"Time for {oversized} iterations\n{repeated}\n")
        self.assertEqual(result["evidence_status"], "malformed")
        self.assertEqual(result["malformed_relevant_line_count"], 2)
        self.assertIsNone(result["actual_final_timestep_count"])
        self.assertIsNone(result["did_reach_requested_decay"])


if __name__ == "__main__":
    unittest.main()
