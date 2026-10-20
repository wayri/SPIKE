# SPDX-License-Identifier: Apache-2.0
"""Worker budget must not include preceding optional emulator fixtures."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.package_smoke import worker_timed_out


class PackageWorkerBudgetTests(unittest.TestCase):
    def test_fixture_setup_does_not_spend_unstarted_worker_budget(self):
        self.assertFalse(worker_timed_out(None,10000))
        self.assertFalse(worker_timed_out(100,100.5))

    def test_actual_worker_still_has_strict_sixty_second_budget(self):
        self.assertFalse(worker_timed_out(100,160))
        self.assertTrue(worker_timed_out(100,160.001))


if __name__=='__main__':unittest.main()
