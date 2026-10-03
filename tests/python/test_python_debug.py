"""Cross-process behavior of the integrated Python debugger."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.script_debug import (
    python_debug_command,
    python_debug_status,
    start_python_debug,
)


DESIGN = {
    "contract": "spike/v1", "design_id": "debug-board", "name": "Debug board",
    "source_format": "test", "units": "mm", "layers": [], "nets": [],
    "tracks": [], "vias": [], "pads": [], "zones": [], "components": [],
    "stackup": [], "issues": [], "metadata": {},
}


class PythonDebugTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sessions = self.root / "sessions"
        self.environment = patch.dict(os.environ, {
            "SPIKE_WORKSPACE": str(self.root),
            "SPIKE_DEBUG_SESSION_ROOT": str(self.sessions),
        })
        self.environment.start()
        self.session_ids: list[str] = []

    def tearDown(self) -> None:
        for session_id in self.session_ids:
            try:
                state = python_debug_status({"session_id": session_id})
                if state["status"] in {"starting", "running", "paused"}:
                    python_debug_command({"session_id": session_id, "command": "stop"})
            except (OSError, ValueError):
                pass
        self.environment.stop()
        self.temporary.cleanup()

    def start(self, code: str, **params: object) -> dict[str, object]:
        result = start_python_debug({
            "code": code, "filename": "debug_target.py", "timeout_seconds": 10, **params,
        })
        self.session_ids.append(str(result["session_id"]))
        return result

    def await_status(self, session_id: str, expected: set[str], timeout: float = 4) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        result: dict[str, object] = {}
        while time.monotonic() < deadline:
            result = python_debug_status({"session_id": session_id})
            if result["status"] in expected:
                return result
            time.sleep(0.025)
        self.fail(f"debug session did not reach {expected}: {result}")

    def test_break_step_into_out_locals_and_output(self):
        code = "def add(value):\n    inner = value + 1\n    return inner\nbase = 4\nanswer = add(base)\nprint(answer)\n"
        started = self.start(code, breakpoints=[5])
        session_id = str(started["session_id"])
        paused = self.await_status(session_id, {"paused"})
        self.assertEqual(paused["line"], 5)
        self.assertEqual(paused["frames"][0]["locals"]["base"], "4")
        revision = int(paused["revision"])

        command = python_debug_command({"session_id": session_id, "command": "step_into"})
        self.assertEqual(command["command_sequence"], 1)
        self.assertGreaterEqual(int(command["command_ack"]), 1)
        entered = self.await_status(session_id, {"paused"})
        self.assertGreater(int(entered["revision"]), revision)
        self.assertEqual(entered["frames"][0]["name"], "add")
        self.assertEqual(entered["frames"][0]["locals"]["value"], "4")

        python_debug_command({"session_id": session_id, "command": "step_out"})
        stepped_out = self.await_status(session_id, {"paused"})
        self.assertEqual(stepped_out["line"], 6)
        completed = python_debug_command({"session_id": session_id, "command": "continue"})
        if completed["status"] != "completed":
            completed = self.await_status(session_id, {"completed"})
        self.assertEqual(completed["return_code"], 0)
        self.assertEqual(completed["stdout"].strip(), "5")

    def test_step_into_neighboring_local_module(self):
        (self.root / "helper.py").write_text(
            "def calculate(value):\n    doubled = value * 2\n    return doubled\n", encoding="utf-8",
        )
        started = self.start(
            "import helper\nvalue = 3\nanswer = helper.calculate(value)\nprint(answer)\n",
            breakpoints=[3], working_directory=str(self.root),
        )
        session_id = str(started["session_id"])
        self.await_status(session_id, {"paused"})
        python_debug_command({"session_id": session_id, "command": "step_into"})
        entered = self.await_status(session_id, {"paused"})
        self.assertEqual(entered["frames"][0]["name"], "calculate")
        self.assertTrue(str(entered["filename"]).endswith("helper.py"))
        self.assertEqual(entered["frames"][0]["locals"]["value"], "3")

    def test_stop_terminates_child_blocked_in_call(self):
        started = self.start("import time\nprint('waiting', flush=True)\ntime.sleep(60)\n")
        session_id = str(started["session_id"])
        running = self.await_status(session_id, {"running"})
        deadline = time.monotonic() + 3
        while "waiting" not in str(running["stdout"]) and time.monotonic() < deadline:
            time.sleep(0.025)
            running = python_debug_status({"session_id": session_id})
        stopped = python_debug_command({"session_id": session_id, "command": "stop"})
        self.assertEqual(stopped["status"], "stopped")
        self.assertIn("stopped", stopped["reason"])

    def test_pause_and_breakpoint_update_are_acknowledged(self):
        started = self.start(
            "import time\nfor index in range(200):\n    value = index * 2\n    time.sleep(0.01)\nprint(value)\n",
        )
        session_id = str(started["session_id"])
        self.await_status(session_id, {"running"})
        command = python_debug_command({"session_id": session_id, "command": "pause"})
        if command["status"] != "paused":
            command = self.await_status(session_id, {"paused"})
        self.assertGreaterEqual(int(command["command_ack"]), 1)
        updated = python_debug_command({
            "session_id": session_id, "command": "breakpoints", "breakpoints": [5],
        })
        self.assertEqual(updated["status"], "paused")
        self.assertGreaterEqual(int(updated["command_ack"]), 2)

    def test_hard_timeout_terminates_blocked_child(self):
        result = start_python_debug({
            "code": "import time\ntime.sleep(60)\n", "filename": "timeout.py",
            "timeout_seconds": 1,
        })
        self.session_ids.append(str(result["session_id"]))
        failed = self.await_status(str(result["session_id"]), {"failed"}, timeout=4)
        self.assertEqual(failed["return_code"], 124)
        self.assertIn("time limit", failed["reason"])

    def test_exception_and_nonfinite_publication_fail_cleanly(self):
        raised = self.start("print('before')\nraise ValueError('bad debug script')\n")
        failed = self.await_status(str(raised["session_id"]), {"failed"})
        self.assertIn("before", failed["stdout"])
        self.assertIn("ValueError: bad debug script", failed["stderr"])

        nonfinite = self.start(
            "spike.publish_scalar_field('voltage_v', "
            "[{'x_mm': 1, 'y_mm': 2, 'value': float('nan')}])\n",
            design=DESIGN,
        )
        rejected = self.await_status(str(nonfinite["session_id"]), {"failed"})
        self.assertIn("non-finite", rejected["stderr"])
        self.assertIsNone(rejected.get("published_result"))

    def test_parent_rejects_result_for_another_board(self):
        code = """spike.publish_result({
    'contract': 'spike/v1', 'analysis_id': 'wrong-board', 'status': 'completed',
    'mode': 'dc', 'model_status': 'unvalidated', 'summary': {}, 'fields': {},
    'networks': {}, 'probes': [], 'issues': [],
    'provenance': {'design_id': 'another-board', 'design_digest_sha256': '0' * 64,
                   'solver': 'debug-test'}})
"""
        started = self.start(code, design=DESIGN)
        failed = self.await_status(str(started["session_id"]), {"failed", "completed"})
        self.assertEqual(failed["status"], "failed")
        self.assertIn("does not match", failed["stderr"])
        self.assertIsNone(failed["published_result"])

    def test_parent_admits_design_bound_result(self):
        started = self.start(
            "spike.publish_scalar_field('voltage_v', "
            "[{'x_mm': 1, 'y_mm': 2, 'value': 3.3}])\n",
            design=DESIGN,
        )
        completed = self.await_status(str(started["session_id"]), {"completed", "failed"})
        self.assertEqual(completed["status"], "completed")
        published = completed["published_result"]
        self.assertEqual(published["provenance"]["design_id"], "debug-board")
        self.assertEqual(published["provenance"]["extension_id"], "spike.python-workspace")


if __name__ == "__main__":
    unittest.main()
