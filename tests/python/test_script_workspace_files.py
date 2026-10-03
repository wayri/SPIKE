"""Confined file service for the integrated Python workspace."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.script_runtime import run_python_script
from python.spike_core.service_script_workspace import handle_script_workspace_request
from python.spike_core.script_workspace_files import python_workspace_files


class ScriptWorkspaceFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def call(self, action: str, path: str = "", **params: object) -> dict[str, object]:
        return python_workspace_files({
            "root": str(self.root), "path": path, "action": action, **params,
        })

    def test_lazy_list_filters_generated_and_nontext_entries(self):
        (self.root / "package").mkdir()
        (self.root / "node_modules").mkdir()
        (self.root / "script.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / "notes.md").write_text("hidden from script tree\n", encoding="utf-8")
        (self.root / "image.png").write_bytes(b"png")
        result = self.call("list")
        self.assertEqual(result["contract"], "spike/python-workspace-files/v1")
        self.assertEqual([entry["name"] for entry in result["entries"]], ["package", "script.py"])
        self.assertFalse(result["truncated"])

    def test_worker_subservice_routes_file_contract(self):
        (self.root / "route.py").write_text("value = 1\n", encoding="utf-8")
        response = handle_script_workspace_request(
            "python_workspace_files",
            {"root": str(self.root), "path": "", "action": "list"},
            trusted_extension_ids=[],
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["entries"][0]["name"], "route.py")
        self.assertIsNone(handle_script_workspace_request(
            "not_a_workspace_method", {}, trusted_extension_ids=[],
        ))

    def test_read_hash_and_atomic_write_with_conflict_detection(self):
        source = self.root / "script.py"
        source.write_text("value = 1\n", encoding="utf-8")
        opened = self.call("read", "script.py")
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(opened["sha256"], expected)

        saved = self.call("write", "script.py", contents="value = 2\n", expected_sha256=expected)
        self.assertEqual(source.read_text(encoding="utf-8"), "value = 2\n")
        source.write_text("external = True\n", encoding="utf-8")
        with self.assertRaisesRegex(FileExistsError, "changed"):
            self.call("write", "script.py", contents="value = 3\n", expected_sha256=saved["sha256"])
        self.assertEqual(source.read_text(encoding="utf-8"), "external = True\n")

    def test_create_only_python_and_reject_escape(self):
        created = self.call("write", "new_script.py", contents="print('new')\n")
        self.assertEqual(created["size"], len("print('new')\n"))
        with self.assertRaisesRegex(ValueError, "only save .py"):
            self.call("write", "notes.txt", contents="unsafe overwrite")
        with self.assertRaisesRegex(ValueError, "stay below"):
            self.call("read", "../outside.py")
        with self.assertRaisesRegex(ValueError, "required"):
            self.call("write", "new_script.py", contents="blind overwrite")

    def test_read_rejects_binary_and_oversized_files(self):
        (self.root / "binary.py").write_bytes(b"a\x00b")
        with self.assertRaisesRegex(ValueError, "Binary"):
            self.call("read", "binary.py")
        (self.root / "large.py").write_bytes(b"x" * 512_001)
        with self.assertRaisesRegex(ValueError, "512 KB"):
            self.call("read", "large.py")
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.call("write", "large.py", contents="small\n", expected_sha256="0" * 64)

    def test_large_directory_listing_is_bounded_and_marked_truncated(self):
        for index in range(505):
            (self.root / f"script_{index:04d}.py").write_text("", encoding="utf-8")
        result = self.call("list")
        self.assertEqual(len(result["entries"]), 500)
        self.assertTrue(result["truncated"])

    def test_normal_run_uses_filename_working_directory_and_local_imports(self):
        default_root = self.root / "default"
        selected_root = self.root / "selected"
        default_root.mkdir()
        selected_root.mkdir()
        (selected_root / "helper.py").write_text("VALUE = 17\n", encoding="utf-8")
        with patch.dict(os.environ, {"SPIKE_WORKSPACE": str(default_root)}):
            result = run_python_script({
                "code": "import helper\nprint(__file__)\nprint(helper.VALUE)\n",
                "filename": "main.py", "working_directory": str(selected_root),
            })
        self.assertEqual(result["status"], "completed")
        self.assertIn(str(selected_root / "main.py"), result["stdout"])
        self.assertTrue(result["stdout"].rstrip().endswith("17"))


if __name__ == "__main__":
    unittest.main()
