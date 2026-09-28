# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

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
        source = json.loads(REPORT.read_text(encoding="utf-8"))
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
            with self.assertRaises(ReleaseVerificationError):
                verify_engine_release(report, launch_smoke=False)


if __name__ == "__main__":
    unittest.main()
