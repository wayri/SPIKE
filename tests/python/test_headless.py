# SPDX-License-Identifier: Apache-2.0
"""Actual subprocess and bounded workflow acceptance checks."""
import json
import os
import sys
import tempfile
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.headless import load_document, run_request, run_workflow, WORKFLOW_CONTRACT
from python.spike_core.mcp_server import McpServer
from python.spike_core.automation import SpikeAutomation


class HeadlessTests(unittest.TestCase):
    def child(self, code, timeout=5):
        return run_request({"method": "test"}, timeout, command=[sys.executable, "-c", code])

    def test_real_worker_without_desktop_and_preserved_error(self):
        result = run_request({"method": "list_importers"}, 30)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["meta"]["method"], "list_importers")
        failure = run_request({"method": "missing_headless_operation"}, 30)
        self.assertFalse(failure["ok"])
        self.assertEqual(failure["error_code"], "SPIKE-BE-IPC-E-0002")

    def test_timeout_and_nonzero_exit(self):
        self.assertEqual(self.child('import time; time.sleep(30)', .2)["error_code"], "SPIKE-HEADLESS-TIMEOUT")
        self.assertEqual(self.child('import sys; sys.exit(7)')["error_code"], "SPIKE-HEADLESS-EXIT")

    def test_interruption_and_supervisor_start_failure_reap_worker(self):
        popen = subprocess.Popen
        real_sleep = time.sleep
        interrupted = False

        def interrupt_once(delay):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt()
            return real_sleep(delay)

        for target, effect, expected in (
            ('python.spike_core.headless.time.sleep', interrupt_once, 'SPIKE-HEADLESS-CANCELLED'),
            ('python.spike_core.headless.threading.Thread.start', RuntimeError('thread unavailable'), 'SPIKE-HEADLESS-START'),
        ):
            with self.subTest(expected=expected):
                processes = []

                def capture(*args, **kwargs):
                    process = popen(*args, **kwargs)
                    processes.append(process)
                    return process

                with patch('python.spike_core.headless.subprocess.Popen', side_effect=capture), \
                        patch(target, side_effect=effect):
                    result = self.child('import time; time.sleep(30)')
                self.assertEqual(result['error_code'], expected)
                self.assertNotIn('cleanup_warning', result)
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(processes[0].poll())
                self.assertTrue(all(stream.closed for stream in
                                    (processes[0].stdin, processes[0].stdout, processes[0].stderr)))

    def test_timeout_terminates_owned_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'survived'
            ready = Path(directory) / 'ready'
            child = f'import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).touch()'
            parent = f'import subprocess,sys,time; from pathlib import Path; subprocess.Popen([sys.executable,"-c",{child!r}]); Path({str(ready)!r}).touch(); time.sleep(30)'
            self.assertEqual(self.child(parent, 1)["error_code"], "SPIKE-HEADLESS-TIMEOUT")
            self.assertTrue(ready.exists(), 'Descendant was actually launched')
            time.sleep(2.2)
            self.assertFalse(marker.exists(), 'Owned descendant survived cancellation')

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object ownership')
    def test_windows_job_stops_actual_child_but_not_unowned_process(self):
        import ctypes
        from ctypes import wintypes
        from python.spike_core.headless import _WindowsProcessTree

        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        api.TerminateProcess.restype = wintypes.BOOL
        api.CloseHandle.argtypes = (wintypes.HANDLE,)
        api.CloseHandle.restype = wintypes.BOOL
        handles = []
        # Bypass Windows venv redirectors: this unrelated sentinel is a single
        # directly owned interpreter and can be reaped by its process handle.
        unrelated = subprocess.Popen([getattr(sys, '_base_executable', sys.executable),
                                      '-c', 'import time; time.sleep(30)'],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with tempfile.TemporaryDirectory() as directory:
                ready = Path(directory) / 'child-pid'
                child = f'import os,time; from pathlib import Path; Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(30)'
                parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); time.sleep(30)'
                terminate = _WindowsProcessTree.terminate

                def capture_child(job):
                    # Keep the actual process handle, so PID reuse cannot fake
                    # termination and test cleanup targets only this child.
                    if ready.exists():
                        handle = api.OpenProcess(0x00100001, False, int(ready.read_text()))
                        if handle:
                            handles.append(handle)
                    return terminate(job)

                with patch.object(_WindowsProcessTree, 'terminate', capture_child):
                    result = self.child(parent, 1)
                self.assertEqual(result['error_code'], 'SPIKE-HEADLESS-TIMEOUT')
                self.assertNotIn('cleanup_warning', result)
                self.assertEqual(len(handles), 1, 'Actual child was running before termination')
                self.assertEqual(api.WaitForSingleObject(handles[0], 5000), 0,
                                 'Owned child process handle did not become signalled')
                self.assertIsNone(unrelated.poll(), 'Unowned process must remain alive')
        finally:
            for handle in handles:
                if api.WaitForSingleObject(handle, 0) != 0:
                    api.TerminateProcess(handle, 1)
                    api.WaitForSingleObject(handle, 5000)
                api.CloseHandle(handle)
            unrelated.kill()
            unrelated.wait(timeout=5)

    @unittest.skipUnless(os.name == 'nt', 'Windows suspended process admission')
    def test_windows_failed_job_assignment_never_runs_worker(self):
        from python.spike_core.headless import _WindowsProcessTree
        processes = []
        popen = subprocess.Popen

        def capture(*args, **kwargs):
            process = popen(*args, **kwargs)
            processes.append(process)
            return process

        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'ran-without-job'
            code = f'from pathlib import Path; Path({str(marker)!r}).touch()'
            with patch.object(_WindowsProcessTree, 'assign', side_effect=OSError('assignment refused')), \
                    patch('python.spike_core.headless.subprocess.Popen', side_effect=capture):
                result = self.child(code)
            self.assertEqual(result['error_code'], 'SPIKE-HEADLESS-START')
            self.assertFalse(marker.exists())
            self.assertEqual(len(processes), 1)
            self.assertIsNotNone(processes[0].poll(), 'Suspended worker must be reaped on admission failure')
            self.assertTrue(all(stream.closed for stream in
                                (processes[0].stdin, processes[0].stdout, processes[0].stderr)))

    @unittest.skipUnless(os.name == 'nt', 'Windows descendant ownership after parent exit')
    def test_windows_normal_worker_exit_closes_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'survived-parent'
            ready = Path(directory) / 'launched'
            child = f'import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).touch()'
            parent = ('import subprocess,sys,json; from pathlib import Path; '
                      'request=json.loads(sys.stdin.readline()); '
                      f'subprocess.Popen([sys.executable,"-c",{child!r}],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
                      f'Path({str(ready)!r}).touch(); '
                      'print(json.dumps({"id":request["id"],"ok":True}))')
            self.assertTrue(self.child(parent)['ok'])
            self.assertTrue(ready.exists())
            time.sleep(2.2)
            self.assertFalse(marker.exists(), 'Descendant survived normal supervisor completion')

    def test_cli_workflow_and_nonzero_failure_envelopes(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / 'plan.json'
            plan = {"contract": WORKFLOW_CONTRACT, "steps": [
                {"name": "catalog", "method": "list_importers", "params": {}},
                {"name": "blocked", "method": "missing_operation", "params": {}},
                {"name": "never", "method": "capabilities", "params": {}},
            ]}
            request.write_text(json.dumps(plan), encoding='utf-8')
            result = subprocess.run([sys.executable, '-m', 'python.spike_cli', '--compact', 'workflow', str(request)],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 2, result.stderr)
            envelope = json.loads(result.stdout)
            self.assertTrue(envelope['steps']['catalog']['ok'])
            self.assertEqual(envelope['failed_step'], 'blocked')
            self.assertNotIn('never', envelope['steps'])

    def test_cli_warning_policy_and_malformed_document(self):
        import contextlib
        import io
        from unittest.mock import patch
        from python.spike_core.cli import main
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / 'request.json'
            request.write_text('{"method":"test"}', encoding='utf-8')
            output = io.StringIO()
            envelope = {"ok": True, "result": {"issues": [{"severity": "warning"}]}}
            with patch('python.spike_core.headless.run_request', return_value=envelope), contextlib.redirect_stdout(output):
                self.assertEqual(main(['--fail-on-warning', 'worker-call', str(request)]), 4)
            self.assertEqual(json.loads(output.getvalue()), envelope)
            request.write_text('[' * 2000 + '0' + ']' * 2000, encoding='utf-8')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['worker-call', str(request)]), 1)
            self.assertFalse(json.loads(output.getvalue())['ok'])

    def test_protocol_and_response_identity(self):
        for code in ('print("not json")', 'print(\'{"ok":true,"id":"wrong"}\')',
                     'print(\'{"ok":true,"result":NaN}\')'):
            self.assertEqual(self.child(code)["error_code"], "SPIKE-HEADLESS-PROTOCOL")

    def test_bounded_output(self):
        from unittest.mock import patch
        with patch('python.spike_core.headless.MAX_OUTPUT_BYTES', 1024):
            result = self.child('print("x" * 65536)')
        self.assertEqual(result["error_code"], "SPIKE-HEADLESS-OUTPUT-LIMIT")

    def test_request_admission(self):
        for request in ({}, {"method": "test", "params": []}, {"method": "test", "shell": "bad"},
                        {"method": "test", "params": {"value": float("nan")}}):
            with self.assertRaises(ValueError):
                run_request(request)
        for timeout in (0, -1, float("inf"), True, 86401):
            with self.assertRaises(ValueError):
                run_request({"method": "test"}, timeout)

    def test_workflow_refs_and_stop_on_error(self):
        calls = []
        def execute(request, timeout):
            calls.append(request)
            return {"ok": True, "result": {"a/b": [{"~key": 42}]}} if len(calls) == 1 else {"ok": False, "error_code": "blocked"}
        plan = {"contract": WORKFLOW_CONTRACT, "steps": [
            {"name": "load", "method": "read", "params": {}},
            {"name": "run", "method": "run", "params": {"value": {"$ref": "load#/result/a~1b/0/~0key"}}},
            {"name": "report", "method": "report", "params": {}},
        ]}
        result = run_workflow(plan, execute=execute)
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_step"], "run")
        self.assertEqual(calls[1]["params"]["value"], 42)
        self.assertEqual(len(calls), 2)
        plan["steps"][1]["params"]["value"] = {"$ref": "future#/result"}
        result = run_workflow(plan, execute=lambda *_: {"ok": True})
        self.assertEqual(result["steps"]["run"]["error_code"], "SPIKE-HEADLESS-REFERENCE")
        plan["steps"][1]["name"] = "load"
        with self.assertRaises(ValueError):
            run_workflow(plan, execute=execute)

    def test_document_and_mcp_structured_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text('{"method":"test","params":{"value":NaN}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_document(path)
        server = McpServer(SpikeAutomation(lambda _: {"ok": False, "error": "stale", "error_code": "STALE"}))
        result = server.call_tool("spike_read_project", {"path": "saved.spike"})
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["error_code"], "STALE")
        server = McpServer(SpikeAutomation(lambda req: {"ok": True, "result": req}))
        result = server.call_tool("spike_prepare_multiboard_study", {"request": {"domain": "thermal"}})
        self.assertEqual(result["structuredContent"]["method"], "prepare_multiboard_study")


if __name__ == "__main__":
    unittest.main()
