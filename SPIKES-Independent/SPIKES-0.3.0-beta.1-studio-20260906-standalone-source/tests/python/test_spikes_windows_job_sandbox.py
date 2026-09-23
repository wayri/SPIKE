from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from python.spike_core.sparselizard_process import run_adapter_process


@unittest.skipUnless(os.name == "nt", "Windows Job containment test")
class WindowsJobSandboxTests(unittest.TestCase):
    def test_process_is_resumed_only_after_job_assignment(self):
        executable = Path(getattr(sys, "_base_executable", sys.executable))
        with tempfile.TemporaryDirectory(prefix="spikes-job-test-") as directory:
            result = run_adapter_process(
                [str(executable), "-I", "-S", "-c", "print('contained')"],
                cwd=Path(directory), timeout_s=10, memory_limit_mb=256,
                output_limit_bytes=4096, stream_limit_bytes=4096,
            )
        self.assertEqual(result["return_code"], 0)
        self.assertEqual(result["stdout"].strip(), "contained")
        self.assertTrue(result["memory_limit_enforced"])
        self.assertTrue(result["suspended_before_job_assignment"])
        self.assertTrue(result["job_assignment_race_closed"])


if __name__ == "__main__":
    unittest.main()
