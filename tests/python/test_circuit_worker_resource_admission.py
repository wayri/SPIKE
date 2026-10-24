# SPDX-License-Identifier: Apache-2.0
"""Fail-closed POSIX initialization reporting without executing a solver."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from python.spike_core import circuit_worker_supervisor as supervisor


class CircuitWorkerResourceAdmissionTests(unittest.TestCase):
    def _fixture(self, root):
        worker = root / "spike-circuit-worker"
        library = root / "libspikes_c_api.dylib"
        worker.write_bytes(b"admitted executable fixture")
        library.write_bytes(b"admitted library fixture")
        (root / "job").mkdir()
        (root / "job" / "request.json").write_text("{}", encoding="utf-8")
        return dict(worker_executable=worker, worker_sha256=supervisor.sha256_file(worker),
                    library_path=library, library_sha256=supervisor.sha256_file(library),
                    job_root=root, request="job/request.json", result="job/result.json",
                    timeout_seconds=30, memory_limit_mib=4096)

    def test_popen_failure_is_chained_and_never_retried(self):
        original = subprocess.SubprocessError("Exception occurred in preexec_fn.")
        with patch.dict(sys.modules, {"resource": SimpleNamespace()}), \
                patch.object(supervisor.sys, "platform", "darwin"), \
                patch.object(supervisor.subprocess, "Popen", side_effect=original) as launch, \
                patch.object(supervisor, "_terminate_posix_group") as cleanup:
            with self.assertRaises(supervisor.SupervisorInitializationError) as caught:
                supervisor._supervise_posix(Path(sys.executable), [], Path.cwd(),
                                           30, 4096, lambda: False)
        self.assertIs(caught.exception.__cause__, original)
        self.assertEqual((caught.exception.platform, caught.exception.timeout_seconds,
                          caught.exception.memory_limit_mib), ("darwin", 30, 4096))
        self.assertNotIn("RLIMIT_AS", str(caught.exception))
        self.assertNotIn("RLIMIT_CORE", str(caught.exception))
        launch.assert_called_once()
        self.assertTrue(callable(launch.call_args.kwargs["preexec_fn"]))
        self.assertTrue(launch.call_args.kwargs["start_new_session"])
        cleanup.assert_not_called()

    def test_other_launch_errors_are_not_misreported_as_initialization_failure(self):
        original = FileNotFoundError("missing executable")
        with patch.dict(sys.modules, {"resource": SimpleNamespace()}), \
                patch.object(supervisor.subprocess, "Popen", side_effect=original) as launch:
            with self.assertRaises(FileNotFoundError) as caught:
                supervisor._supervise_posix(Path(sys.executable), [], Path.cwd(),
                                           30, 4096, lambda: False)
        self.assertIs(caught.exception, original)
        launch.assert_called_once()

    def test_admitted_failure_atomically_publishes_truthful_terminal_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            arguments = self._fixture(root)
            original = subprocess.SubprocessError("hidden internal detail /private/path")
            with patch.object(supervisor, "os", SimpleNamespace(name="posix")), \
                    patch.object(supervisor.sys, "platform", "darwin"), \
                    patch.dict(sys.modules, {"resource": SimpleNamespace()}), \
                    patch.object(supervisor.subprocess, "Popen", side_effect=original) as launch, \
                    patch.object(supervisor, "_atomic_publish", wraps=supervisor._atomic_publish) as publish:
                with self.assertRaises(supervisor.SupervisorInitializationError) as caught:
                    supervisor.run_circuit_worker(**arguments)
                self.assertIs(caught.exception.__cause__, original)
                launch.assert_called_once()
                publish.assert_called_once()
            value = json.loads((root / "job/result.json").read_text(encoding="utf-8"))
            self.assertEqual(value["contract"], supervisor.PROCESS_RESULT_CONTRACT)
            self.assertEqual(value["status"], "failed")
            self.assertEqual(value["validation_state"], "experimental")
            self.assertIsNone(value["circuit"])
            self.assertEqual(value["issues"][0]["code"], "SPIKE-BE-SPICE-E-0057")
            self.assertEqual(value["provenance"], {
                "supervisor": "python.spike_core.circuit_worker_supervisor",
                "supervisor_initialization_failed": True,
                "enforcement_established": False,
                "complete_process_tree_termination_requested": False,
                "platform": "darwin", "requested_timeout_seconds": 30,
                "requested_memory_limit_mib": 4096,
            })
            self.assertNotIn("/private/path", json.dumps(value))
            self.assertNotIn("errno", json.dumps(value))
            self.assertEqual(list((root / "job").glob(".*.tmp")), [])

    def test_invalid_identity_paths_and_budgets_do_not_launch_or_mutate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            arguments = self._fixture(root)
            result = root / "job/result.json"
            result.write_bytes(b"previous result must remain unchanged")
            before = {str(path.relative_to(root)): path.read_bytes()
                      for path in root.rglob("*") if path.is_file()}
            invalid = [
                {"worker_sha256": "0" * 64}, {"library_sha256": "0" * 64},
                {"request": "../request.json"},
                {"request": "missing/request.json", "result": "missing/result.json"},
                {"result": "other/result.json"}, {"timeout_seconds": 0},
                {"timeout_seconds": float("nan")}, {"timeout_seconds": float("inf")},
                {"memory_limit_mib": 15}, {"memory_limit_mib": True},
            ]
            with patch.object(supervisor, "os", SimpleNamespace(name="posix")), \
                    patch.object(supervisor.sys, "platform", "darwin"), \
                    patch.object(supervisor, "_supervise_posix") as attempt, \
                    patch.object(supervisor, "_atomic_publish") as publish:
                for change in invalid:
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        supervisor.run_circuit_worker(**(arguments | change))
                attempt.assert_not_called()
                publish.assert_not_called()
            after = {str(path.relative_to(root)): path.read_bytes()
                     for path in root.rglob("*") if path.is_file()}
            self.assertEqual(after, before)

    def test_timeout_and_cancellation_reporting_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            arguments = self._fixture(root)
            for status, terminal, code in (("timeout", "failed", "0056"),
                                           ("cancelled", "cancelled", "0055")):
                outcome = supervisor.SupervisionResult(status, -15, 1, "posix_process_group_rlimit")
                with self.subTest(status=status), \
                        patch.object(supervisor, "os", SimpleNamespace(name="posix")), \
                        patch.object(supervisor.sys, "platform", "darwin"), \
                        patch.object(supervisor, "supervise_process", return_value=outcome):
                    self.assertIs(supervisor.run_circuit_worker(**arguments), outcome)
                result = json.loads((root / "job/result.json").read_text(encoding="utf-8"))
                self.assertEqual(result["status"], terminal)
                self.assertEqual(result["issues"][0]["code"], "SPIKE-BE-SPICE-E-" + code)
                self.assertEqual(result["provenance"], {
                    "supervisor": "python.spike_core.circuit_worker_supervisor",
                    "complete_process_tree_termination_requested": True,
                })



@unittest.skipUnless(__import__("os").name == "posix", "native POSIX limit admission required")
class NativeResourceAdmissionTests(unittest.TestCase):
    def test_native_launch_enforces_exact_budget_or_fails_before_worker_starts(self):
        import resource
        program = r"""
import json, mmap, pathlib, resource
cap = 4096 * 1024 * 1024
limits = resource.getrlimit(resource.RLIMIT_AS)
core = resource.getrlimit(resource.RLIMIT_CORE)
with mmap.mmap(-1, 4096) as tiny:
    tiny[0] = 1
blocked = False
try:
    large = mmap.mmap(-1, cap + 1)
except (OSError, MemoryError):
    blocked = True
else:
    large.close()
pathlib.Path("worker-started.json").write_text(json.dumps({"limits":limits,"core":core,"over_budget_blocked":blocked}))
"""
        before = resource.getrlimit(resource.RLIMIT_AS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            marker = root / "worker-started.json"
            executable = Path(getattr(sys, "_base_executable", sys.executable)).resolve(strict=True)
            try:
                result = supervisor.supervise_process(executable, ["-c", program], cwd=root,
                            timeout_seconds=5, memory_limit_mib=4096)
            except supervisor.SupervisorInitializationError as error:
                self.assertEqual(sys.platform, "darwin", "supported Linux admission must succeed")
                self.assertFalse(marker.exists(), "failed admission must never start worker code")
                self.assertIsInstance(error.__cause__, subprocess.SubprocessError)
                self.assertEqual(error.memory_limit_mib, 4096)
            else:
                self.assertEqual((result.status, result.returncode), ("completed", 0))
                value = json.loads(marker.read_text())
                self.assertEqual(value["limits"], [4294967296, 4294967296])
                self.assertEqual(value["core"], [0, 0])
                self.assertTrue(value["over_budget_blocked"])
        self.assertEqual(resource.getrlimit(resource.RLIMIT_AS), before)

if __name__ == "__main__":
    unittest.main()
