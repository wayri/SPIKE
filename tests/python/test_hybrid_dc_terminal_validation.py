"""Physical terminal evidence for DC source-to-load paths."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.sparse import csr_matrix

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_dc_solver import solve_hybrid_dc
from python.spike_core.dc_terminal_validation import build_source_to_load_evidence, terminal_copper_weights
from python.spike_core.hybrid_mesh import HybridMesh, MeshBranch, MeshNode
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
    def test_conductor_currents_are_invariant_to_absolute_source_offset(self) -> None:
        reference = _line_spec()
        shifted = _line_spec()
        shifted.sources[0]["voltage_v"] = 1e9
        low = solve_hybrid_dc(_line_design(), reference)
        high = solve_hybrid_dc(_line_design(), shifted)
        self.assertEqual((low.status, high.status), ("completed", "completed"))
        self.assertAlmostEqual(low.summary["total_copper_loss_w"], high.summary["total_copper_loss_w"], places=14)
        self.assertAlmostEqual(low.networks["source_to_load"]["source_current_balance_a"],
                               high.networks["source_to_load"]["source_current_balance_a"], places=12)

    def test_source_kcl_uses_branch_currents_without_absolute_voltage_cancellation(self) -> None:
        voltage = np.array([12.0, 12.0 - 1e-11])
        current = float((voltage[0] - voltage[1]) * 1e12)
        source = {"id": "source", "role": "source_positive", "domain_id": "default",
                  "net": "VCC", "geometry_anchor_id": "pad-source", "node": 0, "boundary_nodes": [0]}
        load = {"id": "load", "role": "load_positive", "domain_id": "default",
                "net": "VCC", "geometry_anchor_id": "pad-load", "node": 1, "boundary_nodes": [1],
                "pair_id": "load", "current_a": current}
        conductance = csr_matrix([[1e12, -1e12], [-1e12, 1e12]])
        # Matrix multiplication loses low-order digits in the 12 V products;
        # the solved branch current remains the correct graph KCL quantity.
        self.assertGreater(abs(float((conductance @ voltage)[0]) - current), 1e-4)
        evidence = build_source_to_load_evidence(
            [source], [load], voltage, np.array([0.0, -current]), 0.0, False,
            [{"a": 0, "b": 1, "current_a": current}],
        )
        self.assertEqual(evidence["status"], "validated")
        self.assertAlmostEqual(evidence["source_current_balance_a"], 0.0, places=12)

    @staticmethod
    def _parallel_contact_mesh(split: bool) -> HybridMesh:
        # Two parallel copper paths partitioned in the same 1:3 area ratio.
        # R_i = 0.5 / w_i ohm, so subdivision preserves 0.5 ohm in parallel.
        weights = [0.25, 0.75] if split else [1.0]
        mesh = HybridMesh(nodes=[MeshNode(0, 0, 0, 0, "F.Cu", "VCC")])
        mesh.branches.append(MeshBranch(
            "source-node", "via", 0, 0, (0, 0, 0), (0, 0, 0),
            1, 1, 1000, "F.Cu", "VCC", "source-anchor",
        ))
        for index, weight in enumerate(weights, 1):
            mesh.nodes.append(MeshNode(index, index, 0, 0, "F.Cu", "VCC"))
            mesh.branches.append(MeshBranch(
                f"copper-{index}", "track", 0, index, (0, 0, 0), (index, 0, 0),
                index * weight / 0.5, 1, 1000, "F.Cu", "VCC", "copper",
            ))
            mesh.cells.append({
                "id": f"pad-cell-{index}", "kind": "surface",
                "source_kind": "pad", "source_id": "load-pad", "node_id": index,
                "layer": "F.Cu", "net": "VCC",
                "vertices_mm": [[index, 0, 0], [index + weight, 0, 0],
                                [index + weight, 1, 0], [index, 1, 0]],
            })
        mesh.branches.append(MeshBranch(
            "pad-link", "pad", 1, len(weights), (1, 0, 0), (len(weights), 0, 0),
            1, 1, 1000, "F.Cu", "VCC", "load-pad",
        ))
        return mesh

    def test_pad_area_subdivision_preserves_current_contact_drop_and_energy(self) -> None:
        for resistance in (0.0, 0.1):
            for split in (False, True):
                with self.subTest(contact_resistance=resistance, split=split):
                    spec = AnalysisSpec(
                        mode="dc", net_names=["VCC"],
                        sources=[{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5,
                                  "geometry_anchor": {"type": "via", "id": "source-anchor"}}],
                        loads=[{"position_mm": [1, 0], "layer": "F.Cu", "current_a": 1,
                                "geometry_anchor": {"type": "pad", "id": "load-pad"},
                                "contact_resistance_ohm": resistance}],
                        options={"require_exact_terminal_geometry": True},
                    )
                    with patch("python.spike_core.hybrid_dc_solver.build_hybrid_mesh",
                               return_value=self._parallel_contact_mesh(split)):
                        result = solve_hybrid_dc(DesignIR(), spec)
                    self.assertEqual(result.status, "completed")
                    self.assertAlmostEqual(result.summary["max_load_voltage_drop_v"], 0.5 + resistance, places=10)
                    self.assertAlmostEqual(result.summary["geometry_power_loss_w"]["track"], 0.5, places=10)
                    self.assertAlmostEqual(result.summary["total_copper_loss_w"], 0.5, places=10)
                    self.assertAlmostEqual(result.summary["total_network_loss_w"], 0.5 + resistance, places=10)
                    self.assertAlmostEqual(result.networks["source_to_load"]["source_current_balance_a"], 0, places=10)

    def test_pad_boundary_excludes_zone_attachment_and_requires_cell_ownership(self) -> None:
        mesh = self._parallel_contact_mesh(True)
        mesh.nodes.append(MeshNode(3, 4, 0, 0, "F.Cu", "VCC"))
        mesh.branches.append(MeshBranch(
            "zone-link", "pad_zone_attachment", 2, 3, (2, 0, 0), (4, 0, 0),
            1, 1, 1000, "F.Cu", "VCC", "load-pad",
        ))
        terminal = {"position_mm": [1, 0], "layer": "F.Cu",
                    "geometry_anchor": {"type": "pad", "id": "load-pad"}}
        spec = AnalysisSpec(net_names=["VCC"])
        self.assertEqual(terminal_copper_weights(mesh, spec, terminal, True), {1: 0.25, 2: 0.75})
        self.assertEqual(terminal_copper_weights(mesh, spec, terminal, False), {1: 1/3, 2: 1/3, 3: 1/3})
        del mesh.cells[0]["node_id"]
        self.assertEqual(terminal_copper_weights(mesh, spec, terminal, True), {})
        for vertices in ([], [[0, 0]], [[0, 0], [1, 0], [float("nan"), 1]],
                         [[0, 0], [1, 0], [float("inf"), 1]], [[0, 0], [1, 0], [2, 0]]):
            with self.subTest(vertices=vertices):
                mesh.cells[0]["node_id"] = 1
                mesh.cells[0]["vertices_mm"] = vertices
                self.assertEqual(terminal_copper_weights(mesh, spec, terminal, True), {})
        mesh.cells.clear()
        self.assertEqual(terminal_copper_weights(mesh, spec, terminal, True), {})

    def test_area_weighted_voltage_is_power_conjugate_to_injected_current(self) -> None:
        mesh = self._parallel_contact_mesh(True)
        # Both path resistances are now 1 ohm, joined by another 1 ohm pad link.
        # With sinks 1/4 A and 3/4 A, KCL gives drops 5/12 V and 7/12 V.
        # The power-conjugate terminal drop is (1/4*5 + 3/4*7)/12 = 13/24 V.
        for index, branch in enumerate(mesh.branches[1:3], 1):
            branch.width_mm = index
        spec = AnalysisSpec(
            mode="dc", net_names=["VCC"],
            sources=[{"position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5,
                      "geometry_anchor": {"type": "via", "id": "source-anchor"}}],
            loads=[{"position_mm": [1, 0], "layer": "F.Cu", "current_a": 1,
                    "geometry_anchor": {"type": "pad", "id": "load-pad"}}],
            options={"require_exact_terminal_geometry": True},
        )
        with patch("python.spike_core.hybrid_dc_solver.build_hybrid_mesh", return_value=mesh):
            result = solve_hybrid_dc(DesignIR(), spec)
        expected = 13 / 24
        self.assertEqual(result.status, "completed")
        self.assertAlmostEqual(result.summary["max_load_voltage_drop_v"], expected, places=10)
        self.assertAlmostEqual(result.summary["total_network_loss_w"], expected, places=10)
        self.assertAlmostEqual(result.networks["source_to_load"]["paths"][0]["supply_drop_v"], expected, places=10)

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
