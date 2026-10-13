# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.kicad_schematic_importer import (
    KicadSchematicViewError,
    _parse_netlist,
    _sanitize_svg,
    import_kicad_schematic_view,
)


ROOT_SCH = '''(kicad_sch (version 20231120) (generator eeschema)
  (uuid 00000000-0000-0000-0000-000000000001)
  (symbol (lib_id "Device:R") (at 25.4 30.48 90) (unit 1)
    (uuid 11111111-1111-1111-1111-111111111111)
    (property "Reference" "R1" (at 25.4 29.21 90))
    (property "Value" "10k" (at 25.4 31.75 90)))
  (sheet (at 50 50) (size 20 10)
    (uuid 22222222-2222-2222-2222-222222222222)
    (property "Sheet name" "child" (at 50 49 0))
    (property "Sheet file" "child.kicad_sch" (at 50 61 0))))'''

CHILD_SCH = '''(kicad_sch (version 20231120) (generator eeschema)
  (uuid 00000000-0000-0000-0000-000000000002)
  (symbol (lib_id "Device:C") (at 12.7 15.24 0) (unit 1)
    (uuid 33333333-3333-3333-3333-333333333333)
    (property "Reference" "C1" (at 12.7 13.97 0))
    (property "Value" "1u" (at 12.7 16.51 0))))'''

NETLIST = b'''<?xml version="1.0"?><export><components>
  <comp ref="R1"><value>10k</value><footprint>R_0603</footprint></comp>
</components><nets><net code="1" name="VCC">
  <node ref="R1" pin="1" pinfunction="~"/><node ref="C1" pin="1"/>
</net></nets></export>'''

SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">
  <g><path d="M 0 0 L 10 10"/><text x="1" y="2">R1</text></g>
</svg>'''


class KicadSchematicViewerTests(unittest.TestCase):
    def test_returns_sanitized_pages_source_identity_and_compiled_connectivity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schematic = root / "root.kicad_sch"
            schematic.write_text(ROOT_SCH, encoding="utf-8")
            (root / "child.kicad_sch").write_text(CHILD_SCH, encoding="utf-8")

            def fake_run(arguments, cwd, timeout):
                arguments = list(arguments)
                if "svg" in arguments:
                    (cwd / "root.svg").write_bytes(SVG)
                else:
                    Path(arguments[arguments.index("--output") + 1]).write_bytes(NETLIST)
                return subprocess.CompletedProcess(arguments, 0, b"rendered", b"")

            with patch("python.spike_core.kicad_schematic_importer._run", side_effect=fake_run) as launched:
                result = import_kicad_schematic_view(schematic, executable="kicad-cli", timeout_seconds=12)

        self.assertEqual(result["contract"], "spike/kicad-schematic-view/v1")
        self.assertEqual(len(result["hierarchy"]), 2)
        self.assertEqual({item["reference"] for item in result["symbols"]}, {"R1", "C1"})
        resistor = next(item for item in result["symbols"] if item["reference"] == "R1")
        self.assertEqual(resistor["position_mm"], {"x": 25.4, "y": 30.48})
        self.assertEqual(resistor["nets"], ["VCC"])
        self.assertEqual(result["nets"][0]["nodes"][1]["symbol_ids"], [
            "33333333-3333-3333-3333-333333333333@/22222222-2222-2222-2222-222222222222/"
        ])
        self.assertIn('(property "Reference" "C1"', result["source_files"][1]["content"])
        self.assertEqual(result["pages"][0]["view_box"], [0.0, 0.0, 10.0, 10.0])
        self.assertNotIn("<?xml", result["pages"][0]["svg"])
        self.assertEqual(launched.call_count, 2)
        for call in launched.call_args_list:
            self.assertFalse(call.args[0][0].lower().endswith(("cmd.exe", "powershell.exe")))

    def test_rejects_hierarchy_traversal_before_starting_kicad(self) -> None:
        bad = ROOT_SCH.replace("child.kicad_sch", "../child.kicad_sch")
        with tempfile.TemporaryDirectory() as directory:
            schematic = Path(directory) / "root.kicad_sch"
            schematic.write_text(bad, encoding="utf-8")
            with patch("python.spike_core.kicad_schematic_importer._run") as launched:
                with self.assertRaisesRegex(KicadSchematicViewError, "without traversal"):
                    import_kicad_schematic_view(schematic, executable="kicad-cli")
                launched.assert_not_called()

    def test_rejects_active_or_external_svg(self) -> None:
        unsafe = b'<svg xmlns="http://www.w3.org/2000/svg"><script>bad()</script></svg>'
        with self.assertRaisesRegex(KicadSchematicViewError, "unsupported element"):
            _sanitize_svg(unsafe)
        external = b'<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///secret"/></svg>'
        with self.assertRaises(KicadSchematicViewError):
            _sanitize_svg(external)

    def test_rejects_xml_entities_and_malformed_netlist(self) -> None:
        with self.assertRaisesRegex(KicadSchematicViewError, "forbidden XML"):
            _parse_netlist(b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///x">]><export/>')
        with self.assertRaisesRegex(KicadSchematicViewError, "malformed XML"):
            _parse_netlist(b"<export>")


if __name__ == "__main__":
    unittest.main()
