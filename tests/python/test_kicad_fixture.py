import os
import unittest
from collections import Counter
from pathlib import Path

from python.spike_core.service import _design_from_kicad, handle, validate_design
from python.spike_core.peec_plugin import native_available
from python.spike_core.contracts import AnalysisSpec
from python.spike_core.convergence import run_mesh_convergence
from python.spike_core.solver_plugins import default_solver_registry


FIXTURE_PROFILES = {
    "ebrake1": {
        # Independent KiCad 10.0.6 inventory; see
        # docs/validation/EBRAKE_FIXTURE_QUALIFICATION_20261019.md.
        "source_sha256": "d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca",
        "minimum_counts": {
            "nets": 80,
            "tracks": 700,
            "vias": 90,
            "pads": 450,
            "components": 100,
            "stackup": 10,
        },
        "filled_zone_layers": {
            "3110c870-71c4-4885-b8ca-f76016cd3a52": {"F.Cu": 1},
            "9c88fc49-1ddd-49e5-84f4-275ca82131d2": {"F.Cu": 1},
            "2c3f1b1c-0171-4db4-9179-13867a4c75fa": {"F.Cu": 1, "B.Cu": 1},
            "0cb49f67-e064-4728-9668-e6dd455be214": {"F.Cu": 1, "B.Cu": 2, "In1.Cu": 1, "In2.Cu": 1},
            "456e478a-4b71-4f6e-9e2f-a770ccf7db69": {"F.Cu": 1, "B.Cu": 1, "In1.Cu": 2, "In2.Cu": 1},
            "8319d80f-a16f-437e-8a4d-b5ddfe687501": {"F.Cu": 1, "B.Cu": 1, "In1.Cu": 1, "In2.Cu": 1},
            "3e92eaae-cc72-46d6-841f-64a3ea5ffdd5": {"B.Cu": 1},
            "6398ebd9-7882-40fa-8944-cf87f97795f8": {"B.Cu": 1},
            "989b1b2f-c00d-4f18-9138-3bcef7fbc5e4": {"B.Cu": 1},
            "9a8c62d9-1a90-4414-9d24-b9def4ab082d": {"B.Cu": 1},
            "a7ad4cdd-aafd-499b-b6f6-d8d5a6e96a54": {"B.Cu": 1},
            "c7757bbe-17ec-474f-9f97-0dab53be7151": {"B.Cu": 1},
            "f506a9f0-f2ea-4e6f-b5b4-7f868f43e5ae": {"B.Cu": 1},
            "f67bf072-6636-4e2c-a3a4-009107466d33": {"B.Cu": 1},
        },
        "copper_graphics": {("388e6d16-82ed-4c7b-b385-33da3fae27dd", "F.Cu"): 1},
        "dc_spec": {
            "mode": "dc",
            "net_names": ["3Vin"],
            "sources": [{
                "id": "fixture-source",
                "position_mm": [165.1, 116.3],
                "layer": "B.Cu",
                "voltage_v": 24.0,
            }],
            "loads": [{
                "id": "fixture-load",
                "position_mm": [149.05, 116.3],
                "layer": "B.Cu",
                "current_a": 1.0,
            }],
            "limits": {"max_voltage_drop_mv": 50},
        },
        "ac_spec": {
            "mode": "ac",
            "solver_id": "spike.peec_2_5d",
            "formulation": "peec_2_5d",
            "net_names": ["/AOUT1"],
            "frequency_start_hz": 1e3,
            "frequency_stop_hz": 1e5,
            "frequency_points": 3,
            "mesh": {
                "target_size_mm": 1.5,
                "zone_cell_mm": 1.0,
                "max_zone_cells": 1000,
                "max_conductors": 1200,
            },
        },
        "ac_geometry_counts": {"track": 8, "zone": 1, "via": 1, "pad": 4},
    },
}


class KicadFixtureTests(unittest.TestCase):
    """Run the real-board regression when SPIKE_FIXTURE_BOARD is configured."""

    @classmethod
    def setUpClass(cls):
        value = os.environ.get("SPIKE_FIXTURE_BOARD")
        if not value:
            raise unittest.SkipTest("Set SPIKE_FIXTURE_BOARD to run the external KiCad fixture")
        cls.board = Path(value)
        if not cls.board.exists():
            raise unittest.SkipTest(f"Fixture does not exist: {cls.board}")
        cls.profile = FIXTURE_PROFILES.get(cls.board.stem.lower())
        if cls.profile is None:
            supported = ", ".join(sorted(FIXTURE_PROFILES))
            raise unittest.SkipTest(
                f"No regression profile for {cls.board.name}; supported fixtures: {supported}"
            )

    def test_board_extracts_expected_geometry(self):
        design = _design_from_kicad(str(self.board))
        self.assertEqual(design.metadata["source_sha256"], self.profile["source_sha256"])
        counts = self.profile["minimum_counts"]
        for field, minimum in counts.items():
            self.assertGreaterEqual(len(getattr(design, field)), minimum, field)
        filled = [zone for zone in design.zones if zone.get("source_kind") == "filled_zone"]
        self.assertEqual(
            Counter((zone["source_zone_id"], zone["layer"]) for zone in filled),
            Counter({(source, layer): count
                     for source, layers in self.profile["filled_zone_layers"].items()
                     for layer, count in layers.items()}),
        )
        self.assertTrue(all(zone["filled_copper_state"] == "source_filled" for zone in filled))
        self.assertEqual(len({zone["id"] for zone in filled}), len(filled))
        self.assertEqual(
            Counter((zone["id"], zone["layer"]) for zone in design.zones
                    if zone.get("source_kind") != "filled_zone"),
            Counter(self.profile["copper_graphics"]),
        )
        net_names = {item["id"]: item["name"] for item in design.nets}
        self.assertTrue(all(track["net_name"] == net_names[track["net_id"]] for track in design.tracks))
        self.assertTrue(all(via["net_name"] == net_names[via["net_id"]] for via in design.vias))
        validation = validate_design(design)
        self.assertTrue(validation["valid"])

    def test_routed_dc_path_returns_an_approximate_result(self):
        design = _design_from_kicad(str(self.board))
        response = handle({
            "method": "run_analysis",
            "params": {
                "design": design.to_dict(),
                "spec": self.profile["dc_spec"],
            },
        })
        result = response["result"]
        self.assertTrue(response["ok"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_status"], "approximate")
        self.assertGreater(result["summary"]["max_voltage_drop_v"], 0)

    def test_routed_dc_mesh_convergence_signs_off(self):
        design = _design_from_kicad(str(self.board))
        report = run_mesh_convergence(
            design,
            AnalysisSpec(**self.profile["dc_spec"]),
            default_solver_registry().run,
            levels=[2, 1, 0.5, 0.25],
            minimum_levels=3,
        )
        self.assertEqual(report["status"], "passed", report["comparisons"])
        self.assertTrue(report["can_sign_off"])
        self.assertTrue(all(
            item["status"] == "passed"
            for item in report["comparisons"]
            if item["required"]
        ))

    @unittest.skipUnless(native_available(), "Native PEEC extension is not built")
    def test_hybrid_net_runs_through_native_peec(self):
        design = _design_from_kicad(str(self.board))
        response = handle({
            "method": "run_analysis",
            "params": {
                "design": design.to_dict(),
                "spec": self.profile["ac_spec"],
            },
        })
        result = response["result"]
        self.assertEqual(result["status"], "completed", result["issues"])
        self.assertEqual(
            result["summary"]["geometry_counts"],
            self.profile["ac_geometry_counts"],
        )
        self.assertGreater(result["summary"]["resistance_start_ohm"], 0)
        self.assertGreater(result["summary"]["partial_inductance_h"], 0)


if __name__ == "__main__":
    unittest.main()
