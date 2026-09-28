# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from python.spike_core.circuit_worker_supervisor import (
    _regular_identity,
    sha256_file,
    supervise_process,
    run_circuit_worker,
)


# A venv's ``sys.executable`` is a launcher which starts the base interpreter.
# The supervisor intentionally permits one active process in its Job Object, so
# that launcher cannot be used as the long-running child in lifecycle tests.
# The packaged worker is itself the admitted process; use the corresponding
# base interpreter here to exercise timeout/cancellation deterministically.
TEST_INTERPRETER = Path(getattr(sys, "_base_executable", sys.executable)).resolve(strict=True)


class CircuitWorkerSupervisorTests(unittest.TestCase):
    def test_sha256_admission_rejects_tampering_and_wrong_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected_name = (
                "spike-circuit-worker.exe" if os.name == "nt" else "spike-circuit-worker"
            )
            worker = root / expected_name
            worker.write_bytes(b"admitted worker bytes")
            digest = hashlib.sha256(worker.read_bytes()).hexdigest()
            self.assertEqual(_regular_identity(worker, expected_name, digest), worker)
            worker.write_bytes(b"tampered worker bytes")
            with self.assertRaisesRegex(ValueError, "SHA-256 admission failed"):
                _regular_identity(worker, expected_name, digest)
            with self.assertRaisesRegex(ValueError, "untrusted"):
                _regular_identity(worker, "different-name", sha256_file(worker))

    def test_timeout_terminates_the_os_container(self):
        outcome = supervise_process(
            TEST_INTERPRETER, ["-c", "import time; time.sleep(30)"],
            cwd=Path.cwd().resolve(strict=True), timeout_seconds=0.15,
            memory_limit_mib=256,
        )
        self.assertEqual(outcome.status, "timeout")
        self.assertLess(outcome.elapsed_seconds, 5.0)
        self.assertIn(outcome.os_enforcement, {
            "windows_job_object", "posix_process_group_rlimit",
        })

    def test_cancellation_terminates_the_os_container(self):
        stop = threading.Event()
        timer = threading.Timer(0.1, stop.set)
        timer.start()
        try:
            outcome = supervise_process(
                TEST_INTERPRETER,
                ["-c", "import time; time.sleep(30)"],
                cwd=Path.cwd().resolve(strict=True), timeout_seconds=10,
                memory_limit_mib=256, cancelled=stop.is_set,
            )
        finally:
            timer.cancel()
        self.assertEqual(outcome.status, "cancelled")
        self.assertLess(outcome.elapsed_seconds, 5.0)

    def test_memory_budget_prevents_large_allocation(self):
        outcome = supervise_process(
            TEST_INTERPRETER,
            ["-c", "x=bytearray(256*1024*1024); print(len(x))"],
            cwd=Path.cwd().resolve(strict=True), timeout_seconds=10,
            memory_limit_mib=64,
        )
        self.assertNotEqual(outcome.returncode, 0)

    def test_resource_budgets_fail_closed(self):
        for timeout, memory in ((0, 256), (1, 15), (86_401, 256)):
            with self.subTest(timeout=timeout, memory=memory):
                with self.assertRaises(ValueError):
                    supervise_process(
                        TEST_INTERPRETER, ["-c", "pass"], cwd=Path.cwd().resolve(strict=True),
                        timeout_seconds=timeout, memory_limit_mib=memory,
                    )

    def test_packaged_worker_runs_under_supervisor_when_present(self):
        root = Path(__file__).resolve().parents[2]
        artifact = root / "app" / "src-tauri" / "resources" / "worker" / "spike-circuit-worker"
        executable = artifact / (
            "spike-circuit-worker.exe" if os.name == "nt" else "spike-circuit-worker"
        )
        library = artifact / "_internal" / "spikes" / (
            "spikes_c_api.dll" if os.name == "nt" else "libspikes_c_api.so"
        )
        if not executable.is_file() or not library.is_file():
            self.skipTest("packaged circuit worker is not present")
        from scripts.build_packaged_circuit_worker import _smoke_job

        with tempfile.TemporaryDirectory() as directory:
            job_root = Path(directory).resolve(strict=True)
            job = job_root / "job"
            job.mkdir()
            (job / "request.json").write_text(
                json.dumps(_smoke_job(), sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            outcome = run_circuit_worker(
                worker_executable=executable.resolve(strict=True),
                worker_sha256=sha256_file(executable),
                library_path=library.resolve(strict=True),
                library_sha256=sha256_file(library),
                job_root=job_root, request="job/request.json", result="job/result.json",
                timeout_seconds=30, memory_limit_mib=256,
            )
            self.assertEqual(outcome.status, "completed")
            self.assertEqual(outcome.returncode, 0)
            result = json.loads((job / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "completed")


if __name__ == "__main__":
    unittest.main()
