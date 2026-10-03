# SPDX-License-Identifier: Apache-2.0
"""Focused tests for the repository documentation quality guard."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_documentation", ROOT / "scripts" / "check_documentation.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


class DocumentationQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, relative_path: str, content: str | bytes) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def errors(self, *paths: str) -> list[str]:
        requested = [Path(path) for path in paths] if paths else None
        return CHECKER.check_documentation(self.root, requested)

    def test_accepts_unicode_valid_links_images_anchors_and_fences(self) -> None:
        self.write("docs/guide.md", "# Guide\n")
        self.write("docs/name (draft).md", "# Draft\n")
        self.write("images/icon.png", b"png")
        self.write("images/bare.png", b"png")
        self.write(
            "README.md",
            """# SPIKE — Ω tools

[Usage](#usage) · [Second usage](#usage-1) · [Guide](docs/guide.md)
[Draft](<docs/name (draft).md>) · [![Build](https://example.test/badge.svg)](docs/guide.md#guide)
<img src="images/icon.png" alt="icon">
<img src=images/bare.png alt="bare icon">

<details><summary>More</summary>

[External fragment](https://example.test/guide#missing-locally)

</details>

## Usage

## Usage

```text
[ignored example](missing.md)
```
""",
        )
        self.assertEqual([], self.errors())

    def test_reports_invalid_utf8_and_common_mojibake(self) -> None:
        self.write("invalid.md", b"# Bad\n\xff\n")
        self.write("README.md", "# SPIKE â€” tools\n\nÂ· Guide\n")
        self.assertTrue(any("not valid UTF-8" in error for error in self.errors("invalid.md")))
        errors = self.errors()
        self.assertTrue(any("corrupted punctuation" in error for error in errors))
        self.assertTrue(any("stray UTF-8 lead byte" in error for error in errors))

    def test_reports_missing_markdown_and_html_image_targets(self) -> None:
        self.write(
            "README.md",
            '# SPIKE\n\n[Guide](docs/missing.md)\n<img src="images/missing.png">\n',
        )
        errors = self.errors()
        self.assertEqual(2, sum("local target does not exist" in error for error in errors))

    def test_reports_missing_heading_anchor(self) -> None:
        self.write("README.md", "# SPIKE\n\n[Setup](#installation)\n\n## Usage\n")
        self.assertTrue(any("heading anchor does not exist" in error for error in self.errors()))

    def test_reports_unclosed_fence_and_heading_hierarchy_jump(self) -> None:
        self.write("README.md", "# SPIKE\n\n### Details\n\n```python\nprint('x')\n")
        errors = self.errors()
        self.assertTrue(any("heading level jumps" in error for error in errors))
        self.assertTrue(any("fenced code block is not closed" in error for error in errors))

    def test_explicit_paths_do_not_implicitly_check_readme(self) -> None:
        self.write("README.md", "# SPIKE â€” broken\n")
        self.write("docs/guide.md", "# Guide\n")
        self.assertEqual([], self.errors("docs/guide.md"))

    def test_comments_and_colliding_heading_slugs(self) -> None:
        self.write("README.md", "<!--\n### Obsolete heading\n[Old](missing.md)\n-->\n# SPIKE\n\n## Usage\n## Usage-1\n## Usage\n[Last](#usage-2)\n")
        self.assertEqual([], self.errors())

    def test_empty_readme_and_malformed_link_are_diagnostics(self) -> None:
        self.write("README.md", "")
        self.assertTrue(any("level 1 title" in error for error in self.errors()))
        self.write("README.md", "# SPIKE\n[Bad](https://[invalid)\n")
        self.assertTrue(any("malformed link" in error for error in self.errors()))


if __name__ == "__main__":
    unittest.main()
