"""Source-level parity tests for the packaged worker CLI entry point."""

from __future__ import annotations

import json
import contextlib
import subprocess
import sys
import tempfile
import types
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import spike_worker_entry
from scripts import verify_packaged_cli


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "scripts" / "spike_worker_entry.py"


class WorkerCliEntryTests(unittest.TestCase):
    def test_verifier_strips_argument_delimiter_from_launcher_prefix(self) -> None:
        report = {"contract": "spike/packaged-cli-verification/v1", "status": "passed"}
        output = StringIO()
        with patch.object(verify_packaged_cli, "verify", return_value=report) as verify_call, \
                contextlib.redirect_stdout(output):
            code = verify_packaged_cli.main(["--", "flatpak", "run", "org.spike.integrity"])
        self.assertEqual(code, 0)
        verify_call.assert_called_once_with(["flatpak", "run", "org.spike.integrity"])
        self.assertEqual(json.loads(output.getvalue()), report)

    def test_dispatch_forwards_cli_arguments_and_preserves_default_service(self) -> None:
        cli_module = types.ModuleType("python.spike_cli")
        cli_calls: list[list[str]] = []
        cli_module.main = lambda arguments: cli_calls.append(arguments) or 7
        with patch.dict(sys.modules, {"python.spike_cli": cli_module}):
            self.assertEqual(
                spike_worker_entry.main(["--cli", "--compact", "inspect", "board.json"]),
                7,
            )
        self.assertEqual(cli_calls, [["--compact", "inspect", "board.json"]])

        service_module = types.ModuleType("python.spike_core.service")
        service_calls: list[bool] = []
        service_module.main = lambda: service_calls.append(True) or 0
        with patch.dict(sys.modules, {"python.spike_core.service": service_module}):
            self.assertEqual(spike_worker_entry.main([]), 0)
        self.assertEqual(service_calls, [True])

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ENTRYPOINT), "--cli", *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_help_and_version_use_cli_streams_and_exit_codes(self) -> None:
        help_result = self.invoke("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("SPIKE local-first PI/SI automation CLI", help_result.stdout)
        self.assertEqual(help_result.stderr, "")

        version_result = self.invoke("--version")
        self.assertEqual(version_result.returncode, 0, version_result.stderr)
        self.assertRegex(
            version_result.stdout.strip(),
            r"^SPIKE CLI (?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
            r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
            r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
            r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$",
        )
        self.assertEqual(version_result.stderr, "")

    def test_inspect_forwards_the_complete_cli_argument_vector(self) -> None:
        design = {
            "contract": "spike/v1",
            "design_id": "packaged-cli-fixture",
            "name": "packaged CLI fixture",
            "source_format": "fixture",
            "source_path": "fixture.json",
            "units": "mm",
            "layers": [{"name": "F.Cu"}],
            "nets": [{"id": 1, "name": "VCC"}],
            "tracks": [{
                "start": [0, 0], "end": [10, 0], "width": 1,
                "layer": "F.Cu", "net_name": "VCC",
            }],
            "vias": [],
            "pads": [],
            "zones": [],
            "components": [],
            "stackup": [{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
            "metadata": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            design_path = Path(directory) / "fixture.json"
            design_path.write_text(json.dumps(design), encoding="utf-8")
            result = self.invoke("--compact", "inspect", str(design_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        inspected = json.loads(result.stdout)
        self.assertEqual(inspected["counts"]["tracks"], 1)
        self.assertEqual(inspected["counts"]["nets"], 1)
        self.assertNotIn("\n  ", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_operational_failure_remains_structured_json(self) -> None:
        missing = ROOT / "tests" / "fixtures" / "missing-packaged-cli-input.json"
        result = self.invoke("inspect", str(missing))

        self.assertNotEqual(result.returncode, 0)
        error = json.loads(result.stdout)
        self.assertFalse(error["ok"])
        self.assertIsInstance(error["type"], str)
        self.assertTrue(error["type"])
        self.assertIn(str(missing), error["error"])
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
