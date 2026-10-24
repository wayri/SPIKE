# SPDX-License-Identifier: Apache-2.0
"""Native finite full-pad studies preserve source identity and physical support."""
from copy import deepcopy
import hashlib
from pathlib import Path
import unittest
from shapely.geometry import Point
from python.spike_core.dc_board_source import prepare_source_board, prepare_board_sources, authenticate_board_pads
from python.spike_core.dc_board_volume import compile_board_volume
from python.spike_core.dc_tetra_rt0 import solve_tetra_dc
from python.spike_core.dc_tetra_rt0_evidence import validate_tetra_dc
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.kicad_source_evidence import read_kicad_board_pad_inventory

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT/"tests/fixtures/dc_board_volume_source.kicad_pcb"


def source_model():
    electrodes = [{"id": "source", "pad_id": "f3eeec65-f95d-456a-b5df-fa95ee3a95a1", "layer": "F.Cu", "side": "top", "current_a": 1.},
                  {"id": "load", "pad_id": "0b5b1e1f-bff2-438d-b1e7-e050c9c90302", "layer": "F.Cu", "side": "top", "current_a": -1.}]
    return prepare_source_board(FIXTURE, hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), net_names=["VDD"],
        electrodes=electrodes, plating_thickness_mm=.025, conductivity_s_m=5.8e7)


class BoardSourceTests(unittest.TestCase):
    def test_native_full_pad_study_actual_complete_volume_fields(self):
        prepared = source_model()
        compiled = compile_board_volume(prepared["groups"], prepared["barrels"], prepared["contacts"],
            expected_axial_source_ids=prepared["expected_axial_source_ids"], target_mm=1., max_cells=5000)
        result = solve_tetra_dc(compiled["request"]); validate_tetra_dc(result)
        self.assertEqual(prepared["source_evidence"]["native_pad_count"], 2)
        self.assertEqual(prepared["expected_axial_source_ids"], [])
        self.assertAlmostEqual(result["current_density_observable"]["physical_volume_m3"], 3*.035*1e-9, delta=1e-23)
        self.assertTrue(compiled["coverage"]["complete_selected_geometry"])
        self.assertFalse(result["current_density_observable"]["complete_board_physical_volume"])
        for contact in result["contacts"]:
            self.assertAlmostEqual(contact["recovered_inward_current_a"], contact["inward_current_a"], delta=1e-9)
        self.assertGreater(result["joule_heat_w"], 0)

    def test_full_annular_pad_retains_drill_hole_and_explicit_barrels(self):
        p = ROOT/"tests/fixtures/dc_annular_source.kicad_pcb"
        prepared = prepare_source_board(p, hashlib.sha256(p.read_bytes()).hexdigest(), net_names=["STACK"],
            electrodes=[{"id": "source", "pad_id": "b6805fb9-ea4f-456f-a1b1-2ca414521568", "layer": "B.Cu", "side": "bottom", "current_a": 1.},
                        {"id": "load", "pad_id": "b6805fb9-ea4f-456f-a1b1-2ca414521568", "layer": "F.Cu", "side": "top", "current_a": -1.}],
            plating_thickness_mm=.025, conductivity_s_m=5.8e7)
        self.assertEqual(len(prepared["barrels"]), 1)
        self.assertEqual(len(prepared["expected_axial_source_ids"]), 1)
        for contact in prepared["contacts"]:
            self.assertEqual(len(contact["geometry"].interiors), 1)
            self.assertFalse(contact["geometry"].covers(Point(10, 20)))
        b = prepared["barrels"][0]
        self.assertAlmostEqual(b["z_max_mm"]-b["z_min_mm"], 1.565)

    def test_source_geometry_digest_native_disagreement_and_ids_reject(self):
        sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        design = import_kicad_design(str(FIXTURE)); before = deepcopy(design.to_dict())
        native = read_kicad_board_pad_inventory(FIXTURE, sha)
        authenticate_board_pads(design, native)
        design.pads[0]["size"] = [2., 1.]
        with self.assertRaisesRegex(ValueError, "geometry differs"): authenticate_board_pads(design, native)
        self.assertEqual(before["pads"][0]["size"], (1., 1.))
        with self.assertRaisesRegex(ValueError, "hash differs"):
            prepare_source_board(FIXTURE, "0"*64, net_names=["VDD"], electrodes=[], plating_thickness_mm=.025, conductivity_s_m=5.8e7)
        prepared = source_model(); invalid = deepcopy(prepared["source_evidence"]["electrodes"])
        invalid[0]["pad_id"] = "not-a-source-pad"
        with self.assertRaises(ValueError):
            prepare_board_sources(import_kicad_design(str(FIXTURE)), net_names=["VDD"], electrodes=invalid,
                                  plating_thickness_mm=.025, conductivity_s_m=5.8e7)

    def test_hidden_native_offset_and_layer_policies_reject_at_adapter_boundary(self):
        sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        design = import_kicad_design(str(FIXTURE)); native = read_kicad_board_pad_inventory(FIXTURE, sha)
        pid = next(iter(native["pads"]))
        for field, value in (("drill_offset_mm", [.1, 0.]), ("padstack_geometry", "per_layer"),
                             ("remove_unused_layers", "yes"), ("keep_end_layers", "yes")):
            changed = deepcopy(native); changed["pads"][pid][field] = value
            with self.assertRaisesRegex(ValueError, "policy is unsupported"):
                authenticate_board_pads(design, changed)


if __name__ == "__main__": unittest.main()
