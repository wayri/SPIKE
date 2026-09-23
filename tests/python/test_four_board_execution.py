"""Four-board executable SI reference, not a Marble geometry qualification."""
import copy
import unittest
from unittest.mock import patch

from python.spike_core.multiboard_execution import run_independent_si_batch, MultiboardExecutionError
from tests.python import test_multiboard_analysis as fixtures


def four_board_request():
    base = fixtures.MultiboardAnalysisTests()._si_batch_request()
    model = next(iter(base["multiboard_request"]["designs"].values()))
    multi = fixtures.request(count=4)
    multi["domain"] = "si"
    multi["designs"] = {f"design-{i:02d}": copy.deepcopy(model) for i in range(4)}
    base["multiboard_request"] = multi
    suite = base["jobs"][0]["suite_request"]
    base["jobs"] = [{"board_id": f"board-{i:02d}", "suite_request": copy.deepcopy(suite)} for i in range(4)]
    return base


class FourBoardExecutionTests(unittest.TestCase):
    def test_four_real_independent_channel_jobs(self):
        result = run_independent_si_batch(four_board_request())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["jobs"]), 4)
        self.assertEqual(len({job["namespace"] for job in result["jobs"]}), 4)
        self.assertFalse(result["coupling"]["included"])
        self.assertFalse(result["production_qualified"])

    def test_bad_last_board_rejected_before_any_execution(self):
        value = four_board_request()
        value["jobs"][-1]["suite_request"]["lanes"] = []
        with patch("python.spike_core.multiboard_execution.run_si_protocol_test_suite") as execute:
            with self.assertRaises(MultiboardExecutionError):
                run_independent_si_batch(value)
            execute.assert_not_called()

    def test_aggregate_lane_budget_rejected_before_any_execution(self):
        value = four_board_request()
        value["resource_limits"] = {"maximum_total_lanes": 3}
        with patch("python.spike_core.multiboard_execution.run_si_protocol_test_suite") as execute:
            with self.assertRaises(MultiboardExecutionError):
                run_independent_si_batch(value)
            execute.assert_not_called()
