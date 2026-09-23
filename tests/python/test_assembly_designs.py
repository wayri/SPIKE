"""Multi-design AssemblyIR package ownership regressions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python.spike_core.assembly_designs import AssemblyDesignError, canonicalize_assembly_designs
from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import AssemblyIRV1, DesignIRV2
from python.spike_core.project_package import ProjectPackageError, read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request


def _design(identity: str, digest: str) -> dict:
    return DesignIRV2.from_v1(DesignIR(
        design_id=identity, name=identity, source_format="neutral",
        layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": digest},
    )).to_dict()


class AssemblyDesignTests(unittest.TestCase):
    def fixture(self):
        first, second = _design("controller", "1" * 64), _design("load", "2" * 64)
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "two-designs", "name": "Two designs",
            "boards": [
                {"id": "controller-board", "design_id": first["design_id"], "frame": {"frame_id": "controller-frame", "parent_frame_id": "assembly"}},
                {"id": "load-board", "design_id": second["design_id"], "frame": {"frame_id": "load-frame", "parent_frame_id": "assembly", "transform": [1, 0, 0, 80, 0, 1, 0, 0, 0, 0, 1, 10, 0, 0, 0, 1]}},
            ],
            "harnesses": [{"id": "power-harness", "endpoint_a": "controller-board:J1", "endpoint_b": "load-board:J2", "length_mm": 125, "pin_map": {"1": "1"}}],
            "connector_mappings": [{"id": "connector-map", "kind": "connector-pin-map", "data": {"endpoint_a": "controller-board:J1", "endpoint_b": "load-board:J2", "pins": {"1": "1"}}}],
            "rigid_flex_links": [{"id": "flex-link", "kind": "rigid-flex-link", "data": {"board_a_id": "controller-board", "board_b_id": "load-board", "bend_radius_mm": 3.0}}],
        }).to_dict()
        retained = {"contract": "spike/assembly-designs/v1", "active_design_id": first["design_id"], "designs": [first, second]}
        return first, second, assembly, retained

    def test_two_designs_are_bound_to_boards_and_reopen_losslessly(self):
        first, second, assembly, retained = self.fixture()
        canonical = canonicalize_assembly_designs(retained, first, assembly)
        self.assertEqual([item["design_id"] for item in canonical["designs"]], [first["design_id"], second["design_id"]])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "multi-design.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "multi-design"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
            })
            self.assertEqual(manifest["schemas"]["assembly_designs"], "spike/assembly-designs/v1")
            reopened = read_project(path, include_members=True)
            self.assertEqual(reopened.payload["assembly_designs"], canonical)
            self.assertIn("design/assembly-designs.json", reopened.members)
            self.assertEqual({board["design_id"] for board in reopened.payload["assembly_ir"]["boards"]}, {first["design_id"], second["design_id"]})

    def test_missing_duplicate_or_mismatched_active_design_fails_closed(self):
        first, _, assembly, retained = self.fixture()
        cases = [
            {**retained, "designs": [first]},
            {**retained, "designs": [first, first]},
            {**retained, "active_design_id": "not-active"},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(AssemblyDesignError):
                canonicalize_assembly_designs(case, first, assembly)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.spike"
            with self.assertRaisesRegex(ProjectPackageError, "assembly design set"):
                write_spike_package(path, {"project": {"id": "bad"}, "design_ir": first, "assembly_ir": assembly, "assembly_designs": cases[0]})

    def test_thirty_32_layer_one_meter_designs_are_retained_for_thirty_boards(self):
        designs = [
            DesignIRV2.from_v1(DesignIR(
                design_id=f"board-design-{index}", name=f"Board design {index}", source_format="neutral",
                layers=[{"id": layer, "name": "F.Cu" if layer == 0 else f"In{layer}.Cu"} for layer in range(32)],
                metadata={"source_sha256": f"{index + 1:064x}", "board_size_mm": [1_000, 1_000]},
            )).to_dict()
            for index in range(30)
        ]
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "thirty-board", "name": "Thirty boards",
            "boards": [
                {"id": f"board-{index}", "design_id": design["design_id"]}
                for index, design in enumerate(designs)
            ],
        }).to_dict()
        retained = {
            "contract": "spike/assembly-designs/v1",
            "active_design_id": designs[0]["design_id"], "designs": designs,
        }

        canonical = canonicalize_assembly_designs(retained, designs[0], assembly)

        self.assertEqual(len(canonical["designs"]), 30)
        self.assertEqual(len(assembly["boards"]), 30)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "thirty-board.spike"
            write_spike_package(path, {
                "project": {"id": "thirty-board"}, "design_ir": designs[0],
                "assembly_ir": assembly, "assembly_designs": retained,
            })
            self.assertEqual(len(read_project(path).payload["assembly_designs"]["designs"]), 30)

    def test_retained_designs_reject_over_limit_layers_or_envelope(self):
        active = _design("active", "a" * 64)
        oversized_layers = DesignIRV2.from_v1(DesignIR(
            design_id="over-layers", name="Over layers", source_format="neutral",
            layers=[{"id": layer, "name": f"In{layer}.Cu"} for layer in range(33)],
            metadata={"source_sha256": "b" * 64},
        )).to_dict()
        oversized_envelope = dict(active)
        oversized_envelope["metadata"] = {**active["metadata"], "board_size_mm": [1_001, 1_000]}
        for candidate in (oversized_layers, oversized_envelope):
            retained = {
                "contract": "spike/assembly-designs/v1", "active_design_id": active["design_id"],
                "designs": [active, candidate],
            }
            with self.subTest(candidate=candidate["design_id"]), self.assertRaises(AssemblyDesignError):
                canonicalize_assembly_designs(retained, active, {"boards": []})

    def test_manifest_bound_board_and_harness_edit_preserves_designs(self):
        first, _, assembly, retained = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edit.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "edit"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
            })
            boards = [dict(item) for item in assembly["boards"]]
            boards[1] = {**boards[1], "frame": {**boards[1]["frame"], "transform": [1, 0, 0, 100, 0, 1, 0, 5, 0, 0, 1, 15, 0, 0, 0, 1]}}
            harnesses = [{**assembly["harnesses"][0], "length_mm": 175.0, "pin_map": {"1": "2", "2": "1"}}]
            response = handle_project_request("update_assembly_structure_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "boards": boards, "harnesses": harnesses,
                "connector_mappings": [{**assembly["connector_mappings"][0], "data": {**assembly["connector_mappings"][0]["data"], "pins": {"1": "2"}}}],
                "rigid_flex_links": [{**assembly["rigid_flex_links"][0], "data": {**assembly["rigid_flex_links"][0]["data"], "bend_radius_mm": 4.0}}],
            }, request_id="structure", application_version="test")
            self.assertTrue(response["ok"], response)
            self.assertFalse(response["result"]["coupled_solver_ready"])
            reopened = read_project(path)
            self.assertEqual(reopened.payload["assembly_designs"], retained)
            self.assertEqual(reopened.payload["assembly_ir"]["boards"][1]["frame"]["transform"][3], 100.0)
            self.assertEqual(reopened.payload["assembly_ir"]["harnesses"][0]["pin_map"], {"1": "2", "2": "1"})
            self.assertEqual(reopened.payload["assembly_ir"]["connector_mappings"][0]["data"]["pins"], {"1": "2"})
            self.assertEqual(reopened.payload["assembly_ir"]["rigid_flex_links"][0]["data"]["bend_radius_mm"], 4.0)
            self.assertEqual(reopened.payload["audit"][-1]["event"], "assembly_structure_updated")
            stale = handle_project_request("update_assembly_structure_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "boards": boards, "harnesses": harnesses,
                "connector_mappings": assembly["connector_mappings"], "rigid_flex_links": assembly["rigid_flex_links"],
            }, request_id="stale-structure", application_version="test")
            self.assertFalse(stale["ok"])


if __name__ == "__main__":
    unittest.main()
