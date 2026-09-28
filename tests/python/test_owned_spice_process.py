# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core.owned_spice_process import (
    JOB_CONTRACT,
    MAX_CIRCUIT_RESULT_BYTES,
    PROCESS_RESULT_CONTRACT,
    capability_manifest,
    main,
)
from tests.python.test_native_circuit_compiler import design, workspace
from tests.python.test_owned_spice_workspace import request as circuit_request


class OwnedSpiceProcessTests(unittest.TestCase):
    def _run_from_parent(self, parent, request_path, result_path):
        previous = Path.cwd()
        try:
            os.chdir(parent)
            return main([
                "--request", str(request_path.relative_to(parent)),
                "--result", str(result_path.relative_to(parent)),
            ])
        finally:
            os.chdir(previous)

    def test_capability_is_narrow_and_experimental(self):
        manifest = capability_manifest()
        self.assertEqual(manifest["engine"], "spike-circuit-worker")
        self.assertEqual(manifest["validation_state"], "experimental")
        self.assertFalse(manifest["raw_netlist_accepted"])
        self.assertFalse(manifest["caller_selected_library"])
        self.assertTrue(manifest["owned_engine"]["available"])
        self.assertEqual(len(manifest["owned_engine"]["library_sha256"]), 64)

    def test_dedicated_packaging_entry_exposes_only_the_circuit_capability(self):
        from scripts.build_packaged_circuit_worker import _smoke_job

        root = Path(__file__).resolve().parents[2]
        entry = root / "scripts" / "spike_circuit_worker_entry.py"
        process = subprocess.run(
            [sys.executable, str(entry), "--capabilities"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        manifest = json.loads(process.stdout)
        self.assertEqual(manifest["contract"], "spike/owned-spice-process-capability/v1")
        self.assertEqual(manifest["engine"], "spike-circuit-worker")
        self.assertNotIn("methods", manifest)

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            job = parent / "job"
            job.mkdir()
            (job / "request.json").write_text(
                json.dumps(_smoke_job()), encoding="utf-8",
            )
            solved = subprocess.run(
                [sys.executable, str(entry), "--request", "job/request.json",
                 "--result", "job/result.json"],
                cwd=parent,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(solved.returncode, 0, solved.stderr)
            result = json.loads((job / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "completed")

    def test_job_executes_and_publishes_one_atomic_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "request.json"
            result_path = root / "result.json"
            request_path.write_text(json.dumps({
                "contract": JOB_CONTRACT,
                "design": design().to_dict(),
                "circuit_request": circuit_request(resource_limits={
                    "maximum_netlist_bytes": 2 * 1024 * 1024,
                    "maximum_result_bytes": MAX_CIRCUIT_RESULT_BYTES,
                    "maximum_probes": 16,
                }),
            }), encoding="utf-8")
            code = self._run_from_parent(root.parent, request_path, result_path)
            self.assertEqual(code, 0)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["contract"], PROCESS_RESULT_CONTRACT)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["circuit"]["circuit_result"]["contract"], "spikes/circuit-result/v1")
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_duplicate_json_and_mismatched_job_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            request_path = Path(left) / "request.json"
            result_path = Path(left) / "result.json"
            request_path.write_text('{"contract":"x","contract":"y"}', encoding="utf-8")
            self.assertEqual(self._run_from_parent(Path(left).parent, request_path, result_path), 2)
            self.assertEqual(json.loads(result_path.read_text(encoding="utf-8"))["status"], "failed")

            other_result = Path(right) / "result.json"
            self.assertEqual(
                main(["--request", str(request_path), "--result", str(other_result)]), 2,
            )
            self.assertFalse(other_result.exists())

    def test_absolute_traversal_and_reparse_controls_fail_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job"
            job.mkdir()
            request_path = job / "request.json"
            request_path.write_text("{}", encoding="utf-8")
            result_path = job / "result.json"
            self.assertEqual(main([
                "--request", str(request_path), "--result", str(result_path),
            ]), 2)
            self.assertFalse(result_path.exists())

            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main([
                    "--request", "job/../job/request.json",
                    "--result", "job/result.json",
                ]), 2)
                with patch(
                    "python.spike_core.owned_spice_process._has_reparse_point",
                    side_effect=lambda path: path == job,
                ):
                    self.assertEqual(main([
                        "--request", "job/request.json", "--result", "job/result.json",
                    ]), 2)
            finally:
                os.chdir(previous)
            self.assertFalse(result_path.exists())

    def test_inner_result_budget_cannot_exceed_process_envelope_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job"
            job.mkdir()
            request_path = job / "request.json"
            result_path = job / "result.json"
            request_path.write_text(json.dumps({
                "contract": JOB_CONTRACT,
                "design": design().to_dict(),
                "circuit_request": circuit_request(),
            }), encoding="utf-8")
            self.assertEqual(self._run_from_parent(root, request_path, result_path), 2)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "failed")
            self.assertIn("4 MiB", result["issues"][0]["message"])


if __name__ == "__main__":
    unittest.main()
