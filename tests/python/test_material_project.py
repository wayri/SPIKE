# SPDX-License-Identifier: Apache-2.0
"""Material snapshots persisted on AssemblyIR occurrences."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from python.spike_core.contracts import SpiDeR
from python.spike_core.material_library import MaterialError, load_catalog, material_snapshot, validate_snapshot
from python.spike_core.project_package import ProjectPackageError, read_project, write_spike_package
from python.spike_core.service_material_library import assign_material_to_project
from python.spike_core.spider_v2 import SpiDeRV2


def _payload() -> dict:
    design = SpiDeRV2.from_v1(SpiDeR(
        design_id="material-board-design", name="Electrical source", source_format="neutral",
        layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "7" * 64},
    )).to_dict()
    return {
        "project": {"id": "material-project", "name": "Material project"},
        "design_ir": design,
        "assembly_ir": {
            "contract": "spike/assembly-ir/v1", "assembly_id": "assembly", "name": "Assembly",
            "frame": {"frame_id": "assembly"},
            "boards": [{"id": "board-a", "design_id": design["design_id"],
                        "frame": {"frame_id": "board-frame"},
                        "extensions": {"geometry.vendor": {"mesh": [1, 2, 3]}},
                        "future_geometry_key": {"shape": "retained"}}],
            "parts": [{"id": "case", "name": "Case", "part_type": "subassembly",
                       "model_id": "", "frame": {"frame_id": "case-frame"},
                       "extensions": {"geometry.vendor": {"faces": [8, 9]}},
                       "future_geometry_key": {"shape": "also-retained"}}],
            "materials": [], "thermal_contacts": [], "electrical_bonds": [],
            "extensions": {"spike.multiboard-studies": {
                "thermal": {"setup": {"ambient_k": 300}, "result": {"temperature_k": 310}},
            }},
        },
        "results": {"latest": {"value": 4}},
        "analyses": {"latest_result": {"value": 4}, "result_history": [{"value": 3}]},
        "extensions": {"legacy": {
            "analysis": {"active_result": {"value": 4}},
            "results": {"latest": {"value": 4}},
        }},
        "audit": [{"event": "created"}],
    }


class MaterialProjectTests(unittest.TestCase):
    def _project(self, root: Path) -> tuple[Path, str]:
        path = root / "materials.spike"
        manifest = write_spike_package(path, _payload(), application_version="test")
        return path, manifest["manifest_payload_sha256"]

    def test_part_and_board_assignments_round_trip_without_touching_source_or_geometry_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest = self._project(Path(directory))
            before = read_project(path, include_members=True).payload
            layer_id = before["design_ir"]["layers"][0]["id"]
            part_result = assign_material_to_project({
                "project_path": str(path), "expected_manifest_payload_sha256": digest,
                "target_kind": "part", "target_id": "case",
                "catalog_material_id": load_catalog()[0]["id"],
            }, application_version="test")
            board_result = assign_material_to_project({
                "project_path": str(path),
                "expected_manifest_payload_sha256": part_result["manifest"]["manifest_payload_sha256"],
                "target_kind": "board", "target_id": "board-a",
                "material": copy.deepcopy(load_catalog()[1]),
            }, application_version="test")
            layer_result = assign_material_to_project({
                "project_path": str(path),
                "expected_manifest_payload_sha256": board_result["manifest"]["manifest_payload_sha256"],
                "target_kind": "board_layer", "target_id": "board-a", "layer_id": layer_id,
                "catalog_material_id": load_catalog()[0]["id"],
            }, application_version="test")
            opened = read_project(path).payload

        self.assertEqual(opened["design_ir"], before["design_ir"])
        for collection in ("parts", "boards"):
            old_extensions = before["assembly_ir"][collection][0]["extensions"]
            new_extensions = opened["assembly_ir"][collection][0]["extensions"]
            self.assertEqual(new_extensions["geometry.vendor"], old_extensions["geometry.vendor"])
            self.assertEqual(
                new_extensions["spike.assembly-ir.unknown-fields"],
                old_extensions["spike.assembly-ir.unknown-fields"],
            )
        validate_snapshot(opened["assembly_ir"]["parts"][0]["extensions"]["spike.material"])
        validate_snapshot(opened["assembly_ir"]["boards"][0]["extensions"]["spike.material"])
        validate_snapshot(opened["assembly_ir"]["boards"][0]["extensions"]["spike.layer-materials"][layer_id])
        self.assertEqual(opened["design_ir"]["layers"], before["design_ir"]["layers"])
        self.assertEqual(opened["results"], {})
        self.assertIsNone(opened["analyses"].get("latest_result"))
        self.assertEqual(opened["analyses"]["result_history"], [])
        self.assertNotIn(
            "result",
            opened["assembly_ir"]["extensions"]["spike.multiboard-studies"]["thermal"],
        )
        self.assertNotIn("results", opened["extensions"]["legacy"])
        self.assertNotIn("active_result", opened["extensions"]["legacy"]["analysis"])
        archived = opened["extensions"]["spike.material-assignment-history"]["previous_states"][0]
        self.assertEqual(archived["extensions"]["legacy"]["results"]["latest"]["value"], 4)
        self.assertEqual(archived["extensions"]["legacy"]["analysis"]["active_result"]["value"], 4)
        self.assertEqual(
            archived["assembly_ir"]["extensions"]["spike.multiboard-studies"]["thermal"]["result"]["temperature_k"],
            310,
        )
        self.assertEqual(opened["audit"][-1]["material_digest"], layer_result["material"]["digest"])

    def test_exact_reassignment_is_a_noop_and_retains_current_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest = self._project(Path(directory))
            assigned = assign_material_to_project({
                "project_path": str(path), "expected_manifest_payload_sha256": digest,
                "target_kind": "part", "target_id": "case",
                "catalog_material_id": load_catalog()[0]["id"],
            }, application_version="test")
            current = read_project(path, include_members=True)
            payload = copy.deepcopy(current.payload)
            payload["results"] = {"new_valid_result": {"value": 9}}
            manifest = write_spike_package(
                path, payload, preserved_members=current.members, application_version="test",
            )
            before = path.read_bytes()
            repeated = assign_material_to_project({
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "target_kind": "part", "target_id": "case",
                "catalog_material_id": load_catalog()[0]["id"],
            }, application_version="test")
            self.assertTrue(repeated["unchanged"])
            self.assertFalse(repeated["active_results_invalidated"])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(read_project(path).payload["results"]["new_valid_result"]["value"], 9)

    def test_board_layer_requires_an_exact_retained_canonical_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest = self._project(Path(directory))
            before = path.read_bytes()
            with self.assertRaisesRegex(ProjectPackageError, "Canonical layer"):
                assign_material_to_project({
                    "project_path": str(path), "expected_manifest_payload_sha256": digest,
                    "target_kind": "board_layer", "target_id": "board-a", "layer_id": "F.Cu",
                    "catalog_material_id": load_catalog()[0]["id"],
                }, application_version="test")
            self.assertEqual(path.read_bytes(), before)

    def test_stale_project_or_snapshot_digest_is_rejected(self):
        snapshot = material_snapshot(load_catalog()[0])
        snapshot["digest"] = "0" * 64
        with self.assertRaises(MaterialError):
            validate_snapshot(snapshot)
        with tempfile.TemporaryDirectory() as directory:
            path, digest = self._project(Path(directory))
            with self.assertRaisesRegex(ProjectPackageError, "changed since it was verified"):
                assign_material_to_project({
                    "project_path": str(path), "expected_manifest_payload_sha256": "0" * 64,
                    "target_kind": "part", "target_id": "case",
                    "catalog_material_id": load_catalog()[0]["id"],
                }, application_version="test")
            self.assertEqual(read_project(path).manifest["manifest_payload_sha256"], digest)

    def test_unknown_target_does_not_write_and_snapshot_is_independent(self):
        record = load_catalog()[0]
        snapshot = material_snapshot(record)
        record["name"] = "Changed outside snapshot"
        self.assertNotEqual(snapshot["record"]["name"], record["name"])
        with tempfile.TemporaryDirectory() as directory:
            path, digest = self._project(Path(directory))
            before = path.read_bytes()
            with self.assertRaisesRegex(ProjectPackageError, "does not exist"):
                assign_material_to_project({
                    "project_path": str(path), "expected_manifest_payload_sha256": digest,
                    "target_kind": "part", "target_id": "missing",
                    "catalog_material_id": load_catalog()[0]["id"],
                }, application_version="test")
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
