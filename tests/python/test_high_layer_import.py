import tempfile
import unittest
from pathlib import Path

from python.spike_core.layers import copper_stack_profile
from python.spike_core.service import _design_from_kicad


COPPER_NAMES = ["F.Cu", *[f"In{index}.Cu" for index in range(1, 31)], "B.Cu"]


def high_layer_board() -> str:
    rows = []
    for index, name in enumerate(COPPER_NAMES):
        layer_id = 0 if name == "F.Cu" else 2 if name == "B.Cu" else (index + 1) * 2
        user_name = ' "MEMORY_PWR"' if name == "In10.Cu" else ""
        layer_type = "power" if index % 3 == 0 else "signal"
        rows.append(f'    ({layer_id} "{name}" {layer_type}{user_name})')
    return "\n".join([
        "(kicad_pcb",
        "  (version 20241229)",
        "  (generator pcbnew)",
        "  (layers",
        *rows,
        '    (25 "Edge.Cuts" user)',
        "  )",
        "  (setup (stackup",
        '    (layer "F.Cu" (type "copper") (thickness 0.035))',
        '    (layer "dielectric 1" (type "core") (thickness 1.53) (material "FR4") (epsilon_r 4.2))',
        '    (layer "B.Cu" (type "copper") (thickness 0.035))',
        "  ))",
        '  (net 0 "")',
        '  (net 1 "VCC")',
        '  (segment (start 1 1) (end 9 1) (width 0.25) (layer "In30.Cu") (net 1))',
        ")",
    ])


class HighLayerImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.board_path = Path(self.temporary.name) / "thirty-two-layer.kicad_pcb"
        self.board_path.write_text(high_layer_board(), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_layer_table_is_complete_and_physically_ordered(self):
        design = _design_from_kicad(str(self.board_path))
        imported_copper = [layer["name"] for layer in design.layers if layer["name"].endswith(".Cu")]

        self.assertEqual(imported_copper, COPPER_NAMES)
        self.assertEqual(design.metadata["copper_layer_count"], 32)
        self.assertEqual(design.tracks[0]["layer"], "In30.Cu")
        self.assertEqual(
            next(layer for layer in design.layers if layer["name"] == "In10.Cu")["user_name"],
            "MEMORY_PWR",
        )

    def test_partial_stackup_does_not_remove_solver_layers(self):
        design = _design_from_kicad(str(self.board_path))
        names, z_by_layer, thickness_by_layer = copper_stack_profile(design)

        self.assertEqual(names, COPPER_NAMES)
        self.assertEqual(set(z_by_layer), set(COPPER_NAMES))
        self.assertEqual(set(thickness_by_layer), set(COPPER_NAMES))
        self.assertTrue(all(z_by_layer[left] > z_by_layer[right] for left, right in zip(names, names[1:])))
        self.assertEqual(
            design.metadata["stackup_missing_copper_layers"],
            COPPER_NAMES[1:-1],
        )
        self.assertIn(
            "STACKUP_COPPER_LAYERS_MISSING",
            {issue.code for issue in design.issues},
        )


if __name__ == "__main__":
    unittest.main()
