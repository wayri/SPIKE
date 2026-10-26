# SPDX-License-Identifier: Apache-2.0
"""Public offline example persistence and failure behavior."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/multiport_deembedding/run_fixture.py"


class MultiportWorkflowTests(unittest.TestCase):
    def test_demo_recovery_and_overwrite_protection(self):
        parent = ROOT / "build" / "si08-multiport-tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            path = Path(directory) / "result.json"
            command = [sys.executable, "-B", str(EXAMPLE), "--output", str(path)]
            run = subprocess.run(command, capture_output=True, text=True, timeout=45)
            self.assertEqual(run.returncode, 0, run.stderr)
            raw = path.read_bytes()
            result = json.loads(raw)
            expected = [[.1, .2, -.1], [.05, .15, .3], [.2, -.05, .1]]
            for sample in result["derived_network"]["s_parameters"]:
                for row, reference in zip(sample, expected):
                    for actual, value in zip(row, reference):
                        self.assertAlmostEqual(actual["real"], value, places=13)
                        self.assertEqual(actual["imag"], 0.)
            self.assertFalse(result["production_qualified"])
            retry = subprocess.run(command, capture_output=True, text=True, timeout=45)
            self.assertNotEqual(retry.returncode, 0)
            self.assertEqual(path.read_bytes(), raw)

    def test_invalid_supplied_request_creates_no_result(self):
        parent = ROOT / "build" / "si08-multiport-tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            source = Path(directory) / "request.json"
            output = Path(directory) / "result.json"
            source.write_text('{"contract": "unsupported"}', encoding="utf-8")
            before = source.read_bytes()
            run = subprocess.run([sys.executable, "-B", str(EXAMPLE), "--request", str(source),
                                  "--output", str(output)], capture_output=True, text=True, timeout=45)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), before)
