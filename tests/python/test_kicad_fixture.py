import os
import unittest
from pathlib import Path

from python.spike_core.service import _design_from_kicad, handle, validate_design
from python.spike_core.peec_plugin import native_available
from python.spike_core.contracts import AnalysisSpec
from python.spike_core.convergence import run_mesh_convergence
from python.spike_core.solver_plugins import default_solver_registry


FIXTURE_PROFILES = {
    "ebrake1": {
        "minimum_counts": {
            "nets": 80,
            "tracks": 700,
            "vias": 90,
            "pads": 450,
            "zones": 150,
            "components": 100,
            "stackup": 10,
        },
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
        "ac_geometry_counts": {"track": 8, "zone": 2, "via": 1, "pad": 4},
    },
    "modular-bus-nib": {
        "minimum_counts": {
            "nets": 46,
            "tracks": 404,
            "vias": 617,
            "pads": 260,
            "zones": 160,
            "components": 90,
            "stackup": 17,
        },
        "dc_spec": {
            "mode": "dc",
            "net_names": ["/12Vout"],
            "sources": [{
                "id": "r19-output",
                "position_mm": [160.132, 81.66],
                "layer": "F.Cu",
                "voltage_v": 12.0,
            }],
            "loads": [
                {
                    "id": "j14-output",
                    "position_mm": [165.025, 78.2],
                    "layer": "F.Cu",
                    "current_a": 10.0 / 3.0,
                },
                {
                    "id": "j20-output",
                    "position_mm": [165.025, 82.275],
                    "layer": "F.Cu",
                    "current_a": 10.0 / 3.0,
                },
                {
                    "id": "j15-output",
                    "position_mm": [165.025, 86.35],
                    "layer": "F.Cu",
                    "current_a": 10.0 / 3.0,
                },
            ],
            "mesh": {"target_size_mm": 1.0, "max_conductors": 10000},
            "limits": {"max_voltage_drop_mv": 50},
        },
        "ac_spec": {
            "mode": "ac",
            "solver_id": "spike.peec_2_5d",
            "formulation": "peec_2_5d",
            "net_names": ["/12Vout"],
            "sources": [{
                "id": "r19-output",
                "position_mm": [160.132, 81.66],
                "layer": "F.Cu",
            }],
            "loads": [{
                "id": "j20-output",
                "position_mm": [165.025, 82.275],
                "layer": "F.Cu",
            }],
            "frequency_start_hz": 1e3,
            "frequency_stop_hz": 1e5,
            "frequency_points": 3,
            "mesh": {
                "target_size_mm": 5.0,
                "zone_cell_mm": 5.0,
                "max_zone_cells": 1000,
                "max_conductors": 2000,
            },
        },
        "ac_geometry_counts": {"track": 33, "zone": 7, "via": 76, "pad": 22},
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
        counts = self.profile["minimum_counts"]
        for field, minimum in counts.items():
            self.assertGreaterEqual(len(getattr(design, field)), minimum, field)
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
        self.assertEqual(report["status"], "passed")
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
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            result["summary"]["geometry_counts"],
            self.profile["ac_geometry_counts"],
        )
        self.assertGreater(result["summary"]["resistance_start_ohm"], 0)
        self.assertGreater(result["summary"]["partial_inductance_h"], 0)


if __name__ == "__main__":
    unittest.main()
