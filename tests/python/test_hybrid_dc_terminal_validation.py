"""Physical terminal evidence for DC source-to-load paths."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_dc_solver import solve_hybrid_dc
from python.spike_core.kicad_importer import import_kicad_design


ROOT = Path(__file__).resolve().parents[2]


def _line_design() -> DesignIR:
    return DesignIR(
        layers=[{"name": "F.Cu"}],
        tracks=[
            {"id": "source-track", "start": [0, 0], "end": [5, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"},
            {"id": "load-track", "start": [5, 0], "end": [10, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"},
        ],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
    )


def _line_spec() -> AnalysisSpec:
    return AnalysisSpec(
        mode="dc", net_names=["VCC"],
        sources=[{"id": "source", "position_mm": [0, 0], "layer": "F.Cu", "net": "VCC", "voltage_v": 5,
                  "geometry_anchor": {"id": "source-track", "type": "track"}}],
        loads=[{"id": "load", "position_mm": [10, 0], "layer": "F.Cu", "net": "VCC", "current_a": 1,
                "geometry_anchor": {"id": "load-track", "type": "track"}}],
        options={"require_exact_terminal_geometry": True},
    )


class HybridDCTerminalValidationTests(unittest.TestCase):
    def test_exact_terminals_report_signed_solved_drop_and_current_balance(self) -> None:
        result = solve_hybrid_dc(_line_design(), _line_spec())
        self.assertEqual(result.status, "completed")
        evidence = result.networks["source_to_load"]
        self.assertEqual(evidence["status"], "validated")
        self.assertEqual(len(evidence["paths"]), 1)
        path = evidence["paths"][0]
        self.assertEqual((path["source_id"], path["load_id"]), ("source", "load"))
        self.assertGreater(path["supply_drop_v"], 0)
        self.assertAlmostEqual(path["source_voltage_v"] - path["load_voltage_v"], path["supply_drop_v"], places=12)
        self.assertAlmostEqual(evidence["source_current_balance_a"], 0, places=8)
        self.assertLess(result.summary["max_scaled_linear_residual"], 1e-10)

    def test_missing_or_wrong_anchor_fails_closed(self) -> None:
        for anchor in (None, {"id": "absent", "type": "track"}):
            with self.subTest(anchor=anchor):
                spec = _line_spec()
                if anchor is None:
                    del spec.loads[0]["geometry_anchor"]
                else:
                    spec.loads[0]["geometry_anchor"] = anchor
                result = solve_hybrid_dc(_line_design(), spec)
                self.assertEqual(result.status, "failed")
                self.assertNotIn("source_to_load", result.networks)

    def test_ambiguous_source_pair_fails_closed(self) -> None:
        spec = _line_spec()
        second = dict(spec.sources[0], id="second-source")
        spec.sources.append(second)
        result = solve_hybrid_dc(_line_design(), spec)
        self.assertEqual(result.status, "failed")
        self.assertIn("SPIKE-BE-PI-E-0007", {issue.code for issue in result.issues})

    def test_explicit_return_reports_signed_source_and_load_differentials(self) -> None:
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            tracks=[
                {"id": "supply-source", "start": [0, 0], "end": [5, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "supply-load", "start": [5, 0], "end": [10, 0], "width": 1, "layer": "F.Cu", "net_name": "VCC"},
                {"id": "return-source", "start": [0, 2], "end": [5, 2], "width": 1, "layer": "B.Cu", "net_name": "GND"},
                {"id": "return-load", "start": [5, 2], "end": [10, 2], "width": 1, "layer": "B.Cu", "net_name": "GND"},
            ],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric", "type": "core", "thickness": 1.53},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
        )
        spec = AnalysisSpec(
            mode="dc", net_names=["VCC", "GND"],
            sources=[
                {"id": "sp", "position_mm": [0, 0], "layer": "F.Cu", "net": "VCC", "voltage_v": 5,
                 "terminal_role": "source_positive", "geometry_anchor": {"id": "supply-source", "type": "track"}},
                {"id": "sr", "position_mm": [0, 2], "layer": "B.Cu", "net": "GND", "voltage_v": 0,
                 "terminal_role": "source_return", "geometry_anchor": {"id": "return-source", "type": "track"}},
            ],
            loads=[
                {"id": "lp", "position_mm": [10, 0], "layer": "F.Cu", "net": "VCC", "current_a": 1,
                 "terminal_role": "load_positive", "pair_id": "out", "geometry_anchor": {"id": "supply-load", "type": "track"}},
                {"id": "lr", "position_mm": [10, 2], "layer": "B.Cu", "net": "GND", "current_a": -1,
                 "terminal_role": "load_return", "pair_id": "out", "geometry_anchor": {"id": "return-load", "type": "track"}},
            ],
            return_path={"mode": "explicit", "net": "GND"},
            options={"require_exact_terminal_geometry": True},
        )
        result = solve_hybrid_dc(design, spec)
        self.assertEqual(result.status, "completed")
        evidence = result.networks["source_to_load"]
        self.assertEqual(evidence["status"], "validated")
        path = evidence["paths"][0]
        self.assertAlmostEqual(path["source_differential_v"], 5, places=12)
        self.assertLess(path["load_differential_v"], 5)
        self.assertAlmostEqual(path["loop_drop_v"], path["source_differential_v"] - path["load_differential_v"], places=12)
        self.assertAlmostEqual(evidence["source_current_balance_a"], 0, places=8)

    def test_repo_pinned_modular_bus_nib_source_to_three_loads(self) -> None:
        board = ROOT / "app" / "public" / "demo" / "MODULAR-BUS-NIB.kicad_pcb"
        design = import_kicad_design(str(board))
        pads = {pad["component_pad"]: pad for pad in design.pads if pad.get("component_pad")}
        request = json.loads((ROOT / "docs" / "validation" / "modular-bus-nib-12vout-dcir-request.json").read_text())
        spec_data = request["spec"]
        spec_data["mesh"]["zone_cell_mm"] = 1.0
        spec_data["options"] = {"require_exact_terminal_geometry": True}
        spec_data["sources"][0]["geometry_anchor"] = {"id": pads["R19.3"]["id"], "type": "pad"}
        for load, name in zip(spec_data["loads"], ("J14.2", "J20.2", "J15.2")):
            load["geometry_anchor"] = {"id": pads[name]["id"], "type": "pad"}
        result = solve_hybrid_dc(design, AnalysisSpec(**spec_data))
        self.assertEqual(result.status, "completed", [(issue.code, issue.message) for issue in result.issues])
        evidence = result.networks["source_to_load"]
        self.assertEqual(evidence["status"], "validated")
        self.assertEqual(len(evidence["paths"]), 3)
        self.assertEqual(len(evidence["terminal_voltages"]), 4)
        self.assertAlmostEqual(sum(path["load_current_a"] for path in evidence["paths"]), 10, places=8)
        self.assertLess(abs(evidence["source_current_balance_a"]), 1e-7)
        self.assertLess(result.summary["max_scaled_linear_residual"], 1e-10)
        for path in evidence["paths"]:
            self.assertGreater(path["supply_drop_v"], 0)
            self.assertLess(path["supply_drop_v"], 0.02)
            self.assertAlmostEqual(path["source_voltage_v"] - path["load_voltage_v"], path["supply_drop_v"], places=12)


if __name__ == "__main__":
    unittest.main()
