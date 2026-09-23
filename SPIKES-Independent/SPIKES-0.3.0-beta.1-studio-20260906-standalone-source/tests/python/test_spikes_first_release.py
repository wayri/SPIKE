import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from python.spikes.first_release import verify_portable_archive, verify_portable_tree


class FirstReleaseTests(unittest.TestCase):
    def test_portable_tree_is_inventory_and_digest_bound(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "worker.exe"
            payload.write_bytes(b"worker")
            manifest = {
                "contract": "spike/portable-manifest/v1",
                "product": "SPIKE", "version": "0.2.0", "architecture": "x64",
                "files": [{
                    "path": "worker.exe", "size": 6,
                    "sha256": hashlib.sha256(b"worker").hexdigest(),
                }],
            }
            (root / "portable.manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            self.assertEqual(verify_portable_tree(root)["status"], "passed")
            payload.write_bytes(b"tamper")
            report = verify_portable_tree(root)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failures"][0]["reason"], "sha256_mismatch")

    def test_portable_tree_rejects_traversal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "portable.manifest.json").write_text(json.dumps({
                "contract": "spike/portable-manifest/v1",
                "files": [{"path": "../escape", "size": 0, "sha256": "0" * 64}],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_portable_tree(root)

    def test_portable_archive_is_independently_manifest_bound(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "portable.zip"
            payload = b"worker"
            manifest = {
                "contract": "spike/portable-manifest/v1",
                "version": "0.2.0", "architecture": "x64",
                "files": [{
                    "path": "worker.exe", "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }],
            }
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("SPIKE/worker.exe", payload)
                bundle.writestr("SPIKE/portable.manifest.json", json.dumps(manifest))
            self.assertEqual(verify_portable_archive(archive)["status"], "passed")
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("SPIKE/worker.exe", b"tamper")
                bundle.writestr("SPIKE/portable.manifest.json", json.dumps(manifest))
            self.assertEqual(verify_portable_archive(archive)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
