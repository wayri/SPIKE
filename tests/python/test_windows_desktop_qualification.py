# SPDX-License-Identifier: Apache-2.0
"""Acceptance policy tests; actual GUI acceptance uses the installed executable."""
import unittest
from scripts.verify_windows_desktop import await_qualification, PASS_TITLE, FAIL_TITLE

class Process:
    def __init__(self, status=None): self.status = status
    def poll(self): return self.status

class DesktopQualificationTests(unittest.TestCase):
    def run_wait(self, titles, status=None):
        now = [0.0]
        return await_qualification(Process(status), lambda: titles, timeout=1,
                                   clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0]+seconds))
    def test_actual_complete_proof_is_required(self):
        self.assertEqual(self.run_wait([PASS_TITLE]), PASS_TITLE)
    def test_running_or_error_dialog_is_not_success(self):
        for title in ["SPIKE", "SPIKE development frontend unavailable", "SPIKE PANEL QUALIFICATION RUNNING", "SPIKE PANEL QUALIFICATION PASS - fake"]:
            with self.subTest(title=title), self.assertRaisesRegex(RuntimeError, "timed out"):
                self.run_wait([title])
    def test_failure_is_not_overridden_by_success(self):
        with self.assertRaisesRegex(RuntimeError, "lost draft"):
            self.run_wait([PASS_TITLE, FAIL_TITLE+" - lost draft"])
    def test_early_exit_even_zero_is_not_frontend_readiness(self):
        with self.assertRaisesRegex(RuntimeError, "exited before"):
            self.run_wait([PASS_TITLE], 0)
    def test_no_window_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.run_wait([])

if __name__ == "__main__": unittest.main()
