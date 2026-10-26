# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Original tiny bytecode fixtures for the fail-closed freezer/source guard."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import verify_packaged_source_modules as guard


class PackagedSourceCoherenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        folder = self.root / "python"
        folder.mkdir()
        (folder / "fixture.py").write_text("VALUE = 7\n", encoding="utf-8")

    def inspect(self, modules, **kwargs):
        archive = SimpleNamespace(toc=modules, extract=lambda name: modules[name])
        reader = SimpleNamespace(open_embedded_archive=lambda name: archive)
        with patch.object(guard, "CArchiveReader", return_value=reader):
            return guard.verify_packaged_source_modules("unexecuted-fixture", source_root=self.root, **kwargs)

    def test_equivalent_code_with_relocated_filename_passes(self):
        result = self.inspect({"python.fixture": compile("VALUE = 7\n", "relocated.py", "exec")})
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["checked_modules"], 1)

    def test_changed_constants_and_nested_code_fail(self):
        for text in ("VALUE = 8\n", "def action():\n    return 7\n"):
            with self.subTest(text=text), self.assertRaisesRegex(RuntimeError, '"changed": \\["python.fixture"\\]'):
                self.inspect({"python.fixture": compile(text, "relocated.py", "exec")})

    def test_missing_source_empty_scope_and_missing_required_owners_fail(self):
        cases = (({"python.absent": compile("pass", "x", "exec")}, {}),
                 ({"third_party": compile("pass", "x", "exec")}, {}),
                 ({"python.fixture": compile("VALUE = 7\n", "x", "exec")}, {"require_em_cosimulation": True}))
        for modules, kwargs in cases:
            with self.subTest(modules=list(modules)), self.assertRaises(RuntimeError):
                self.inspect(modules, **kwargs)

    def test_line_table_change_is_not_hidden_by_filename_normalization(self):
        with self.assertRaises(RuntimeError):
            self.inspect({"python.fixture": compile("\nVALUE = 7\n", "relocated.py", "exec")})


if __name__ == "__main__":
    unittest.main()
