# SPDX-License-Identifier: Apache-2.0
import hashlib
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from python.spikes.pdk_inventory import PdkInventoryError, catalog, inspect


class PdkInventoryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / f"pdk_inventory_fixture_{uuid.uuid4().hex}"
        self.root.mkdir()
        self.model_root = self.root / "sky130"
        self.entry = self.model_root / "sky130A" / "libs.tech" / "ngspice" / "sky130.lib.spice"
        self.entry.parent.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def write(self, relative, text):
        path = self.model_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_catalog_has_official_layout_metadata_without_capability_claims(self):
        entries = {item["id"]: item for item in catalog()}
        self.assertEqual(entries["sky130"]["default_entry"], "sky130A/libs.tech/ngspice/sky130.lib.spice")
        self.assertEqual(entries["gf180mcu"]["official_url"], "https://github.com/google/gf180mcu-pdk")
        self.assertEqual(entries["ihp_sg13g2"]["official_url"], "https://github.com/IHP-GmbH/IHP-Open-PDK")
        self.assertTrue(all(item["model_readiness"] == "review_only" and not item["qualified"] for item in entries.values()))

    def test_inspects_sections_dependencies_hashes_and_declarations_inertly(self):
        dependency = self.write("sky130A/libs.tech/ngspice/cells.spice", """* no execution
.subckt INV A Y VP VN params: w=1 l=2
.ends INV
.subckt INV IN OUT VDD VSS strength=3
.ends INV
""")
        self.entry.write_text(""".lib tt
.include "cells.spice"
.endl tt
.lib cells.spice ss
""", encoding="utf-8")
        license_path = self.write("LICENSE.txt", "fixture license text\n")

        with patch("subprocess.run", side_effect=AssertionError("must remain inert")):
            report = inspect("sky130", self.root)

        self.assertEqual(report["status"], "review_only")
        self.assertEqual(report["root"], str(self.model_root.resolve()))
        self.assertEqual(report["entry"], "sky130A/libs.tech/ngspice/sky130.lib.spice")
        self.assertEqual(report["sections"], ["tt"])
        self.assertEqual(len(report["section_declarations"]), 1)
        self.assertEqual([item["section"] for item in report["dependencies"]], [None, "ss"])
        self.assertEqual(len(report["subcircuits"]), 2)
        self.assertEqual(report["subcircuits"][0]["pins"], ["A", "Y", "VP", "VN"])
        self.assertEqual(report["subcircuits"][0]["parameters"], [{"name": "w", "default": "1"}, {"name": "l", "default": "2"}])
        self.assertEqual(len(report["duplicate_subcircuits"]), 1)
        self.assertEqual(report["licenses"][0]["sha256"], hashlib.sha256(license_path.read_bytes()).hexdigest())
        self.assertEqual(report["claims"]["model_execution"], "unsupported")
        self.assertEqual(report["claims"]["tcad"], "unsupported")
        self.assertFalse(report["qualified"])
        self.assertIn(dependency.resolve().relative_to(self.model_root.resolve()).as_posix(), [item["path"] for item in report["files"]])

    def test_missing_dependency_and_section_syntax_are_preserved_as_issues(self):
        self.entry.write_text(""".endl orphan
.lib ff
.include missing.spice
""", encoding="utf-8")
        report = inspect("sky130", self.root)
        self.assertFalse(report["inspection_complete"])
        self.assertEqual(report["sections"], ["ff"])
        self.assertEqual(report["dependencies"][0]["status"], "unresolved")
        self.assertEqual({issue["code"] for issue in report["issues"]},
                         {"unmatched_endl", "unclosed_lib_section", "unresolved_dependency"})

    def test_rejects_entry_escape_and_missing_entry(self):
        self.entry.write_text(".end\n", encoding="utf-8")
        with self.assertRaisesRegex(PdkInventoryError, "relative path"):
            inspect("sky130", self.root, "../outside.spice")
        with self.assertRaisesRegex(PdkInventoryError, "entry is missing"):
            inspect("sky130", self.root, "absent.spice")

    def test_rejects_dependency_escape(self):
        outside = self.root / "outside.spice"
        outside.write_text(".subckt BAD a b\n", encoding="utf-8")
        self.entry.write_text(".include ../../../../outside.spice\n", encoding="utf-8")
        with self.assertRaisesRegex(PdkInventoryError, "escapes"):
            inspect("sky130", self.root)

    def test_enforces_file_size_bound_without_reading_dependency(self):
        self.entry.write_text(".include large.spice\n", encoding="utf-8")
        self.write("sky130A/libs.tech/ngspice/large.spice", "x" * 40)
        with patch("python.spikes.pdk_inventory.MAX_FILE_BYTES", 30):
            report = inspect("sky130", self.root)
        self.assertIn("file_too_large", {issue["code"] for issue in report["issues"]})


if __name__ == "__main__":
    unittest.main()
