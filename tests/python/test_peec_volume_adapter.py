# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Runtime admission and topology-overlay checks for finite-volume PEEC."""

import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import MeshBranch, build_hybrid_mesh, nearest_mesh_node
from python.spike_core.peec_plugin import _connected_component
from python.spike_core.peec_volume_adapter import (
    VolumeResistanceOverlay, extract_volume_matrices,
)
from python.spike_core.quasistatic_capacitance import zone_pad_mesh_dependence_issue
from python.spike_core.transient_peec import solve_peec_rl_transient
from python.spike_core.service import _design_from_kicad

try:
    from python import spike_peec_native as native
except ImportError:
    native = None


def _track(name, start=(0.0, 0.0), end=(1.0, 0.0)):
    return MeshBranch(name, "track", 0, 1, (*start, 0.0), (*end, 0.0),
                      0.2, 0.035, 5.8e7, "F.Cu", "N", name)


class _NativeResistance:
    def compute_resistance(self, frequency):
        return np.array([[2.0 + frequency, 0.0, 0.0],
                         [0.0, 4.0 + 2.0 * frequency, 0.0],
                         [0.0, 0.0, 8.0]], dtype=float)


class VolumeAdapterTests(unittest.TestCase):
    def test_mesh_dependent_zone_capacitance_is_explicitly_warned(self):
        branches = [SimpleNamespace(kind="track"), SimpleNamespace(kind="zone")]
        self.assertIsNone(zone_pad_mesh_dependence_issue(branches, [0, 1], False))
        self.assertIsNone(zone_pad_mesh_dependence_issue(branches, [0], True))
        issue = zone_pad_mesh_dependence_issue(branches, [0, 1], True)
        self.assertEqual(issue.code, "PEEC_ZONE_PAD_CAPACITANCE_MESH_DEPENDENT")

    def test_unavailable_backend_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unavailable"):
            extract_volume_matrices(object(), DesignIR(), [_track("a")])

    def test_overlay_replaces_physical_dc_and_preserves_skin_increment(self):
        overlay = VolumeResistanceOverlay(_NativeResistance(), [0, 1],
                                          np.array([[1.0, 0.3], [0.3, 3.0]]))
        np.testing.assert_allclose(overlay.compute_resistance(0.0),
            [[1.0, 0.3, 0.0], [0.3, 3.0, 0.0], [0.0, 0.0, 8.0]])
        np.testing.assert_allclose(overlay.compute_resistance(5.0),
            [[6.0, 0.3, 0.0], [0.3, 13.0, 0.0], [0.0, 0.0, 8.0]])

    def test_overlay_rejects_wrong_matrix_dimension(self):
        with self.assertRaisesRegex(ValueError, "incompatible"):
            VolumeResistanceOverlay(_NativeResistance(), [0, 1], np.eye(3))

    @unittest.skipUnless(native is not None and hasattr(native, "VolumeMatrixAssembler"),
                         "native volume PEEC extension required")
    def test_duplicate_and_reversed_volume_bases_have_nonnegative_energy(self):
        branches = [_track("a"), _track("b"),
                    _track("c", (1.0, 0.0), (0.0, 0.0))]
        matrices = extract_volume_matrices(native, DesignIR(), branches)
        signs = np.array([1.0, 1.0, -1.0])
        np.testing.assert_allclose(matrices.inductance_h,
            matrices.inductance_h[0, 0] * np.outer(signs, signs),
            rtol=1e-10, atol=1e-18)
        np.testing.assert_allclose(matrices.dc_resistance_ohm,
            matrices.dc_resistance_ohm[0, 0] * np.outer(signs, signs),
            rtol=1e-12, atol=1e-17)
        self.assertGreater(matrices.inductance_h[0, 0], 0.0)
        self.assertEqual(matrices.quality["pair_count"], 6)
        self.assertEqual(matrices.quality["maximum_matrix_pairs"], 8192)
        self.assertEqual(matrices.quality["maximum_pair_potential_evaluations"], 2_000_000)
        self.assertGreaterEqual(float(np.linalg.eigvalsh(matrices.inductance_h)[0]), -1e-18)

    @unittest.skipUnless(native is not None and hasattr(native, "VolumeMatrixAssembler"),
                         "native volume PEEC extension required")
    def test_opted_in_transient_uses_real_volume_backend(self):
        design = DesignIR(
            name="short copper transient", layers=[{"name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{"id": "trace", "start": [0.0, 0.0], "end": [2.0, 0.0],
                     "width": 0.2, "layer": "F.Cu", "net_name": "VCC"}],
            stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        )
        spec = AnalysisSpec(
            mode="transient", solver_id="spike.peec_rl_transient",
            formulation="peec_rl_transient", net_names=["VCC"],
            options={"peec_volume_extraction": "enabled"},
            sources=[{"id": "source", "position_mm": [0.0, 0.0],
                      "layer": "F.Cu", "net": "VCC", "voltage_v": 1.0}],
            loads=[{"id": "load", "position_mm": [2.0, 0.0],
                    "layer": "F.Cu", "net": "VCC", "current_a": 0.01}],
            transient={"stop_time_s": 2e-7, "time_step_s": 1e-8,
                       "output_decimation": 2, "initial_condition": "operating_point"},
            mesh={"target_size_mm": 1.0, "max_preview_cells": 100},
        )
        result = solve_peec_rl_transient(design, spec)
        self.assertEqual(result.status, "completed", [issue.code for issue in result.issues])
        self.assertEqual(result.model_status, "approximate")
        self.assertEqual(result.provenance["volume_current_model"],
                         "uniform_volume_current")
        self.assertGreater(result.provenance["volume_extraction"]["pair_count"], 0)

    def test_optional_marble_ports_reflect_copper_connectivity(self):
        board = (Path(__file__).resolve().parents[2] / "build" / "marble-qualification"
                 / "sources" / "Marble-v1.4.4" / "design" / "Marble.kicad_pcb")
        if not board.is_file():
            self.skipTest("pinned public Marble board has not been fetched")
        design = _design_from_kicad(str(board))
        net = "Net-(C383-Pad1)"
        for field in ("tracks", "vias", "pads", "zones"):
            setattr(design, field, [item for item in getattr(design, field)
                                   if str(item.get("net_name", item.get("net", ""))) == net])
        mesh = build_hybrid_mesh(design, AnalysisSpec(mode="ac", net_names=[net],
            mesh={"target_size_mm": 1.0, "zone_cell_mm": 1.0,
                  "max_zone_cells": 1000, "max_conductors": 2000}))
        self.assertFalse(mesh.truncated)
        pads = {str(item.get("component_pad")): item for item in design.pads}

        def pad_node(name):
            pad = pads[name]
            return nearest_mesh_node(mesh, {"id": name, "net": net,
                "position_mm": pad["at"], "layer": pad.get("layer", "F.Cu"),
                "geometry_anchor": {"id": pad["id"], "type": "pad"}}, net)

        source, routed, isolated = (pad_node(name) for name in
                                    ("U37.18", "R195.1", "C383.1"))
        self.assertIsNotNone(source)
        component_nodes, _ = _connected_component(mesh, net, source)
        self.assertIn(routed, component_nodes)
        self.assertNotIn(isolated, component_nodes)


if __name__ == "__main__":
    unittest.main()
