"""Small reproducible regressions found in pinned public hardware projects."""
import json
from pathlib import Path
import tempfile
import unittest

from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.odb_importer import import_odb_design
from python.spike_core.odb_features import parse_features
from python.spike_core.source_package import SourcePackage
from tests.python.test_odb_harness_extensions import board_files, write_board


class PublicBoardRegressions(unittest.TestCase):
    def kicad(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "board.kicad_pcb"
            path.write_text(content, encoding="utf-8")
            return import_kicad_design(str(path))

    def test_modern_layer_ids_do_not_change_physical_via_span(self):
        d = self.kicad('(kicad_pcb (version 20241229) (layers (0 "F.Cu" signal) (4 "In1.Cu" signal) (6 "In2.Cu" signal) (2 "B.Cu" signal)) (net 1 "GND") (via (at 1 1) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1)))')
        self.assertEqual(len(d.vias), 1)
        self.assertEqual(d.vias[0]["layers"], ("F.Cu", "B.Cu"))

    def test_duplicate_silkscreen_polygons_are_drawings_not_copper(self):
        polygon = '(fp_poly (pts (xy 0 0) (xy 1 0) (xy 1 1)) (layer "B.SilkS"))'
        d = self.kicad(f'(kicad_pcb (layers (0 "F.Cu" signal) (2 "B.Cu" signal)) (footprint "Logo" (layer "F.Cu") {polygon} {polygon}))')
        self.assertFalse(d.zones)
        DesignIRV2.from_v1(d)

    def test_duplicate_source_pad_ids_and_anonymous_tracks_survive(self):
        pad = '(pad "1" smd rect (at %s 0) (size 1 1) (layers "F.Cu") (uuid "same-source-uuid"))'
        track = '(segment (start 0 0) (end 1 0) (width 0.2) (layer "F.Cu"))'
        d = self.kicad(f'(kicad_pcb (layers (0 "F.Cu" signal) (2 "B.Cu" signal)) (footprint "test" (property "Reference" "J1") (layer "F.Cu") {pad % 0} {pad % 2}) {track} {track})')
        typed = DesignIRV2.from_v1(d)
        self.assertEqual(len({p.id for p in typed.pads}), 2)
        self.assertEqual(len({t.id for t in typed.tracks}), 2)
        self.assertEqual(d.pads[0]["source_native_uuid"], "same-source-uuid")

    def test_uppercase_matrix_and_legacy_units_do_not_lose_features(self):
        files = board_files()
        files["matrix/matrix"] = files["matrix/matrix"].replace("NAME=board", "NAME=BOARD").replace("NAME=top", "NAME=TOP").replace("NAME=comp_+_top", "NAME=COMP_+_TOP")
        files["steps/board/layers/top/features"] = files["steps/board/layers/top/features"].replace("UNITS=MM", "U MM")
        with tempfile.TemporaryDirectory() as directory:
            d = import_odb_design(str(write_board(directory, files)))
        self.assertEqual(len(d.tracks), 1)
        self.assertEqual(d.tracks[0]["net_id"], 1)
        self.assertEqual(d.metadata["odb_matrix"][0]["NAME"], "BOARD")

    def test_full_circle_surface_uses_two_canonical_arcs(self):
        errors = []
        rows = parse_features('UNITS=MM\nS P 0\nOB 1 0 I\nOC 1 0 0 0 N\nOE\nSE', 'top', 'MM', lambda *args: errors.append(args))
        self.assertFalse(errors)
        self.assertEqual(len(rows[0]["boundary_rings"][0]["segments"]), 2)

    def test_empty_attribute_text_export_is_preserved(self):
        from python.spike_core.odb_features import Attributes
        table = Attributes()
        self.assertTrue(table.consume("&0"))
        self.assertEqual(table.strings["0"], "")

    def test_repeated_first_contour_vertex_preserves_surface(self):
        errors = []
        rows = parse_features('UNITS=MM\nF 1\nS P 0\nOB 0 0 I\nOS 0 0\nOS 1 0\nOS 1 1\nOS 0 0\nOE\nSE', 'top', 'MM', lambda *args: errors.append(args))
        self.assertFalse(errors)
        self.assertEqual(len(rows[0]["boundary_rings"][0]["segments"]), 3)

    def test_unix_compress_encoding_is_an_explicit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "features.Z").write_bytes(b"\x1f\x9d\x90")
            with SourcePackage(directory) as package:
                with self.assertRaisesRegex(ValueError, r"Unix compress \(\.Z\)"):
                    package.text("features")

if __name__ == "__main__": unittest.main()
