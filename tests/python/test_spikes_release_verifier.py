# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

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


ROOT = Path(__file__).resolve().parents[2]
REPORT = (
    ROOT / "artifacts" / "releases" / "beta-0.3.0-beta.1-coherent"
    / "SPIKES-0.3.0-beta.1-release.json"
)


class SpikesReleaseVerifierTests(unittest.TestCase):
    def test_current_coherent_bundle_passes_offline_staging_smoke(self) -> None:
        # The retained beta.1 artifact predates standalone-source admission.
        # Its integrity remains verifiable, but a new package must pass the
        # launch smoke before it can be considered for public distribution.
        result = verify_engine_release(REPORT, launch_smoke=False)
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
            import hashlib
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
