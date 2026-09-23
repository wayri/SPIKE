# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Trusted study staging must never redirect unrelated command cases."""
import unittest
from unittest.mock import Mock, patch
from scripts.fan_wsl_scratch import ScratchRunner


class ScratchTests(unittest.TestCase):
    def worker(self):
        worker = object.__new__(ScratchRunner)
        worker.mounted = "/mnt/c/study/case"
        worker.remote = "/tmp/spike-fan-abcdefghij"
        worker.case = "case"
        worker.runner = Mock(return_value={"return_code": 0})
        worker._transfer = Mock()
        return worker

    def test_only_expected_case_is_replaced_and_inputs_reverified(self):
        worker = self.worker()
        with patch("scripts.fan_wsl_scratch.load_verified_runnable_case") as verify:
            worker(["wsl", "solver", "-case", worker.mounted], timeout_s=10)
        self.assertEqual(worker.runner.call_args.args[0][-1], worker.remote)
        worker._transfer.assert_called_once_with(["/usr/bin/cp", "-r", "--", worker.remote + "/.", worker.mounted + "/"])
        verify.assert_called_once_with("case")

    def test_unrelated_case_rejected(self):
        worker = self.worker()
        with self.assertRaisesRegex(ValueError, "unexpected"):
            worker(["wsl", "solver", "-case", "/elsewhere"])
        worker.runner.assert_not_called()

    def test_probe_is_not_staged(self):
        worker = self.worker()
        worker(["wsl", "solver", "-case", "/probe", "-help"])
        worker._transfer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
