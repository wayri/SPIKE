# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from python.spikes.release_verifier import (
    ReleaseVerificationError,
    verify_engine_release,
)


class SpikesReleaseVerifierTests(unittest.TestCase):
    def test_current_coherent_bundle_passes_offline_staging_smoke(self) -> None:
        version = "unit-fixture"
        package_name = f"SPIKES-{version}-windows-x64-engineering-preview"
        payload = b"self-contained verifier fixture\n"
        manifest = {
            "contract": "spikes/engine-release-manifest/v1",
            "version": version,
            "files": [{
                "path": "payload.txt", "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }],
            "claims": {name: False for name in (
                "complete_spice3_parity", "competitive_superiority", "hard_realtime",
                "physical_hil", "hostile_code_safe", "production_signed",
            )},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(f"{package_name}/payload.txt", payload)
                bundle.writestr(
                    f"{package_name}/release.manifest.json",
                    json.dumps(manifest).encode("utf-8"),
                )
            report_payload = {
                **manifest,
                "archive": {
                    "path": archive.name,
                    "size": archive.stat().st_size,
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                },
            }
            report = root / "release.json"
            report.write_text(json.dumps(report_payload), encoding="utf-8")
            result = verify_engine_release(report, launch_smoke=False)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["cli_launch_smoke"], "skipped")
        self.assertEqual(result["cli_functional_smoke"], "skipped")
        self.assertEqual(result["native_console_version_smoke"], "not_present")
        self.assertEqual(result["uninstall"], "passed")
        self.assertFalse(result["production_qualified"])

    def test_archive_traversal_is_rejected_before_extraction(self) -> None:
        # This security unit test must reach traversal admission independently
        # of the separately required real release artifact above.
        source = {"contract": "spikes/engine-release-manifest/v1", "version": "original-unit-fixture",
                  "files": [{"path": "payload.txt", "size": 0, "sha256": "0" * 64}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape", b"bad")
            source["archive"] = {
                "path": archive.name, "size": archive.stat().st_size,
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
            report = root / "report.json"
            report.write_text(json.dumps(source), encoding="utf-8")
            with patch.object(zipfile.ZipFile, "extractall", side_effect=AssertionError("Extraction must not occur")) as extract:
                with self.assertRaisesRegex(ReleaseVerificationError, "unsafe archive member"):
                    verify_engine_release(report, launch_smoke=False)
                extract.assert_not_called()


if __name__ == "__main__":
    unittest.main()
