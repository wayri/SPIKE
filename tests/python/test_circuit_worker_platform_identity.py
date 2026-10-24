# SPDX-License-Identifier: Apache-2.0
"""Platform library identity admission without launching a native solver."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core import circuit_worker_supervisor as supervisor


class CircuitWorkerPlatformIdentityTests(unittest.TestCase):
    def test_each_platform_admits_only_its_release_library_name(self):
        names = {
            "win32": "spikes_c_api.dll",
            "linux": "libspikes_c_api.so",
            "darwin": "libspikes_c_api.dylib",
        }
        with tempfile.TemporaryDirectory(prefix="spike-circuit-platform-") as temporary:
            root = Path(temporary).resolve(strict=True)
            worker = root / ("spike-circuit-worker.exe" if os.name == "nt" else "spike-circuit-worker")
            worker.write_bytes(b"original executable fixture")
            job = root / "job"
            job.mkdir()
            (job / "request.json").write_text(json.dumps({"fixture": True}), encoding="utf-8")
            libraries = {}
            for name in names.values():
                library = root / name
                library.write_bytes(b"original library identity fixture")
                libraries[name] = library
            for platform, expected_name in names.items():
                for candidate_name, library in libraries.items():
                    with self.subTest(platform=platform, candidate=candidate_name), patch(
                            "python.spike_core.spikes_runtime.sys.platform", platform), patch.object(
                            supervisor, "supervise_process", return_value=supervisor.SupervisionResult(
                                "completed", 0, 0., "test-only")) as launch:
                        arguments = dict(
                            worker_executable=worker, worker_sha256=supervisor.sha256_file(worker),
                            library_path=library, library_sha256=supervisor.sha256_file(library),
                            job_root=root, request="job/request.json", result="job/result.json",
                        )
                        if candidate_name == expected_name:
                            outcome = supervisor.run_circuit_worker(**arguments)
                            self.assertEqual(outcome.status, "completed")
                            launch.assert_called_once()
                            self.assertEqual(launch.call_args.args[0], worker)
                            self.assertEqual(launch.call_args.args[1], [
                                "--request", "job/request.json", "--result", "job/result.json"])
                        else:
                            with self.assertRaisesRegex(ValueError, "untrusted"):
                                supervisor.run_circuit_worker(**arguments)
                            launch.assert_not_called()

    def test_darwin_correct_name_does_not_bypass_library_digest(self):
        with tempfile.TemporaryDirectory(prefix="spike-circuit-digest-") as temporary:
            root = Path(temporary).resolve(strict=True)
            worker = root / ("spike-circuit-worker.exe" if os.name == "nt" else "spike-circuit-worker")
            worker.write_bytes(b"original executable fixture")
            library = root / "libspikes_c_api.dylib"
            library.write_bytes(b"original library fixture")
            digest = supervisor.sha256_file(library)
            library.write_bytes(b"tampered library fixture")
            with patch("python.spike_core.spikes_runtime.sys.platform", "darwin"), patch.object(
                    supervisor, "supervise_process") as launch:
                with self.assertRaisesRegex(ValueError, "SHA-256 admission failed"):
                    supervisor.run_circuit_worker(
                        worker_executable=worker, worker_sha256=supervisor.sha256_file(worker),
                        library_path=library, library_sha256=digest, job_root=root,
                        request="job/request.json", result="job/result.json")
                launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
