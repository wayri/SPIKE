# SPDX-License-Identifier: Apache-2.0
"""Frontmatter regressions for the repository documentation checker."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_documentation_frontmatter", ROOT / "scripts" / "check_documentation.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


class DocumentationFrontmatterTests(unittest.TestCase):
    def check(self, content: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "README.md"
            path.write_text(content, encoding="utf-8")
            return CHECKER.check_documentation(root)

    def test_closed_leading_frontmatter_is_not_a_setext_heading(self) -> None:
        errors = self.check(
            "---\nname: SPIKE UI\ndescription: Desktop UI guidance\n---\n# SPIKE UI\n\n## Workflow\n"
        )
        self.assertEqual([], errors)

    def test_body_after_closed_frontmatter_keeps_original_line_numbers(self) -> None:
        errors = self.check("---\ntitle: Guide\n---\n# Guide\n\n[Missing](missing.md)\n")
        self.assertEqual(1, len(errors))
        self.assertIn("README.md:6: local target does not exist", errors[0])

    def test_unclosed_leading_delimiter_does_not_hide_document(self) -> None:
        errors = self.check("---\ntitle: Guide\n# Guide\n\n[Missing](missing.md)\n")
        self.assertTrue(any("README.md:5: local target does not exist" in error for error in errors))

    def test_nonleading_delimiter_remains_a_setext_heading(self) -> None:
        errors = self.check("# Guide\n\n[Metadata](#metadata)\n\nMetadata\n---\n")
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
