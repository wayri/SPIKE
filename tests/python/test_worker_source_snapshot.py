# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
from hashlib import sha256
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import capture_worker_source_snapshot as snapshots


class WorkerSourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.destination = self.root / "build" / "source-snapshot"
        self.executable = self.root / "artifact" / "worker.bin"
        self.executable.parent.mkdir()
        self.executable.write_bytes(b"not executed: original byte identity fixture")
        self.modules = {}
        for name in sorted(snapshots.EM_COSIM_MODULES | {"python.fixture"}):
            path = self.root.joinpath(*name.split(".")).with_suffix(".py")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("VALUE = 7\n", encoding="utf-8")
            self.modules[name] = compile("VALUE = 7\n", "relocated.py", "exec")
        for base in (self.root / "schemas", self.executable.parent / "_internal" / "schemas"):
            base.mkdir(parents=True)
            (base / "manifest.json").write_bytes(b"{}\n")

    def capture(self, destination=None):
        archive = SimpleNamespace(toc=self.modules, extract=lambda name: self.modules[name])
        reader = SimpleNamespace(open_embedded_archive=lambda name: archive)
        with patch.object(snapshots, "CArchiveReader", return_value=reader):
            return snapshots.capture(self.executable, destination or self.destination, source_root=self.root)

    def test_copied_bytes_and_hashes_are_bound_to_frozen_identity(self):
        result = self.capture()
        self.assertEqual(result["checked_modules"], len(self.modules))
        self.assertEqual(result["schema_json_files"], 1)
        self.assertEqual(result["executable_sha256"], sha256(self.executable.read_bytes()).hexdigest())
        for item in result["files"]:
            self.assertEqual(sha256((self.destination / item["path"]).read_bytes()).hexdigest(), item["sha256"])
        # An active-tree edit cannot silently change the retained baseline.
        (self.root / "python" / "fixture.py").write_text("VALUE = 8\n", encoding="utf-8")
        self.assertEqual((self.destination / "python" / "fixture.py").read_text(), "VALUE = 7\n")
        with self.assertRaises(ValueError):
            self.capture()

    def test_mismatch_or_missing_owner_does_not_publish_snapshot(self):
        (self.root / "python" / "fixture.py").write_text("VALUE = 8\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.capture()
        self.assertFalse(self.destination.exists())
        self.modules = {"python.fixture": compile("VALUE = 8\n", "x", "exec")}
        with self.assertRaisesRegex(ValueError, "Required"):
            self.capture()
        self.assertFalse(self.destination.exists())

    def test_schema_drift_and_outside_root_and_budgets_fail(self):
        for target in (self.root, self.root / "build", self.root / "outside"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.capture(target)
        with patch.object(snapshots, "MAX_FILE_BYTES", 1), self.assertRaisesRegex(ValueError, "budget"):
            self.capture()
        (self.root / "schemas" / "manifest.json").write_bytes(b'{"changed":true}\n')
        with self.assertRaisesRegex(ValueError, "Schema bytes"):
            self.capture()
        self.assertFalse(self.destination.exists())

    def test_packaged_schema_mutation_during_capture_is_rejected(self):
        packaged = self.executable.parent / "_internal" / "schemas"
        (self.root / "schemas" / "a.json").write_bytes(b"{}\n")
        (packaged / "a.json").write_bytes(b"{}\n")
        original_read = snapshots._read_source
        for action in ("change", "add"):
            with self.subTest(action=action):
                (packaged / "a.json").write_bytes(b"{}\n")
                extra = packaged / "extra.json"
                if extra.exists():
                    extra.unlink()
                def mutate(path, remaining):
                    data = original_read(path, remaining)
                    if path == self.root / "schemas" / "manifest.json":
                        (packaged / ("a.json" if action == "change" else "extra.json")).write_bytes(b'{"changed":true}\n')
                    return data
                with patch.object(snapshots, "_read_source", side_effect=mutate):
                    with self.assertRaisesRegex(ValueError, "changed during"):
                        self.capture()
                self.assertFalse(self.destination.exists())

    def test_escaping_build_root_is_rejected_without_creating_output(self):
        # Deterministically simulate resolved junction behavior without requiring
        # Windows symlink privileges on the test machine.
        original_resolve = Path.resolve
        outside = self.root.parent / (self.root.name + "-outside")
        def resolve(path, *args, **kwargs):
            if path == self.root / "build":
                return outside
            if path == self.destination:
                return outside / "source-snapshot"
            return original_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", resolve):
            with self.assertRaisesRegex(ValueError, "strictly below"):
                self.capture()
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
