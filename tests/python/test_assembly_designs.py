"""Multi-design AssemblyIR package ownership regressions."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from python.spike_core.assembly_designs import AssemblyDesignError, canonicalize_assembly_designs
from python.spike_core.contracts import SpiDeR
from python.spike_core.spider_v2 import AssemblyIRV1, SpiDeRV2
from python.spike_core.project_package import PackageLimits, ProjectPackageError, read_project, read_spike_package, write_spike_package
from python.spike_core.service_project_assembly import _prune_removed_entity_bindings
from python.spike_core.service_project_handlers import handle_project_request


def _design(identity: str, digest: str) -> dict:
    return SpiDeRV2.from_v1(SpiDeR(
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

    def test_assembly_design_set_uses_design_ir_budget_without_bypassing_integrity(self):
        first, _, assembly, retained = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "assembly-budget.spike"
            write_spike_package(path, {
                "project": {"id": "assembly-budget"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
            })
            with zipfile.ZipFile(path, "r") as archive:
                sizes = {item.filename: item.file_size for item in archive.infolist()}
            assembly_size = sizes["design/assembly-designs.json"]
            ordinary_size = max(size for name, size in sizes.items() if name.endswith(".json")
                                and name not in {"manifest.json", "design/design-ir.json", "design/assembly-designs.json"})
            self.assertGreater(assembly_size, ordinary_size)

            limits = PackageLimits(max_control_plane_json_bytes=ordinary_size,
                                   max_design_ir_json_bytes=assembly_size)
            self.assertEqual(read_spike_package(path, limits=limits).payload["assembly_designs"], retained)
            with self.assertRaisesRegex(ProjectPackageError, "control-plane JSON member exceeds.*assembly-designs"):
                read_spike_package(path, limits=PackageLimits(
                    max_control_plane_json_bytes=ordinary_size,
                    max_design_ir_json_bytes=assembly_size - 1,
                ))
            with self.assertRaisesRegex(ProjectPackageError, "control-plane JSON member exceeds"):
                read_spike_package(path, limits=PackageLimits(
                    max_control_plane_json_bytes=ordinary_size - 1,
                    max_design_ir_json_bytes=assembly_size,
                ))

            damaged = root / "assembly-budget-damaged.spike"
            with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(damaged, "w", allowZip64=True) as target:
                for info in source.infolist():
                    data = source.read(info.filename)
                    if info.filename == "design/assembly-designs.json":
                        data = data[:-2] + (b" " if data[-2:-1] != b" " else b"\t") + data[-1:]
                    target.writestr(info, data)
            with self.assertRaisesRegex(ProjectPackageError, "member integrity check failed"):
                read_spike_package(damaged, limits=limits)

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

    def test_removed_contact_binding_is_pruned_without_changing_constraints(self):
        constraint = {"constraint_id": "keep-constraint", "references": [{"part_id": "part-a"}]}
        index, counts = _prune_removed_entity_bindings({
            "constraints": [constraint],
            "thermal_contact_bindings": [
                {"assembly_entity_id": "removed-contact"},
                {"assembly_entity_id": "retained-contact"},
            ],
            "electrical_bond_bindings": [{"assembly_entity_id": "retained-bond"}],
        }, {"removed-contact"}, set())

        self.assertEqual(index["constraints"], [constraint])
        self.assertEqual(index["thermal_contact_bindings"], [{"assembly_entity_id": "retained-contact"}])
        self.assertEqual(index["electrical_bond_bindings"], [{"assembly_entity_id": "retained-bond"}])
        self.assertEqual(counts, {"thermal_contact_bindings": 1, "electrical_bond_bindings": 0})

    def test_thirty_32_layer_one_meter_designs_are_retained_for_thirty_boards(self):
        designs = [
            SpiDeRV2.from_v1(SpiDeR(
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
        oversized_layers = SpiDeRV2.from_v1(SpiDeR(
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

    def test_manifest_bound_stack_mate_round_trip(self):
        first, _, assembly, retained = self.fixture()
        mate = {"id": "stack-mate", "name": "Stack header", "kind": "connector-mate",
                "data": {"endpoint_a": "controller-board::J3", "endpoint_b": "load-board::J4",
                         "pin_map": {"1": "2", "2": "1"}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stack.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "stack"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
            })
            response = handle_project_request("update_assembly_structure_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "boards": assembly["boards"], "harnesses": assembly["harnesses"],
                "connector_mappings": [*assembly["connector_mappings"], mate],
                "rigid_flex_links": assembly["rigid_flex_links"],
            }, request_id="stack", application_version="test")
            self.assertTrue(response["ok"], response)
            self.assertEqual(read_project(path).payload["assembly_ir"]["connector_mappings"][-1]["data"], mate["data"])

    def test_duplicate_occurrence_reuses_one_retained_design_and_source_artifact(self):
        source = b"(kicad_pcb (version 20240108))"
        source_digest = hashlib.sha256(source).hexdigest()
        first, second, assembly, retained = self.fixture()
        first["source"]["source_digest"] = source_digest
        first["source"]["artifact_path"] = f"package:sources/{source_digest}.kicad_pcb"
        retained["designs"][0] = first
        retained["active_design_id"] = first["design_id"]
        duplicate = {
            **assembly["boards"][0],
            "id": "controller-board-copy",
            "frame": {
                **assembly["boards"][0]["frame"],
                "frame_id": "controller-copy-frame",
                "transform": [1, 0, 0, 25, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicated-occurrence.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "duplicated-occurrence"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
            }, source_artifacts={"controller.kicad_pcb": source})
            response = handle_project_request("update_assembly_structure_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "boards": [*assembly["boards"], duplicate],
                "harnesses": assembly["harnesses"],
                "connector_mappings": assembly["connector_mappings"],
                "rigid_flex_links": assembly["rigid_flex_links"],
            }, request_id="duplicate-occurrence", application_version="test")
            self.assertTrue(response["ok"], response)
            reopened = read_project(path, include_members=True)

        boards = reopened.payload["assembly_ir"]["boards"]
        self.assertEqual(len({board["id"] for board in boards}), 3)
        self.assertEqual(sum(board["design_id"] == first["design_id"] for board in boards), 2)
        self.assertEqual(len(reopened.payload["assembly_designs"]["designs"]), 2)
        self.assertEqual(len([name for name in reopened.members if name.startswith("sources/")]), 1)

    def test_duplicate_occurrence_or_frame_identity_is_rejected_without_writing(self):
        first, _, assembly, retained = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate-id.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "duplicate-id"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
            })
            cases = [
                ({**assembly["boards"][0], "frame": {
                    **assembly["boards"][0]["frame"], "frame_id": "unique-copy-frame",
                }}, "IDs must be unique"),
                ({**assembly["boards"][0], "id": "unique-copy-id"}, "frame IDs must be unique"),
                ({**assembly["boards"][0], "id": "missing-design-board", "design_id": "missing-design", "frame": {
                    **assembly["boards"][0]["frame"], "frame_id": "missing-design-frame",
                }}, "unretained SpiDeR identities"),
            ]
            for duplicate, expected_error in cases:
                with self.subTest(expected_error=expected_error):
                    response = handle_project_request("update_assembly_structure_in_project", {
                        "project_path": str(path),
                        "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                        "boards": [*assembly["boards"], duplicate],
                        "harnesses": assembly["harnesses"],
                        "connector_mappings": assembly["connector_mappings"],
                        "rigid_flex_links": assembly["rigid_flex_links"],
                    }, request_id="duplicate-id", application_version="test")

                    self.assertFalse(response["ok"])
                    self.assertIn(expected_error, response["error"])
                    self.assertEqual(
                        read_project(path).manifest["manifest_payload_sha256"],
                        manifest["manifest_payload_sha256"],
                    )

    def test_no_op_structure_update_preserves_saved_results(self):
        first, _, assembly, retained = self.fixture()
        results = {"retained-result": {"assembly_id": assembly["assembly_id"]}}
        analyses = {"latest_result": {"analysis_id": "retained-analysis"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "no-op.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "no-op"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
                "analyses": analyses, "results": results,
            })
            response = handle_project_request("update_assembly_structure_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "boards": assembly["boards"], "harnesses": assembly["harnesses"],
                "connector_mappings": assembly["connector_mappings"],
                "rigid_flex_links": assembly["rigid_flex_links"],
            }, request_id="no-op", application_version="test")
            self.assertTrue(response["ok"], response)
            reopened = read_project(path)

        self.assertFalse(response["result"]["results_invalidated"])
        self.assertEqual(reopened.payload["results"], results)
        self.assertEqual(reopened.payload["analyses"], analyses)

    def test_removal_prunes_only_explicit_occurrence_references_and_invalidates_results(self):
        first, _, assembly, retained = self.fixture()
        assembly["thermal_contacts"] = [{
            "id": "board-contact", "endpoint_a": "controller-board", "endpoint_b": "load-board",
            "contact_type": "board-stack",
        }]
        assembly["electrical_bonds"] = [{
            "id": "ground-bond", "endpoint_a": "controller-board::GND", "endpoint_b": "load-board::GND",
            "bond_type": "ground-bond",
        }]
        assembly = AssemblyIRV1.from_dict(assembly).to_dict()
        replacement = {
            **assembly["boards"][1],
            "id": "load-board-copy",
            "frame": {
                **assembly["boards"][1]["frame"],
                "frame_id": "load-copy-frame",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "remove-occurrence.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "remove-occurrence"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
                "analyses": {
                    "latest_result": {"analysis_id": "stale-analysis"},
                    "nested": {"active_result": {"analysis_id": "also-stale"}},
                },
                "results": {"stale-result": {"assembly_id": assembly["assembly_id"]}},
            })
            response = handle_project_request("update_assembly_structure_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "boards": [assembly["boards"][0], replacement],
                # Old clients can submit stale dependencies; the verified write
                # reconciles them only by the removed occurrence identity.
                "harnesses": assembly["harnesses"],
                "connector_mappings": assembly["connector_mappings"],
                "rigid_flex_links": assembly["rigid_flex_links"],
            }, request_id="remove-occurrence", application_version="test")
            self.assertTrue(response["ok"], response)
            reopened = read_project(path)

        self.assertEqual(response["result"]["removed_board_ids"], ["load-board"])
        self.assertTrue(response["result"]["results_invalidated"])
        self.assertEqual(reopened.payload["results"], {})
        self.assertNotIn("latest_result", reopened.payload["analyses"])
        self.assertIsNone(reopened.payload["analyses"]["nested"]["active_result"])
        saved = reopened.payload["assembly_ir"]
        self.assertEqual([board["id"] for board in saved["boards"]], ["controller-board", "load-board-copy"])
        self.assertEqual(saved["harnesses"], [])
        self.assertEqual(saved["connector_mappings"], [])
        self.assertEqual(saved["rigid_flex_links"], [])
        self.assertEqual(saved["thermal_contacts"], [])
        self.assertEqual(saved["electrical_bonds"], [])
        self.assertEqual(len(reopened.payload["assembly_designs"]["designs"]), 2)
        history = reopened.payload["extensions"]["spike.assembly-structure-history"]["previous_states"]
        self.assertEqual(history[-1]["results"]["stale-result"]["assembly_id"], assembly["assembly_id"])

    def test_removal_blocks_a_retained_part_parented_to_removed_board_frame(self):
        first, _, assembly, retained = self.fixture()
        model_artifact = b"ISO-10303-21;END-ISO-10303-21;"
        assembly["parts"] = [{
            "id": "dependent-part", "name": "Dependent part", "part_type": "fixture",
            "model_id": "dependent-model",
            "frame": {"frame_id": "dependent-frame", "parent_frame_id": "load-frame"},
        }]
        assembly = AssemblyIRV1.from_dict(assembly).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dependent-part.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "dependent-part"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
                "models": {"contract": "spike/model-index/v1", "models": [{
                    "id": "dependent-model", "name": "Dependent model", "model_type": "step",
                    "uri": "package:models/artifacts/dependent.step",
                    "digest": hashlib.sha256(model_artifact).hexdigest(), "transform": [], "extensions": {},
                }]},
            }, model_artifacts={"dependent.step": model_artifact})
            response = handle_project_request("update_assembly_structure_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "boards": [assembly["boards"][0]],
                "harnesses": [], "connector_mappings": [], "rigid_flex_links": [],
            }, request_id="dependent-part", application_version="test")

            self.assertFalse(response["ok"])
            self.assertIn("dependent-part", response["error"])
            self.assertIn("Reparent", response["error"])
            self.assertEqual(len(read_project(path).payload["assembly_ir"]["boards"]), 2)

    def test_removal_blocks_a_retained_child_board_parented_to_removed_board_frame(self):
        first, _, assembly, retained = self.fixture()
        assembly["boards"][1]["frame"]["parent_frame_id"] = "controller-frame"
        assembly = AssemblyIRV1.from_dict(assembly).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dependent-board.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "dependent-board"}, "design_ir": first,
                "assembly_ir": assembly, "assembly_designs": retained,
            })
            response = handle_project_request("update_assembly_structure_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "boards": [assembly["boards"][1]],
                "harnesses": [], "connector_mappings": [], "rigid_flex_links": [],
            }, request_id="dependent-board", application_version="test")

            self.assertFalse(response["ok"])
            self.assertIn("board load-board depends", response["error"])
            self.assertEqual(
                read_project(path).manifest["manifest_payload_sha256"],
                manifest["manifest_payload_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
