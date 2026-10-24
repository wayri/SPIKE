# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""A stale catalog or omitted new schema cannot pass worker qualification."""
from pathlib import Path
import tempfile
import unittest

from scripts.verify_packaged_schema_catalog import verify_packaged_schema_catalog


class PackagedSchemaCoherenceTests(unittest.TestCase):
    def test_current_bytes_and_missing_changed_extra_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"; source.mkdir()
            package = base / "worker/_internal/schemas"; package.mkdir(parents=True)
            for folder in (source, package):
                (folder / "manifest.json").write_bytes(b'{"schemas":{}}\n')
            exe = base / "worker/spike-worker.exe"
            self.assertEqual(verify_packaged_schema_catalog(exe, source)["json_files"], 1)
            (source / "new.json").write_bytes(b'{}')
            with self.assertRaisesRegex(RuntimeError, "missing=.*new.json"):
                verify_packaged_schema_catalog(exe, source)
            (package / "new.json").write_bytes(b'{}')
            self.assertEqual(verify_packaged_schema_catalog(exe, source)["json_files"], 2)
            (package / "manifest.json").write_bytes(b'{}')
            with self.assertRaisesRegex(RuntimeError, "changed=.*manifest.json"):
                verify_packaged_schema_catalog(exe, source)
            (package / "manifest.json").write_bytes((source / "manifest.json").read_bytes())
            (package / "extra.json").write_bytes(b'{}')
            with self.assertRaisesRegex(RuntimeError, "extra=.*extra.json"):
                verify_packaged_schema_catalog(exe, source)
