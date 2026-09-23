import tempfile
import unittest
from pathlib import Path

from python.spike_core.contracts import AnalysisSpec
from python.spike_core.geometry import extract_net_geometry
from python.spike_core.service import _design_from_kicad
from python.spike_core.solver_geometry import build_solver_geometry


RIGID_FLEX_BOARD = """(kicad_pcb
  (version 20240108)
  (generator pcbnew)
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "User.1" user "Flex Region")
    (37 "User.2" user "Bend R1.5 A90")
    (44 "Edge.Cuts" user)
  )
  (net 0 "")
  (net 1 "VCC")
  (gr_line (start 0 0) (end 10 0) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))
  (gr_line (start 10 0) (end 10 10) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))
  (gr_line (start 10 10) (end 0 10) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))
  (gr_line (start 0 10) (end 0 0) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))
  (gr_rect (start 0 0) (end 4 10) (stroke (width 0.05) (type default)) (fill none) (layer "User.1"))
  (gr_line (start 2 0) (end 2 10) (stroke (width 0.05) (type default)) (layer "User.2"))
  (segment (start 1 5) (end 9 5) (width 0.5) (layer "F.Cu") (net 1))
)"""


class RigidFlexImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.board_path = Path(self.temporary.name) / "rigid-flex.kicad_pcb"
        self.board_path.write_text(RIGID_FLEX_BOARD, encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_kicad_regions_and_bends_reach_design_ir(self):
        design = _design_from_kicad(str(self.board_path))

        self.assertEqual(design.technology, "rigid-flex")
        self.assertEqual(len(design.regions), 1)
        self.assertEqual(design.regions[0]["kind"], "flex")
        self.assertAlmostEqual(design.regions[0]["outline"][1][0], 4.0)
        self.assertEqual(len(design.bends), 1)
        self.assertAlmostEqual(design.bends[0]["radius_mm"], 1.5)
        self.assertAlmostEqual(design.bends[0]["angle_deg"], 90.0)

    def test_rigid_flex_metadata_survives_solver_exchange(self):
        design = _design_from_kicad(str(self.board_path))
        net_geometry = extract_net_geometry(design, "VCC")
        bundle = build_solver_geometry(
            design,
            AnalysisSpec(mode="dc", net_names=["VCC"]),
        )

        self.assertEqual(net_geometry["technology"], "rigid-flex")
        self.assertEqual(net_geometry["regions"], design.regions)
        self.assertEqual(net_geometry["bends"], design.bends)
        self.assertEqual(bundle["assembly"]["technology"], "rigid-flex")
        self.assertEqual(bundle["assembly"]["regions"], design.regions)
        self.assertEqual(bundle["counts"]["bends"], 1)


if __name__ == "__main__":
    unittest.main()
