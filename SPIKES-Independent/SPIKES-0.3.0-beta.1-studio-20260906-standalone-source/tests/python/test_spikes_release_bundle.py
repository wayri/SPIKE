from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from python.spikes.release_bundle import RELEASE_MANIFEST_CONTRACT, build_engine_release


ROOT = Path(__file__).resolve().parents[2]


class SpikesReleaseBundleTests(unittest.TestCase):
    def test_release_is_manifested_and_fail_closed_about_claims(self) -> None:
        library = ROOT / "build-spikes-bdf2" / "spikes_c_api.dll"
        if not library.is_file():
            self.skipTest("current SPIKES native library is unavailable")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            package, archive, report = build_engine_release(
                root=ROOT, version="0.0.0-test", library=library,
                output_root=directory,
            )
            manifest = json.loads((package / "release.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["contract"], RELEASE_MANIFEST_CONTRACT)
            self.assertFalse(manifest["claims"]["complete_spice3_parity"])
            self.assertFalse(manifest["claims"]["physical_hil"])
            self.assertFalse(manifest["claims"]["production_signed"])
            self.assertGreater(len(manifest["files"]), 20)
            packaged_paths = {item["path"] for item in manifest["files"]}
            self.assertIn("models/bsimbulk-107.2.1-windows-x64.osdi", packaged_paths)
            self.assertIn("models/bsimcmg-112.1.0-windows-x64.osdi", packaged_paths)
            self.assertIn("legal/bsimbulk-107.2.1/LICENSE.txt", packaged_paths)
            self.assertIn("legal/bsimcmg-112.1.0/NOTICE.txt", packaged_paths)
            self.assertIn("docs/PHYSICAL_HIL_CERTIFICATION.md", packaged_paths)
            self.assertTrue(archive.is_file())
            with zipfile.ZipFile(archive) as bundle:
                self.assertIn(
                    f"{package.name}/release.manifest.json", bundle.namelist(),
                )
            self.assertEqual(report["archive"]["sha256"], report["archive"]["sha256"].lower())


if __name__ == "__main__":
    unittest.main()
