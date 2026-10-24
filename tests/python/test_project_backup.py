# SPDX-License-Identifier: Apache-2.0
"""Durable automatic recovery packages, independent of primary save state."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.project_package import read_project, write_spike_package
from tests.python import test_assembly_designs as fixture


class ProjectBackupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "recovery"
        self.session = uuid.uuid4().hex
        design, _, assembly, designs = fixture.AssemblyDesignTests().fixture()
        self.snapshot = {"project": {"name": "Unsaved stack"}, "design_ir": design,
                         "assembly_ir": assembly, "assembly_designs": designs,
                         "analyses": {"latest_result": {"analysis_id": "result", "outputs": {"volts": [1, 2]}}}}

    def request(self, method, **params):
        return handle_project_request(method, {"_backup_root": str(self.root), **params}, request_id="backup-test", application_version="test")

    def write(self, **params):
        return self.request("write_project_backup", session_id=self.session, snapshot=self.snapshot, **params)

    def test_unsaved_portable_roundtrip_and_integrity(self):
        original = copy.deepcopy(self.snapshot)
        saved = self.write()
        self.assertTrue(saved["ok"], saved)
        row = saved["result"]
        self.assertTrue(Path(row["path"]).is_file())
        self.assertEqual(self.snapshot, original)
        self.assertEqual(self.request("list_project_backups")["result"]["backups"][0]["id"], row["id"])
        self.assertTrue(self.request("open_project_backup", id=row["id"])["ok"])
        self.assertEqual(read_project(row["path"]).payload["project"]["name"], "Unsaved stack")
        with Path(row["path"]).open("ab") as stream:
            stream.write(b"corruption")
        self.assertFalse(self.request("open_project_backup", id=row["id"])["ok"])

    def test_base_artifacts_preserved_primary_unchanged_and_stale_rejected(self):
        base = Path(self.directory.name) / "primary.spike"
        from tests.python.test_mcad_tessellation_project import glb_bytes
        artifact = glb_bytes()
        payload = copy.deepcopy(self.snapshot)
        payload["models"] = {"contract": "spike/model-index/v1", "models": [{"id": "enclosure", "model_type": "glb",
            "uri": "package:models/artifacts/original.glb", "digest": hashlib.sha256(artifact).hexdigest()}]}
        manifest = write_spike_package(base, payload, preserved_members={"models/artifacts/original.glb": artifact}, generate_geometry_tables=False)
        before = base.read_bytes()
        saved = self.write(base_package_path=str(base), expected_base_manifest_sha256=manifest["manifest_payload_sha256"])
        self.assertTrue(saved["ok"], saved)
        members = read_project(saved["result"]["path"], include_members=True).members
        self.assertEqual(members["models/artifacts/original.glb"], artifact)
        self.assertEqual(read_project(saved["result"]["path"]).payload["models"]["models"][0]["id"], "enclosure")
        self.assertEqual(base.read_bytes(), before)
        count = len(list(self.root.glob("*.spike")))
        failed = self.write(base_package_path=str(base), expected_base_manifest_sha256="0" * 64)
        self.assertFalse(failed["ok"], failed)
        self.assertEqual(len(list(self.root.glob("*.spike"))), count)
        self.assertFalse(self.write(base_package_path=str(base))["ok"])

    def test_retention_ten_session_only_and_current_base_protected(self):
        first = self.write()["result"]
        protected = Path(first["path"])
        digest = read_project(protected).manifest["manifest_payload_sha256"]
        unrelated = self.root / "user-not-a-backup.txt"
        unrelated.write_text("preserve")
        for _ in range(11):
            saved = self.write(base_package_path=str(protected), expected_base_manifest_sha256=digest)
            self.assertTrue(saved["ok"], saved)
        rows = self.request("list_project_backups")["result"]["backups"]
        self.assertEqual(len(rows), 10)
        self.assertTrue(protected.is_file())
        self.assertEqual(unrelated.read_text(), "preserve")
        self.session = uuid.uuid4().hex
        self.assertTrue(self.write()["ok"])
        self.assertEqual(len(self.request("list_project_backups")["result"]["backups"]), 11)

    def test_failed_write_size_limit_and_malformed_metadata_do_not_prune(self):
        saved = self.write()["result"]
        before = set(self.root.glob("*.spike"))
        with patch("python.spike_core.service_project_backup.MAX_TOTAL_BYTES", 1):
            self.assertFalse(self.write()["ok"])
        self.assertEqual(set(self.root.glob("*.spike")), before)
        self.assertTrue(Path(saved["path"]).exists())
        (self.root / "unrelated.json").write_text("{}")
        self.assertFalse(self.write()["ok"])
        self.assertEqual(set(self.root.glob("*.spike")), before)
        self.assertFalse(self.request("list_project_backups")["ok"])

    def test_orphan_files_count_toward_storage_and_lock_recovers(self):
        from python.spike_core.service_project_backup import _lock, _root
        root = _root({"_backup_root": str(self.root)})
        with _lock(root):
            self.assertFalse(self.write()["ok"])
        orphan = root / "unrecognized.spike"
        orphan.write_bytes(b"unknown-user-data")
        with patch("python.spike_core.service_project_backup.MAX_TOTAL_BYTES", 5):
            self.assertFalse(self.write()["ok"])
        self.assertEqual(orphan.read_bytes(), b"unknown-user-data")
        self.assertTrue(self.write()["ok"])

    def test_invalid_requests_fail_closed(self):
        self.assertFalse(self.request("write_project_backup", session_id="../other", snapshot=self.snapshot)["ok"])
        self.assertFalse(self.request("open_project_backup", id="../primary.spike")["ok"])
        self.assertFalse(self.write(path=str(Path(self.directory.name) / "primary.spike"))["ok"])
        with patch("python.spike_core.service_project_handlers.write_spike_package", side_effect=OSError("disk full")):
            self.assertFalse(self.write()["ok"])
        self.assertEqual(list(self.root.glob("*.spike")), [])
        self.assertEqual(list(self.root.glob("*.json")), [])
        self.assertTrue(self.write()["ok"])


if __name__ == "__main__":
    unittest.main()
