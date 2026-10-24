# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Source-path numerical replay and process-boundary failure checks."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_serdes_worker_reference as verifier
from python.spike_core.si_workflow import run_si_workflow


class SerdesWorkerReferenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.executable = Path(self.directory.name) / "identity-only.bin"
        self.executable.write_bytes(b"original nonexecutable hash fixture")

    def test_same_eleven_requests_and_gates_use_explicit_adapter(self):
        def request(executable, method, params):
            self.assertEqual(method, "run_si_workflow")
            return {"ok": True, "result": run_si_workflow(params["request"])}
        report = verifier.verify(self.executable, request=request)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["workflow_process_calls"], 11)
        self.assertFalse(report["production_qualified"])
        self.assertEqual(report["board_qualification"], "not_evaluated")
        self.assertTrue(all(row["pass"] for row in report["qualification"]["criteria"]))

    def test_process_failure_is_not_a_numerical_pass(self):
        with self.assertRaisesRegex(RuntimeError, "no successful"):
            verifier.verify(self.executable, request=lambda *args: {"ok": False})

    def test_failed_gate_and_missing_executions_are_rejected(self):
        with patch.object(verifier, "qualification_report", return_value={"status": "fail"}):
            with self.assertRaisesRegex(RuntimeError, "gates failed"):
                verifier.verify(self.executable)

    def test_replaced_executable_invalidates_evidence(self):
        def changed(**kwargs):
            self.executable.write_bytes(b"changed")
            return {"status": "pass"}
        with patch.object(verifier, "qualification_report", side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, "changed during"):
                verifier.verify(self.executable)


if __name__ == "__main__":
    unittest.main()
