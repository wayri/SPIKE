import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.sparselizard_runtime import detect_sparselizard_runtime


class SparseLizardRuntimeTests(unittest.TestCase):
    def test_accepts_integrity_bound_passing_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "bin" / "spike-sparselizard-runtime.exe"
            binary.parent.mkdir()
            binary.write_bytes(b"native-runtime")
            (root / "self-test.json").write_text(json.dumps({
                "contract": "spike/sparselizard-runtime-self-test/v1",
                "status": "passed",
                "validation_scope": "native-dc-fem-runtime-only",
            }), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({
                "contract": "spike/sparselizard-native-runtime/v1",
                "executable": "bin/spike-sparselizard-runtime.exe",
                "executable_sha256": hashlib.sha256(b"native-runtime").hexdigest(),
                "self_test": {"path": "self-test.json"},
                "backend": {"mumps_registered": False},
            }), encoding="utf-8")
            with patch.dict("os.environ", {"SPIKE_SPARSELIZARD_RUNTIME": str(root)}):
                detected = detect_sparselizard_runtime()
            self.assertTrue(detected["available"])
            self.assertEqual(detected["self_test"]["validation_scope"], "native-dc-fem-runtime-only")

    def test_rejects_binary_digest_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "bin" / "spike-sparselizard-runtime.exe"
            binary.parent.mkdir()
            binary.write_bytes(b"tampered")
            (root / "self-test.json").write_text(json.dumps({
                "contract": "spike/sparselizard-runtime-self-test/v1", "status": "passed",
            }), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({
                "contract": "spike/sparselizard-native-runtime/v1",
                "executable": "bin/spike-sparselizard-runtime.exe",
                "executable_sha256": "0" * 64,
                "self_test": {"path": "self-test.json"},
            }), encoding="utf-8")
            with patch.dict("os.environ", {"SPIKE_SPARSELIZARD_RUNTIME": str(root)}):
                detected = detect_sparselizard_runtime()
            self.assertFalse(detected["available"])


if __name__ == "__main__":
    unittest.main()
