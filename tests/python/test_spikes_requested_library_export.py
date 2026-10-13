# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "requested_library_export", ROOT / "scripts/build_spikes_requested_library.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExportTests(unittest.TestCase):
    def test_snapshot_hashes_and_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "library"
            manifest = MODULE.build(path)
            self.assertFalse(manifest["complete_requested_portfolio"])
            self.assertEqual(manifest["manufacturer_models_runnable"], 0)
            self.assertEqual(manifest["compiled_generic_models"], 2)
            for item in manifest["files"]:
                data = (path / item["path"]).read_bytes()
                self.assertEqual(len(data), item["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
            controllers = list((path / "controllers").glob("*.json"))
            self.assertEqual(len(controllers), 2)
            for controller in controllers:
                config = json.loads(controller.read_text())
                self.assertEqual(config["language"], "C++")
                self.assertIn("control_step", config["source"])
            with self.assertRaises(FileExistsError):
                MODULE.build(path)


if __name__ == "__main__":
    unittest.main()
