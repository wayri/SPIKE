# SPDX-License-Identifier: Apache-2.0
"""Exercise sheet import/preview through the real worker dispatch boundary."""
import json
from pathlib import Path
import unittest

from python.spike_core.service import handle


class SheetFoldingServiceTests(unittest.TestCase):
    def test_nonmetal_sheet_and_rigid_flex_coupon_retain_material_evidence(self):
        root = Path(__file__).resolve().parents[2]
        raw = json.loads((root / "examples/mcad/rigid-flex-strip.spike-sheet.json").read_text(encoding="utf-8"))
        material = raw["sheet"]["material"]
        imported = handle({"method": "import_sheet_definition", "params": {"contents": json.dumps(raw), "source_format": "json"}})
        self.assertTrue(imported["ok"], imported)
        self.assertEqual(imported["result"]["sheet"]["sheet"]["material"], material)
        self.assertTrue(handle({"method": "preview_sheet_fold", "params": {"sheet": raw, "fraction": 1}})["ok"])
        raw.update(kind="sheet", flex_regions=[])
        self.assertTrue(handle({"method": "preview_sheet_fold", "params": {"sheet": raw, "fraction": 1}})["ok"])

    def test_import_preview_roundtrip_and_explicit_bad_transport(self):
        source = (Path(__file__).resolve().parents[2] /
                  "examples/mcad/folded-sheet.spike-sheet.json").read_text(encoding="utf-8")
        imported = handle({"method": "import_sheet_definition", "params": {
            "contents": source, "source_format": "json"}})
        self.assertTrue(imported["ok"], imported)
        sheet = imported["result"]["sheet"]
        folded = handle({"method": "preview_sheet_fold", "params": {"sheet": sheet, "fraction": 0.5}})
        self.assertTrue(folded["ok"], folded)
        self.assertEqual(folded["result"]["preview"]["model_status"], "analytical_geometry_preview")
        again = handle({"method": "import_sheet_definition", "params": {
            "contents": json.dumps(sheet), "source_format": "json"}})
        self.assertEqual(again["result"]["sheet"], sheet)
        for params in ({"sheet": sheet, "fraction": True},
                       {"sheet": sheet, "fraction": 1, "output_path": "unapproved.step"},
                       {"sheet": sheet, "fraction": float("inf")}):
            result = handle({"method": "preview_sheet_fold", "params": params})
            self.assertFalse(result["ok"], result)

    def test_import_does_not_accept_a_host_path_or_program(self):
        for params in ({"path": "unapproved.dxf", "source_format": "dxf"},
                       {"contents": "print('not a sheet')", "source_format": "python"}):
            self.assertFalse(handle({"method": "import_sheet_definition", "params": params})["ok"])
