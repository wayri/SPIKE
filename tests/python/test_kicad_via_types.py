import tempfile
import unittest
from pathlib import Path

from python.core.board_parser import KicadParser
from python.spike_core.kicad_importer import import_kicad_design


LAYERS = '''
  (layers
    (0 "F.Cu" signal)
    (2 "In1.Cu" power)
    (4 "In2.Cu" power)
    (6 "In3.Cu" power)
    (31 "B.Cu" signal))
'''


class KicadViaTypeTests(unittest.TestCase):
    def write_board(self, vias: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "via-types.kicad_pcb"
        path.write_text(
            "(kicad_pcb (version 20260101)" + LAYERS + "(net 1 \"VCC\")" + vias + ")",
            encoding="utf-8",
        )
        return path

    def test_source_proven_via_types_and_spans_survive_parser_and_import(self):
        path = self.write_board('''
          (via (at 1 1) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 1) (uuid "through"))
          (via blind (at 2 2) (size 0.3) (drill 0.1) (layers "F.Cu" "In1.Cu") (net 1) (uuid "blind"))
          (via blind (at 3 3) (size 0.3) (drill 0.1) (layers "In1.Cu" "In3.Cu") (net 1) (uuid "buried"))
          (via micro (at 4 4) (size 0.2) (drill 0.1) (layers "B.Cu" "In3.Cu") (net 1) (uuid "microvia"))
        ''')

        parser = KicadParser(path)
        self.assertFalse(parser.diagnostics)
        self.assertEqual(
            [(via["id"], via["type"], via["layers"]) for via in parser.vias],
            [
                ("through", "through", ("F.Cu", "B.Cu")),
                ("blind", "blind", ("F.Cu", "In1.Cu")),
                ("buried", "buried", ("In1.Cu", "In3.Cu")),
                ("microvia", "microvia", ("B.Cu", "In3.Cu")),
            ],
        )
        self.assertTrue(all(via["start_layer"] == via["layers"][0] for via in parser.vias))
        self.assertTrue(all(via["end_layer"] == via["layers"][1] for via in parser.vias))

        design = import_kicad_design(str(path))
        self.assertEqual(
            [(via["id"], via["type"], tuple(via["layers"])) for via in design.vias],
            [
                ("through", "through", ("F.Cu", "B.Cu")),
                ("blind", "blind", ("F.Cu", "In1.Cu")),
                ("buried", "buried", ("In1.Cu", "In3.Cu")),
                ("microvia", "microvia", ("B.Cu", "In3.Cu")),
            ],
        )

    def test_unproven_or_invalid_type_span_combinations_are_diagnosed_and_excluded(self):
        invalid_vias = {
            "untyped partial span": '(via (at 1 1) (size 0.8) (drill 0.4) (layers "F.Cu" "In1.Cu") (net 1))',
            "unknown type": '(via laser (at 1 1) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 1))',
            "blind through span": '(via blind (at 1 1) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 1))',
            "unsupported buried atom": '(via buried (at 1 1) (size 0.8) (drill 0.4) (layers "In1.Cu" "In2.Cu") (net 1))',
            "microvia non-adjacent span": '(via micro (at 1 1) (size 0.8) (drill 0.4) (layers "F.Cu" "In2.Cu") (net 1))',
            "microvia internal span": '(via micro (at 1 1) (size 0.8) (drill 0.4) (layers "In1.Cu" "In2.Cu") (net 1))',
            "missing span endpoint": '(via (at 1 1) (size 0.8) (drill 0.4) (layers "F.Cu") (net 1))',
            "undeclared span layer": '(via (at 1 1) (size 0.8) (drill 0.4) (layers "F.Cu" "NoSuch.Cu") (net 1))',
        }
        for name, via in invalid_vias.items():
            with self.subTest(name=name):
                parser = KicadParser(self.write_board(via))
                self.assertEqual(parser.vias, [])
                self.assertEqual(len(parser.diagnostics), 1)
                self.assertIn("Unable to parse via", parser.diagnostics[0])


if __name__ == "__main__":
    unittest.main()
