"""Cross-process behavior of the integrated Python debugger."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from python.spike_core import script_debug
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
                # Terminal publication precedes OS exit; release the test's
                # owned process/CWD before removing its temporary workspace.
                directory = self.sessions / session_id
                script_debug._terminate_process(script_debug._state_pid(directory, state))
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
        pid = int((self.sessions / session_id / "pid.txt").read_text(encoding="ascii"))
        self.assertFalse(script_debug._process_alive(pid))

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
        deadline = time.monotonic() + 4
        failed = self.await_status(str(result["session_id"]), {"failed"}, timeout=4)
        self.assertEqual(failed["return_code"], 124)
        self.assertIn("time limit", failed["reason"])
        directory = self.sessions / str(result["session_id"])
        pid = int((directory / "pid.txt").read_text(encoding="ascii"))
        while script_debug._process_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(script_debug._process_alive(pid))

    def test_original_deadline_terminates_child_before_watchdog_initializes(self):
        real_popen = subprocess.Popen

        def stalled_startup(command, **kwargs):
            return real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)

        began = time.monotonic()
        with patch.object(script_debug.subprocess, "Popen", side_effect=stalled_startup):
            result = self.start("print('must not run')\n", timeout_seconds=1)
        session_id = str(result["session_id"])
        directory = self.sessions / session_id
        request = script_debug._read_json(directory / "request.json")
        self.assertEqual(request["deadline"] - request["created_at"], 1)
        failed = self.await_status(session_id, {"failed"}, timeout=4)
        self.assertEqual(failed["return_code"], 124)
        self.assertIn("time limit", failed["reason"])
        self.assertEqual(failed["stdout"], "")
        self.assertLess(time.monotonic() - began, 4)
        self.assertFalse(script_debug._process_alive(int((directory / "pid.txt").read_text())))

    def test_liveness_probe_preserves_running_child_and_detects_exit(self):
        with subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) as child:
            try:
                for _ in range(5):
                    self.assertTrue(script_debug._process_alive(child.pid))
                    time.sleep(0.01)
                    self.assertIsNone(child.poll())
            finally:
                child.terminate()
                child.wait(timeout=3)
            # Popen still holds its Windows handle: PID existence is not liveness.
            self.assertFalse(script_debug._process_alive(child.pid))
        with subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(259)"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) as child:
            child.wait(timeout=3)
            # 259 is also STILL_ACTIVE; a signaled handle is authoritative.
            self.assertFalse(script_debug._process_alive(child.pid))

    @unittest.skipUnless(os.name == "nt", "Windows process wait semantics")
    def test_windows_liveness_probe_fails_conservatively_and_closes_handles(self):
        for invalid_pid in (0, -1, True, "123", 1.5, 0x100000000):
            with self.subTest(invalid_pid=invalid_pid), patch("ctypes.WinDLL") as library:
                self.assertFalse(script_debug._process_alive(invalid_pid))
                library.assert_not_called()
        for handle, error, wait_status, alive in (
            (0, 87, 0, False), (0, 5, 0, True),
            (0x100000001, 0, 0, False), (0x100000001, 0, 258, True),
            (0x100000001, 0, 0xFFFFFFFF, True),
        ):
            with self.subTest(handle=handle, error=error, wait_status=wait_status):
                kernel = Mock()
                kernel.OpenProcess.return_value = handle
                kernel.WaitForSingleObject.return_value = wait_status
                with patch("ctypes.WinDLL", return_value=kernel), \
                        patch("ctypes.get_last_error", return_value=error):
                    self.assertEqual(script_debug._process_alive(123), alive)
                kernel.OpenProcess.assert_called_once_with(0x00100000, False, 123)
                if handle:
                    kernel.WaitForSingleObject.assert_called_once_with(handle, 0)
                    kernel.CloseHandle.assert_called_once_with(handle)
                else:
                    kernel.WaitForSingleObject.assert_not_called()
                    kernel.CloseHandle.assert_not_called()

    def test_exit_during_status_read_preserves_child_terminal_state(self):
        request = {"session_id": "exit-race", "token": "test-token", "deadline": time.time() + 60}
        state = {
            "contract": script_debug.CONTRACT, **request, "status": "running",
            "revision": 2, "pid": 123, "command_ack": 0, "frames": [],
        }
        (self.root / "request.json").write_text(json.dumps(request), encoding="utf-8")
        for status, return_code, reason in (
            ("failed", 124, "Python debug session exceeded its time limit."),
            ("completed", 0, "finished"),
            ("stopped", 0, "stopped by user"),
        ):
            with self.subTest(status=status):
                script_debug._atomic_json(self.root / "state.json", state)
                terminal = {**state, "status": status, "return_code": return_code,
                            "reason": reason, "revision": 3}
                published = False

                def exit_after_state_read(pid):
                    # Child publication/exit occurs after the parent's initial read.
                    nonlocal published
                    if not published:
                        script_debug._atomic_json(self.root / "state.json", terminal)
                        published = True
                    return False

                with patch.object(script_debug, "_process_alive", side_effect=exit_after_state_read):
                    result = script_debug._snapshot(self.root, touch=False)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["return_code"], return_code)
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["revision"], 3)
                self.assertEqual(script_debug._read_json(self.root / "state.json"), terminal)

    def test_dead_child_without_terminal_publication_still_fails(self):
        request = {"session_id": "unexpected-exit", "token": "test-token", "deadline": time.time() + 60}
        state = {"contract": script_debug.CONTRACT, **request,
                 "status": "running", "revision": 2, "pid": 123}
        (self.root / "request.json").write_text(json.dumps(request), encoding="utf-8")
        script_debug._atomic_json(self.root / "state.json", state)
        with patch.object(script_debug, "_process_alive", return_value=False):
            result = script_debug._snapshot(self.root, touch=False)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["return_code"], 1)
        self.assertIn("exited unexpectedly", result["reason"])

    def test_terminal_state_reread_must_pass_identity_validation(self):
        request = {"session_id": "exit-race", "token": "test-token", "deadline": time.time() + 60}
        state = {"contract": script_debug.CONTRACT, **request,
                 "status": "running", "revision": 2, "pid": 123}
        for key in ("contract", "session_id", "token"):
            with self.subTest(key=key):
                terminal = {**state, "status": "completed", key: "wrong"}
                with patch.object(script_debug, "_read_json", side_effect=[request, state, terminal]), \
                        patch.object(script_debug, "_process_alive", return_value=False):
                    with self.assertRaisesRegex(ValueError, "token validation"):
                        script_debug._snapshot(self.root, touch=False)

    def test_invalid_deadline_cannot_authorize_process_termination(self):
        for deadline in (None, True, "expired", float("nan"), float("inf"), 10 ** 1000):
            with self.subTest(deadline=deadline):
                request = {"session_id": "deadline", "token": "token", "deadline": deadline}
                state = {"contract": script_debug.CONTRACT, **request,
                         "status": "starting", "pid": 123}
                with patch.object(script_debug, "_read_json", side_effect=[request, state]), \
                        patch.object(script_debug, "_terminate_process") as terminate:
                    with self.assertRaisesRegex(ValueError, "deadline must be finite"):
                        script_debug._snapshot(self.root, touch=False)
                terminate.assert_not_called()

    def test_expired_poll_preserves_terminal_state_and_discards_partial_output(self):
        request = {"session_id": "deadline", "token": "token", "deadline": time.time() - 1}
        (self.root / "request.json").write_text(json.dumps(request), encoding="utf-8")
        active = {"contract": script_debug.CONTRACT, **request, "status": "starting",
                  "pid": 123, "frames": [{"partial": True}], "published_result": {"partial": True},
                  "ui_actions": [{"partial": True}]}
        for terminal_status in (None, "completed", "stopped"):
            with self.subTest(terminal_status=terminal_status):
                script_debug._atomic_json(self.root / "state.json", active)

                def settle_child(pid):
                    if terminal_status is not None:
                        script_debug._atomic_json(self.root / "state.json", {
                            "contract": script_debug.CONTRACT, **request,
                            "status": terminal_status, "return_code": 0,
                        })

                with patch.object(script_debug, "_terminate_process", side_effect=settle_child), \
                        patch.object(script_debug, "_process_alive", return_value=False):
                    result = script_debug._snapshot(self.root, touch=False)
                self.assertEqual(result["status"], terminal_status or "failed")
                self.assertEqual(result["return_code"], 0 if terminal_status else 124)
                self.assertNotIn("published_result", result)
                self.assertEqual(result["ui_actions"], [])

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
