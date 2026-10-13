# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from python.spike_core.connectivity_view_importer import (
    ConnectivityViewError, _generated_svg, import_connectivity_view,
)


XML = '''<?xml version="1.0"?><export><components>
<comp ref="R1"><value>10k</value><footprint>R_0603</footprint></comp>
<comp ref="C1"><value>1u</value><footprint>C_0603</footprint></comp>
</components><nets><net code="1" name="VCC"><node ref="R1" pin="1"/><node ref="C1" pin="1"/></net>
<net code="2" name="GND"><node ref="R1" pin="2"/><node ref="C1" pin="2"/></net></nets></export>'''

LEGACY = '''(export (version D)
  (components (comp (ref R1) (value 10k) (footprint R_0603)))
  (nets (net (code 1) (name VCC) (node (ref R1) (pin 1)))))'''


def odb_files() -> dict[str, str]:
    return {
        "matrix/matrix": "STEP {\nCOL=1\nNAME=board\n}\nLAYER {\nROW=1\nNAME=top\nTYPE=SIGNAL\nCONTEXT=BOARD\nPOLARITY=POSITIVE\n}\nLAYER {\nROW=2\nNAME=comp_+_top\nTYPE=COMPONENT\n}\n",
        "misc/info": "UNITS=MM\nODB_VERSION_MAJOR=8\n",
        "steps/board/profile": "UNITS=MM\nOB 0 0 I\nOS 10 0\nOS 10 5\nOS 0 5\nOS 0 0\nOE\n",
        "steps/board/eda/data": "UNITS=MM\nLYR top\nNET VCC\nSNT TOP T 0 0\nFID C 0 0\nPKG CONN 1 0 0 2 2\nPIN 1 S 1 1 0 E\n",
        "steps/board/layers/top/features": "UNITS=MM\n$0 r1\nF 1\nP 1 1 0 P 0 0\n",
        "steps/board/layers/comp_+_top/components": "UNITS=MM\nCMP 0 1 1 0 N J1 CONN\nTOP 0 1 1 0 N 0 0 1\n",
    }


class ConnectivityViewImporterTests(unittest.TestCase):
    def test_xml_generates_labelled_self_contained_connectivity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "board.xml"
            path.write_text(XML, encoding="utf-8")
            result = import_connectivity_view(path)
        self.assertEqual(result["source"]["presentation"], "generated_connectivity")
        self.assertEqual(result["source"]["format"], "kicad_xml_netlist")
        self.assertIn("R1", result["pages"][0]["svg"])
        self.assertIn("VCC", result["pages"][0]["svg"])
        self.assertEqual(len(result["pages"][0]["view_box"]), 4)
        self.assertEqual(result["nets"][0]["nodes"][0]["symbol_ids"], [result["symbols"][1]["id"]])
        self.assertEqual(result["source_files"][0]["content"], XML)

    def test_legacy_net_preserves_reference_pin_and_net(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "board.net"
            path.write_text(LEGACY, encoding="utf-8")
            result = import_connectivity_view(path)
        self.assertEqual(result["source"]["format"], "kicad_legacy_netlist")
        self.assertEqual(result["nets"][0]["nodes"][0]["pin"], "1")

    def test_rejects_xml_entities_conflicts_and_unknown_spice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entity = root / "entity.xml"
            entity.write_text('<!DOCTYPE x [<!ENTITY e SYSTEM "file:///x">]><export/>', encoding="utf-8")
            with self.assertRaisesRegex(ConnectivityViewError, "DTD or entity"):
                import_connectivity_view(entity)
            conflict = root / "conflict.xml"
            conflict.write_text(XML.replace('<node ref="R1" pin="2"/>', '<node ref="R1" pin="1"/>'), encoding="utf-8")
            with self.assertRaisesRegex(ConnectivityViewError, "conflicting nets"):
                import_connectivity_view(conflict)
            spice = root / "circuit.sp"
            spice.write_text("R1 in out 10k", encoding="utf-8")
            with self.assertRaisesRegex(ConnectivityViewError, "generic SPICE"):
                import_connectivity_view(spice)

    def test_odb_directory_uses_exact_toeprint_connectivity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "job"
            for name, content in odb_files().items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            result = import_connectivity_view(root, format_hint="odb++", step="board")
        self.assertEqual(result["source"]["format"], "odb++")
        self.assertEqual(result["nets"][0]["nodes"], [{
            "reference": "J1", "pin": "1", "pin_function": "",
            "symbol_ids": [result["symbols"][0]["id"]], "pin_uuids": [],
        }])
        self.assertEqual(result["source_files"], [])

    def test_worker_route_accepts_archive_and_retains_error_envelope(self) -> None:
        from python.spike_core.service import handle
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "job.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for name, content in odb_files().items():
                    archive.writestr(name, content)
            response = handle({"id": "connectivity-test", "method": "import_connectivity_view",
                               "params": {"path": str(archive_path), "format_hint": "odb++", "step": "board"}})
            self.assertTrue(response["ok"], response)
            self.assertEqual(response["result"]["nets"][0]["name"], "VCC")
            rejected = handle({"id": "bad-import", "method": "import_connectivity_view",
                               "params": {"path": str(Path(directory) / "missing.xml")}})
            self.assertFalse(rejected["ok"])
            self.assertIn("readable connectivity", rejected["error"])

    def test_odb_archive_traversal_and_malformed_jobs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            unsafe = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(unsafe, "w") as archive:
                archive.writestr("../escape", "bad")
            with self.assertRaises((ValueError, ConnectivityViewError)):
                import_connectivity_view(unsafe, format_hint="odb++")
            malformed = Path(directory) / "malformed.zip"
            with zipfile.ZipFile(malformed, "w") as archive:
                archive.writestr("readme", "not ODB++")
            with self.assertRaises((ValueError, ConnectivityViewError)):
                import_connectivity_view(malformed, format_hint="odb++")

    def test_generated_layout_adapts_to_tall_components_and_long_net_labels(self) -> None:
        components = [{"reference": reference, "value": "connector", "footprint": "test"}
                      for reference in ("J1", "J2", "J3", "J4")]
        long_name = "LONG_RAIL_NAME_THAT_MUST_REMAIN_AVAILABLE_TO_THE_VIEWER"
        nets = [{"code": str(index), "name": f"{long_name}_{index}",
                 "nodes": [{"reference": "J1", "pin": str(index), "pin_function": ""},
                           {"reference": "J4", "pin": str(index), "pin_function": ""}]}
                for index in range(1, 31)]
        svg, symbols = _generated_svg(components, nets)
        first, below = next(item for item in symbols if item["reference"] == "J1"), next(
            item for item in symbols if item["reference"] == "J4")
        self.assertGreaterEqual(below["hit_box"]["y"], first["hit_box"]["y"] + first["hit_box"]["height"] + 45)
        view_box = [float(value) for value in ET.fromstring(svg).get("viewBox", "").split()]
        self.assertEqual(len(view_box), 4)
        self.assertGreaterEqual(view_box[3], below["hit_box"]["y"] + below["hit_box"]["height"])
        self.assertIn(long_name, svg)  # full value survives in each title
        self.assertIn("...", svg)  # visible labels remain within their bounded lane


if __name__ == "__main__":
    unittest.main()
