"""Visual exports must retain hidden source layers for independent toggling."""
import tempfile
import unittest
from pathlib import Path

from python.spike_core.models import _board_layers, _copper_layers


class VisualLayerInventoryTests(unittest.TestCase):
    def test_legacy_hidden_back_copper_is_still_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / "legacy.kicad_pcb"
            board.write_text('(kicad_pcb (layers (0 F.Cu signal) '
                             '(31 B.Cu signal hide) (44 Edge.Cuts user hide)))')
            self.assertEqual(_board_layers(board), ["F.Cu", "B.Cu", "Edge.Cuts"])
            self.assertEqual(_copper_layers(board), ["F.Cu", "B.Cu"])

    def test_quoted_custom_layer_labels_do_not_replace_canonical_names(self):
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / "modern.kicad_pcb"
            board.write_text('(kicad_pcb (layers (0 "F.Cu" signal "Top") '
                             '(2 "In1.Cu" power "Ground plane") '
                             '(31 "B.Cu" signal "Bottom") (44 "Edge.Cuts" user)))')
            self.assertEqual(_copper_layers(board), ["F.Cu", "In1.Cu", "B.Cu"])
