import json
import hashlib
import random
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import AssemblyIRV1, DesignIRV2
from python.spike_core.geometry_arrow import canonical_geometry_rows
from python.spike_core import project_model_artifacts
from python.spike_core.project_package import (
    PackageLimits,
    ProjectPackageError,
    build_package_members,
    migrate_legacy_payload,
    read_geometry_arrow_artifact,
    read_project,
    read_spike_package,
    read_visual_model_artifacts,
    write_spike_package,
)
from python.spike_core.project_model_artifacts import read_project_source_artifact, read_step_model_artifact
from python.spike_core.project_package_auth import validate_targeted_manifest_signature


def _write_underreported_member(source_path: Path, destination: Path, member_path: str) -> dict:
    """Copy a package with one manifest record deliberately smaller than its ZIP member."""

    with zipfile.ZipFile(source_path, "r") as source:
        manifest = json.loads(source.read("manifest.json"))
        members = {item.filename: source.read(item) for item in source.infolist()}
    record = next(item for item in manifest["members"] if item["path"] == member_path)
    record["size"] = 1
    unsigned = dict(manifest)
    unsigned.pop("signature", None)
    unsigned.pop("manifest_payload_sha256", None)
    manifest["manifest_payload_sha256"] = hashlib.sha256(
        (json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
    ).hexdigest()
    members["manifest.json"] = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return manifest


class ProjectPackageV3Tests(unittest.TestCase):
    def test_oversized_legacy_json_rejected_before_materializing_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.spike"
            path.write_text('{"format":"legacy","data":"too large"}', encoding="utf-8")
            with patch("python.spike_core.project_package_access.MAX_LEGACY_PROJECT_BYTES", 16):
                with self.assertRaisesRegex(ProjectPackageError, "Legacy JSON project exceeds"):
                    read_project(path)

    @staticmethod
    def retained_nonregular_padstack_geometry():
        return {
            "contract": "spike/retained-padstack-geometry/v1",
            "user_primitives": [{
                "id": "USER-SPECIAL-1", "kind": "user_special", "source_index": 5,
                "source_units": "mm", "contours": [{"boundary_rings": [{
                    "role": "outer", "fill_style_id": "SOLID_FILL", "start_mm": [0, 0],
                    "segments": [
                        {"kind": "line", "end_mm": [2, 0]}, {"kind": "line", "end_mm": [2, 2]},
                        {"kind": "line", "end_mm": [0, 2]}, {"kind": "line", "end_mm": [0, 0]},
                    ],
                }]}],
            }],
            "occurrences": [{
                "source_index": 17, "source_id": "PADSTACK-17",
                "kind": "retained_padstack_nonregular_occurrence", "status": "retained_unresolved",
                "reason": "negative_plane_user_primitive_semantics_pending", "padstack_ref": "PTH-1",
                "layer_id": "TOP", "layer_polarity": "negative", "raw_net_ref": "VCC",
                "resolved_net_id": "VCC", "occurrence_pad_usage": "via", "matched_profile_use": "thermal",
                "at_mm": [3, 4], "xform": {"rotation_deg": 90, "mirror": False},
                "primitive_ref": "USER-SPECIAL-1",
            }],
        }

    def payload(self):
        design = DesignIRV2.from_v1(DesignIR(
            design_id="fixture",
            name="Fixture",
            source_format="kicad",
            layers=[{"id": 0, "name": "F.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            metadata={"source_sha256": "1" * 64},
        ))
        return {
            "saved_at": "2026-08-13T00:00:00.000Z",
            "project": {"id": "project-fixture", "name": "Fixture"},
            "workspace": {
                "contract": "spike/workspace-state/v1",
                "viewMode": "3D",
                "docks": {
                    "left": {"visible": True, "pinned": True, "size": 220},
                    "right": {"visible": True, "pinned": True, "size": 360},
                    "bottom": {"visible": True, "pinned": True, "size": 180, "activeTab": "console"},
                },
                "viewports": {
                    "threeD": {
                        "contract": "spike/viewport-camera/v1",
                        "position": [2.0, 3.0, 4.0],
                        "target": [0.0, 0.0, 0.0],
                        "up": [0.0, 0.0, 1.0],
                    },
                },
            },
            "design_ir": design.to_dict(),
            "analyses": {"jobs": []},
            "results": {"runs": []},
            "audit": [{"event": "created"}],
        }

    def test_zip64_package_round_trip_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.spike"
            manifest = write_spike_package(
                path,
                self.payload(),
                source_artifacts={"fixture.kicad_pcb": b"(kicad_pcb)"},
                geometry_tables={"tracks": b"ARROW1-fixture"},
            )
            reopened = read_spike_package(path, include_members=True)
        self.assertEqual(manifest["format"], "spike-project-package/v3")
        self.assertEqual(reopened.payload["design_ir"]["contract"], "spike/design-ir/v2")
        self.assertTrue(any(name.startswith("sources/") for name in reopened.members))
        self.assertIn("geometry/tracks.arrow", reopened.members)
        self.assertIn("workspace/state.json", reopened.members)
        self.assertEqual(reopened.payload["workspace"]["viewports"]["threeD"]["position"], [2.0, 3.0, 4.0])
        self.assertEqual(reopened.payload["audit"], [{"event": "created"}])

    def test_retained_incomplete_padstack_group_is_package_bound_but_not_arrow_copper(self):
        payload = self.payload()
        legacy = DesignIR(
            design_id="retained", name="Retained", source_format="ipc-2581",
            layers=[{"id": "L1", "name": "TOP", "type": "copper"},
                    {"id": "L2", "name": "BOTTOM", "type": "copper"}],
            nets=[{"id": "N1", "name": "VCC"}], metadata={"source_sha256": "7" * 64},
        )
        legacy.metadata["ipc2581_incomplete_pad_occurrence_groups"] = [{
            "id": "P1", "kind": "incomplete_padstack_occurrence_group", "status": "retained_unresolved",
            "reason": "missing_required_regular_layers", "padstack_ref": "PTH", "net_id": "N1",
            "at_mm": [1, 2], "expected_regular_layer_ids": ["TOP", "BOTTOM"],
            "observed_layer_ids": ["TOP"], "occurrence_count": 1,
            "occurrences": [{"source_index": 9, "source_id": "P1", "layer_id": "TOP", "pad_usage": "",
                             "at_mm": [1, 2], "shape": {"kind": "circle", "size_mm": [1, 1],
                             "source_primitive_id": "C1"}, "pin": None}],
        }]
        payload["design_ir"] = DesignIRV2.from_v1(legacy).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retained.spike"
            write_spike_package(path, payload, generate_geometry_tables=True)
            reopened = read_spike_package(path, include_members=True)
        self.assertEqual(reopened.payload["design_ir"]["retained_padstack_occurrence_groups"][0]["occurrence_count"], 1)
        self.assertEqual(reopened.payload["geometry"]["tables"][0]["rows"], 0)

    def test_retained_nonregular_padstack_geometry_survives_package_without_inferred_entities_or_arrow_rows(self):
        legacy = DesignIR(
            design_id="retained-nonregular", name="Retained non-regular", source_format="ipc-2581",
            layers=[{"id": "L1", "name": "TOP", "type": "copper"}],
            nets=[{"id": "N1", "name": "VCC"}], metadata={"source_sha256": "8" * 64},
        )
        legacy.metadata["ipc2581_retained_nonregular_padstack_geometry"] = self.retained_nonregular_padstack_geometry()
        design = DesignIRV2.from_v1(legacy)
        self.assertEqual((len(design.pads), len(design.vias), len(design.zones)), (0, 0, 0))

        payload = self.payload()
        payload["design_ir"] = design.to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retained-nonregular.spike"
            write_spike_package(path, payload)
            reopened = read_spike_package(path)
            restored = DesignIRV2.from_dict(reopened.payload["design_ir"])

        self.assertEqual(
            json.loads(json.dumps(restored.to_v1().metadata["ipc2581_retained_nonregular_padstack_geometry"])),
            self.retained_nonregular_padstack_geometry(),
        )
        self.assertEqual(canonical_geometry_rows(restored), [])

    def test_retained_negative_contour_survives_package_without_zone_or_arrow_rows(self):
        legacy = DesignIR(
            design_id="retained-negative", name="Retained negative", source_format="ipc-2581",
            layers=[{"id": "L1", "name": "TOP", "type": "copper"}], nets=[],
            metadata={"source_sha256": "9" * 64},
        )
        retained = {
            "contract": "spike/retained-negative-contours/v1",
            "records": [{
                "status": "retained_unresolved", "reason": "negative_layer_contour_semantics_pending",
                "source_id": "NEG-1", "source_index": 22, "layer_ref": "TOP",
                "resolved_layer_id": "TOP", "layer_polarity": "NEGATIVE",
                "raw_net_ref": "UNKNOWN", "resolved_net_id": "",
                "boundary_rings": [{"role": "outer", "start_mm": [0, 0], "segments": [
                    {"kind": "line", "end_mm": [1, 0]}, {"kind": "line", "end_mm": [1, 1]},
                    {"kind": "line", "end_mm": [0, 0]},
                ]}],
            }],
        }
        legacy.metadata["ipc2581_retained_negative_contours"] = retained
        design = DesignIRV2.from_v1(legacy)
        payload = self.payload()
        payload["design_ir"] = design.to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retained-negative.spike"
            write_spike_package(path, payload, generate_geometry_tables=True)
            reopened = read_spike_package(path)
            restored = DesignIRV2.from_dict(reopened.payload["design_ir"])
        self.assertEqual(restored.to_v1().metadata["ipc2581_retained_negative_contours"], retained)
        self.assertEqual((len(restored.zones), canonical_geometry_rows(restored)), (0, []))

    def test_retained_unnetted_padstack_group_survives_without_pad_via_or_arrow_rows(self):
        legacy = DesignIR(
            design_id="retained-unnetted", name="Retained unnetted", source_format="ipc-2581",
            layers=[{"id": "L1", "name": "TOP", "type": "copper"}], nets=[],
            metadata={"source_sha256": "8" * 64},
        )
        retained = {
            "contract": "spike/retained-unnetted-padstack-groups/v1",
            "groups": [{
                "id": "UNNETTED-1", "kind": "retained_unnetted_padstack_occurrence_group",
                "status": "retained_unresolved", "reason": "native_net_identity_absent",
                "padstack_ref": "MOUNT", "raw_net_ref": "", "at_mm": [4, 5],
                "expected_regular_layer_ids": ["TOP"], "occurrence_count": 1,
                "occurrences": [{"source_index": 12, "source_id": "pad:12", "layer_id": "TOP"}],
            }],
        }
        legacy.metadata["ipc2581_retained_unnetted_padstack_occurrence_groups"] = retained
        payload = self.payload()
        payload["design_ir"] = DesignIRV2.from_v1(legacy).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retained-unnetted.spike"
            write_spike_package(path, payload, generate_geometry_tables=True)
            restored = DesignIRV2.from_dict(read_spike_package(path).payload["design_ir"])
        self.assertEqual(
            restored.to_v1().metadata["ipc2581_retained_unnetted_padstack_occurrence_groups"], retained,
        )
        self.assertEqual((len(restored.pads), len(restored.vias), canonical_geometry_rows(restored)), (0, 0, []))

    def test_retained_standard_contour_land_survives_without_pad_via_or_arrow_rows(self):
        legacy = DesignIR(
            design_id="retained-contour-land", name="Retained contour land", source_format="ipc-2581",
            layers=[{"id": "L1", "name": "TOP", "type": "copper"}],
            nets=[{"id": "N1", "name": "VCC"}], metadata={"source_sha256": "a" * 64},
        )
        retained = {
            "contract": "spike/retained-standard-contour-land-geometry/v1",
            "definitions": [{"id": "SHAPE_S20", "kind": "standard_contour_land_definition",
                             "status": "retained_unresolved", "source_index": 10}],
            "padstacks": [{"name": "NS_S20", "source_index": 20, "primitive_ref": "SHAPE_S20"}],
            "occurrences": [{"source_index": 30, "source_id": "pad:30",
                             "kind": "standard_contour_land_occurrence", "status": "retained_unresolved",
                             "padstack_ref": "NS_S20", "primitive_ref": "SHAPE_S20"}],
        }
        legacy.metadata["ipc2581_retained_standard_contour_land_geometry"] = retained
        payload = self.payload()
        payload["design_ir"] = DesignIRV2.from_v1(legacy).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retained-contour-land.spike"
            write_spike_package(path, payload, generate_geometry_tables=True)
            restored = DesignIRV2.from_dict(read_spike_package(path).payload["design_ir"])
        self.assertEqual(
            restored.to_v1().metadata["ipc2581_retained_standard_contour_land_geometry"], retained,
        )
        self.assertEqual((len(restored.pads), len(restored.vias), canonical_geometry_rows(restored)), (0, 0, []))

    def test_generated_arrow_is_design_bound_deterministic_and_target_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "generated-first.spike"
            second = Path(directory) / "generated-second.spike"
            first_manifest = write_spike_package(first, self.payload(), generate_geometry_tables=True)
            write_spike_package(second, self.payload(), generate_geometry_tables=True)
            first_open = read_spike_package(first, include_members=True)
            second_open = read_spike_package(second, include_members=True)
            table = first_open.payload["geometry"]["tables"][0]
            decoded = read_geometry_arrow_artifact(
                first, table["path"],
                expected_manifest_payload_sha256=first_manifest["manifest_payload_sha256"],
            )
        self.assertEqual(table["schema"], "spike/copper-geometry-arrow/v1")
        self.assertEqual(table["rows"], 0)
        self.assertEqual(
            first_open.members[table["path"]],
            second_open.members[second_open.payload["geometry"]["tables"][0]["path"]],
        )
        self.assertEqual(decoded["artifact"], first_open.members[table["path"]])
        self.assertEqual(decoded["rows"], [])

    def test_generated_arrow_v2_preserves_typed_conductor_paths(self):
        payload = self.payload()
        payload["design_ir"] = DesignIRV2.from_v1(DesignIR(
            design_id="path-fixture",
            name="Path fixture",
            source_format="ipc-2581",
            layers=[{"id": "L1", "name": "TOP", "type": "copper"}],
            nets=[{"id": "N1", "name": "VCC"}],
            tracks=[
                {"id": "route:segment:1", "net_id": "N1", "layer": "TOP", "start": [0, 0], "end": [5, 0], "width": 0.2,
                 "path_id": "route", "path_step_index": 0, "path_step_count": 2, "path_end_cap": "round", "path_join_style": "round"},
                {"id": "route:segment:2", "net_id": "N1", "layer": "TOP", "start": [5, 0], "end": [10, 3], "width": 0.2,
                 "path_id": "route", "path_step_index": 1, "path_step_count": 2, "path_end_cap": "round", "path_join_style": "round"},
            ],
            metadata={"source_sha256": "2" * 64},
        )).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "path.spike"
            manifest = write_spike_package(path, payload, generate_geometry_tables=True)
            opened = read_spike_package(path)
            table = opened.payload["geometry"]["tables"][0]
            decoded = read_geometry_arrow_artifact(
                path, table["path"],
                expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
            )

        self.assertEqual(table["schema"], "spike/copper-geometry-arrow/v2")
        self.assertEqual(table["rows"], 2)
        self.assertEqual(
            sorted((row["path_step_index"], row["path_id"]) for row in decoded["rows"]),
            [(0, "route"), (1, "route")],
        )

    def test_manufacturing_drill_round_trip_is_digest_bound_but_not_extra_copper(self):
        legacy = DesignIR(
            design_id="drill-fixture",
            name="Drill fixture",
            source_format="ipc-2581",
            layers=[
                {"id": "L1", "name": "TOP", "type": "copper"},
                {"id": "L2", "name": "BOTTOM", "type": "copper"},
            ],
            nets=[{"id": "N1", "name": "VCC"}],
            vias=[{
                "id": "VIA-1", "net_name": "VCC", "at": [4, 6],
                "diameter": 0.8, "drill": 0.4, "layers": ["TOP", "BOTTOM"],
            }],
            metadata={
                "source_sha256": "3" * 64,
                "manufacturing_drills": [{
                    "id": "HOLE-1", "source_layer_id": "TOP", "at": [4, 6],
                    "shape": "circle", "diameter_mm": 0.4,
                    "plating_status": "via", "plated": True,
                    "net_id": "VCC", "geometry_ref": "VIA-GEOMETRY",
                    "span_layer_ids": ["TOP", "BOTTOM"],
                    "span_provenance": "matched_owner",
                    "owner_kind": "via", "owner_id": "VIA-1",
                    "owner_match": "exact_source",
                }],
            },
        )
        design = DesignIRV2.from_v1(legacy)
        payload = self.payload()
        payload["design_ir"] = design.to_dict()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "drill.spike"
            manifest = write_spike_package(path, payload, generate_geometry_tables=True)
            opened = read_spike_package(path)
            reopened_design = DesignIRV2.from_dict(opened.payload["design_ir"])
            table = opened.payload["geometry"]["tables"][0]
            decoded = read_geometry_arrow_artifact(
                path, table["path"],
                expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
            )

        self.assertEqual(len(reopened_design.drills), 1)
        self.assertEqual(reopened_design.drills[0].owner_id, reopened_design.vias[0].id)
        self.assertEqual(
            reopened_design.to_v1().metadata["manufacturing_drills"][0]["owner_id"],
            "VIA-1",
        )
        self.assertEqual([row["kind"] for row in decoded["rows"]], ["via"])

    def test_generated_arrow_v3_preserves_exact_curved_zone_boundaries(self):
        legacy = DesignIR(
            design_id="curve-zone", name="Curve zone", source_format="ipc-2581",
            layers=[{"id": "L1", "name": "PWR1", "type": "plane"}],
            nets=[{"id": "N1", "name": "GND"}],
            zones=[{
                "id": "CONTOUR-1", "layer": "PWR1", "net_id": "N1",
                "boundary_rings": [
                    {"role": "outer", "start_mm": [0, 0], "segments": [
                        {"kind": "line", "end_mm": [4, 0]},
                        {"kind": "line", "end_mm": [4, 4]},
                        {"kind": "line", "end_mm": [0, 4]},
                        {"kind": "line", "end_mm": [0, 0]},
                    ]},
                    {"role": "cutout", "start_mm": [3, 2], "segments": [
                        {"kind": "arc", "end_mm": [1, 2], "center_mm": [2, 2], "clockwise": True},
                        {"kind": "arc", "end_mm": [3, 2], "center_mm": [2, 2], "clockwise": True},
                    ]},
                ],
                "fill_style_id": "SOLID_FILL", "fill_property": "FILL",
            }],
            metadata={"source_sha256": "4" * 64, "geometry_solver_ready": False},
        )
        payload = self.payload()
        payload["design_ir"] = DesignIRV2.from_v1(legacy).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "curve-zone.spike"
            manifest = write_spike_package(path, payload, generate_geometry_tables=True)
            opened = read_spike_package(path)
            table = opened.payload["geometry"]["tables"][0]
            decoded = read_geometry_arrow_artifact(
                path, table["path"],
                expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
            )
            restored = DesignIRV2.from_dict(opened.payload["design_ir"])

        self.assertEqual((table["schema"], table["rows"]), ("spike/copper-geometry-arrow/v3", 1))
        self.assertEqual(len(restored.zones[0].boundary_rings), 2)
        self.assertEqual(decoded["rows"][0]["boundary_rings"][1]["segments"][0]["kind"], "arc")

    def test_generated_arrow_v4_preserves_per_layer_land_profiles(self):
        legacy = DesignIR(
            design_id="land-profiles", name="Land profiles", source_format="ipc-2581",
            layers=[{"id": "L1", "name": "TOP", "type": "copper"}, {"id": "L2", "name": "BOTTOM", "type": "copper"}],
            nets=[{"id": "N1", "name": "VCC"}],
            vias=[{
                "id": "V1", "net_id": "N1", "at": [0, 0], "diameter": 1.0, "drill": 0.3,
                "layers": ["TOP", "BOTTOM"],
                "land_profiles": [
                    {"layer_id": "TOP", "use": "regular", "shape": "circle", "size_mm": [1.0, 1.0], "offset_mm": [0, 0], "source_primitive_id": "TOP-CIRCLE"},
                    {"layer_id": "BOTTOM", "use": "regular", "shape": "circle", "size_mm": [0.8, 0.8], "offset_mm": [0, 0], "source_primitive_id": "BOTTOM-CIRCLE"},
                ],
            }], metadata={"source_sha256": "5" * 64, "geometry_solver_ready": False},
        )
        payload = self.payload()
        payload["design_ir"] = DesignIRV2.from_v1(legacy).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "land-profiles.spike"
            manifest = write_spike_package(path, payload, generate_geometry_tables=True)
            opened = read_spike_package(path)
            table = opened.payload["geometry"]["tables"][0]
            decoded = read_geometry_arrow_artifact(
                path, table["path"], expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
            )
        self.assertEqual((table["schema"], table["rows"]), ("spike/copper-geometry-arrow/v4", 1))
        self.assertEqual(decoded["rows"][0]["land_profiles"][0]["source_primitive_id"], "TOP-CIRCLE")

    def test_geometry_index_rejects_orphans_and_target_reader_requires_verified_identity(self):
        with self.assertRaisesRegex(ProjectPackageError, "unindexed Arrow"):
            build_package_members(
                self.payload(), preserved_members={"geometry/orphan.arrow": b"not-arrow"},
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generated.spike"
            write_spike_package(path, self.payload(), generate_geometry_tables=True)
            with self.assertRaisesRegex(ProjectPackageError, "opened project manifest identity"):
                read_geometry_arrow_artifact(
                    path, "geometry/copper_geometry.arrow",
                    expected_manifest_payload_sha256="",
                )

    def test_targeted_arrow_reader_threads_the_row_budget_to_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generated.spike"
            payload = self.payload()
            payload["design_ir"] = DesignIRV2.from_v1(DesignIR(
                design_id="row-budget", name="Row budget", source_format="fixture",
                layers=[{"id": "L1", "name": "TOP", "type": "copper"}],
                nets=[{"id": "N1", "name": "VCC"}],
                tracks=[
                    {"id": "T1", "net_id": "N1", "layer": "TOP", "start": [0, 0], "end": [1, 0], "width": 0.2},
                    {"id": "T2", "net_id": "N1", "layer": "TOP", "start": [1, 0], "end": [2, 0], "width": 0.2},
                ],
                metadata={"source_sha256": "2" * 64},
            )).to_dict()
            manifest = write_spike_package(path, payload, generate_geometry_tables=True)
            with self.assertRaisesRegex(ProjectPackageError, "exceeds the 1-row limit"):
                read_geometry_arrow_artifact(
                    path, "geometry/copper_geometry.arrow",
                    expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
                    max_rows=1,
                )

    def test_arrow_reader_rejects_manifest_and_actual_member_size_before_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid.spike"
            # The rejection paths below precede Arrow decoding; use a small
            # opaque payload so this boundary test does not require pyarrow.
            with patch("python.spike_core.project_geometry_index.build_geometry_arrow", return_value=b"opaque-arrow-fixture"), patch(
                "python.spike_core.project_geometry_index.validate_geometry_arrow",
                return_value=[],
            ):
                manifest = write_spike_package(valid, self.payload(), generate_geometry_tables=True)
            identity = manifest["manifest_payload_sha256"]
            with patch(
                "python.spike_core.project_geometry_artifacts.PackageLimits",
                return_value=PackageLimits(max_manifest_bytes=64),
            ):
                with self.assertRaisesRegex(ProjectPackageError, "manifest exceeds"):
                    read_geometry_arrow_artifact(
                        valid, "geometry/copper_geometry.arrow",
                        expected_manifest_payload_sha256=identity,
                    )

            with zipfile.ZipFile(valid, "r") as source:
                archive_manifest = json.loads(source.read("manifest.json"))
                table_member = next(
                    item for item in archive_manifest["members"]
                    if item["path"] == "geometry/copper_geometry.arrow"
                )
                table_bytes = source.read("geometry/copper_geometry.arrow")
                members = {item.filename: source.read(item) for item in source.infolist()}

            # A deliberately underreported manifest size cannot bypass the
            # ZIP entry's byte budget before the payload is retained.
            table_member["size"] = 1
            unsigned = dict(archive_manifest)
            unsigned.pop("signature", None)
            unsigned.pop("manifest_payload_sha256", None)
            archive_manifest["manifest_payload_sha256"] = hashlib.sha256(
                (json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
            ).hexdigest()
            members["manifest.json"] = (
                json.dumps(archive_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            ).encode("utf-8")
            underreported = root / "underreported-arrow-record.spike"
            with zipfile.ZipFile(underreported, "w", allowZip64=True) as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            with self.assertRaisesRegex(ProjectPackageError, "table exceeds"):
                read_geometry_arrow_artifact(
                    underreported, "geometry/copper_geometry.arrow",
                    expected_manifest_payload_sha256=archive_manifest["manifest_payload_sha256"],
                    max_bytes=len(table_bytes) - 1,
                )

            # A manifest declaration over budget must also fail before the
            # payload is streamed, even when the ZIP member itself fits.
            table_member["size"] = len(table_bytes) + 1
            unsigned = dict(archive_manifest)
            unsigned.pop("signature", None)
            unsigned.pop("manifest_payload_sha256", None)
            archive_manifest["manifest_payload_sha256"] = hashlib.sha256(
                (json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
            ).hexdigest()
            members["manifest.json"] = (
                json.dumps(archive_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            ).encode("utf-8")
            oversized_record = root / "oversized-arrow-record.spike"
            with zipfile.ZipFile(oversized_record, "w", allowZip64=True) as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            with self.assertRaisesRegex(ProjectPackageError, "table exceeds"):
                read_geometry_arrow_artifact(
                    oversized_record, "geometry/copper_geometry.arrow",
                    expected_manifest_payload_sha256=archive_manifest["manifest_payload_sha256"],
                    max_bytes=len(table_bytes),
                )

            tampered = root / "mismatched-arrow.spike"
            with zipfile.ZipFile(valid, "r") as source:
                members = {item.filename: source.read(item) for item in source.infolist()}
            members["geometry/copper_geometry.arrow"] += b"unexpected-trailing-data"
            with zipfile.ZipFile(tampered, "w", allowZip64=True) as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            with self.assertRaisesRegex(ProjectPackageError, "size does not match"):
                read_geometry_arrow_artifact(
                    tampered, "geometry/copper_geometry.arrow",
                    expected_manifest_payload_sha256=identity,
                )

    def test_non_object_manifest_is_a_structured_package_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "array-manifest.spike"
            with zipfile.ZipFile(path, "w", allowZip64=True) as archive:
                archive.writestr("manifest.json", b"[]")
            with self.assertRaisesRegex(ProjectPackageError, "must be a JSON object"):
                read_project(path)

    def test_control_plane_json_limit_does_not_restrict_large_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control-plane-limit.spike"
            source_artifact = random.Random(31).randbytes(128 * 1024)
            write_spike_package(
                path, self.payload(), source_artifacts={"large-source.bin": source_artifact},
            )
            with zipfile.ZipFile(path, "r") as archive:
                json_sizes = [
                    info.file_size for info in archive.infolist()
                    if info.filename.endswith(".json") and info.filename != "manifest.json"
                ]
            control_plane_limit = max(json_sizes)

            # A binary artifact larger than the JSON cap remains governed by
            # the normal artifact/member limits and is still accepted.
            self.assertGreater(len(source_artifact), control_plane_limit)
            read_spike_package(
                path,
                limits=PackageLimits(max_control_plane_json_bytes=control_plane_limit,
                                     max_design_ir_json_bytes=control_plane_limit),
            )
            with self.assertRaisesRegex(ProjectPackageError, "control-plane JSON member exceeds"):
                read_spike_package(
                    path,
                    limits=PackageLimits(max_control_plane_json_bytes=control_plane_limit - 1,
                                         max_design_ir_json_bytes=control_plane_limit - 1),
                )

    def test_design_source_uri_is_package_local_present_and_digest_bound(self):
        source = b"(kicad_pcb (version 20240108))"
        digest = hashlib.sha256(source).hexdigest()
        payload = self.payload()
        payload["design_ir"]["source"]["source_digest"] = digest
        payload["design_ir"]["source"]["artifact_path"] = f"package:sources/{digest}.kicad_pcb"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_spike_package(
                root / "valid.spike", payload,
                source_artifacts={"fixture.kicad_pcb": source},
            )
            missing = json.loads(json.dumps(payload))
            missing["design_ir"]["source"]["artifact_path"] = f"package:sources/{'0' * 64}.kicad_pcb"
            with self.assertRaisesRegex(ProjectPackageError, "missing or does not match"):
                write_spike_package(
                    root / "missing.spike", missing,
                    source_artifacts={"fixture.kicad_pcb": source},
                )
            external = json.loads(json.dumps(payload))
            external["design_ir"]["source"]["artifact_path"] = "C:/untrusted/fixture.kicad_pcb"
            with self.assertRaisesRegex(ProjectPackageError, "safe package:sources URI"):
                write_spike_package(
                    root / "external.spike", external,
                    source_artifacts={"fixture.kicad_pcb": source},
                )

    def test_assembly_ir_save_reopen_is_canonical_and_deterministic(self):
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "assembly-fixture",
            "name": "Assembly fixture",
            "frame": {"frame_id": "assembly"},
            "boards": [
                {
                    "id": "board-a", "source_id": "native-a", "design_id": "design-a",
                    "frame": {"frame_id": "frame-a", "parent_frame_id": "assembly"},
                },
                {
                    "id": "board-b", "source_id": "native-b", "design_id": "design-b",
                    "frame": {
                        "frame_id": "frame-b", "parent_frame_id": "assembly",
                        "transform": [1, 0, 0, 75, 0, 1, 0, 0, 0, 0, 1, 10, 0, 0, 0, 1],
                    },
                },
            ],
            "harnesses": [{
                "id": "harness", "endpoint_a": "board-a:J1", "endpoint_b": "board-b:J2",
                "length_mm": 125, "conductor_material_id": "copper", "pin_map": {"1": "1"},
            }],
            "connector_mappings": [{
                "id": "map", "kind": "connector-pin-map",
                "data": {"endpoint_a": "board-a:J1", "endpoint_b": "board-b:J2"},
            }],
            "rigid_flex_links": [{
                "id": "flex", "kind": "rigid-flex-link",
                "data": {"board_a_id": "board-a", "board_b_id": "board-b"},
            }],
            "parts": [{
                "id": "case", "source_id": "step-case", "part_type": "enclosure",
                "model_id": "model-case", "material_id": "aluminium",
                "frame": {"frame_id": "frame-case", "parent_frame_id": "assembly"},
                "placement_policy": {
                    "contract": "spike/assembly-placement-policy/v1",
                    "translation_snap_mm": 0.5,
                    "rotation_snap_deg": 15,
                },
            }],
        })
        payload = self.payload()
        payload["assembly_ir"] = assembly.to_dict()
        artifact = b"ISO-10303-21;END-ISO-10303-21;"
        payload["models"] = {
            "contract": "spike/model-index/v1",
            "models": [{
                "id": "model-case", "source_id": "step-case", "name": "Case",
                "model_type": "step", "uri": "package:models/artifacts/case.step",
                "digest": hashlib.sha256(artifact).hexdigest(), "transform": [],
                "extensions": {},
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.spike"
            second = Path(directory) / "second.spike"
            write_spike_package(first, payload, model_artifacts={"case.step": artifact})
            write_spike_package(second, payload, model_artifacts={"case.step": artifact})
            reopened = read_spike_package(first)
            with zipfile.ZipFile(first) as first_zip, zipfile.ZipFile(second) as second_zip:
                first_member = first_zip.read("design/assembly-ir.json")
                second_member = second_zip.read("design/assembly-ir.json")

        self.assertEqual(reopened.payload["assembly_ir"], assembly.to_dict())
        self.assertEqual(reopened.manifest["schemas"]["assembly_placement_policy"], "spike/assembly-placement-policy/v1")
        self.assertEqual(reopened.payload["assembly_ir"]["parts"][0]["placement_policy"]["translation_snap_mm"], 0.5)
        self.assertEqual(AssemblyIRV1.from_dict(reopened.payload["assembly_ir"]).to_dict(), assembly.to_dict())
        self.assertEqual(first_member, second_member)

    def test_invalid_assembly_fails_closed_before_package_write(self):
        payload = self.payload()
        payload["assembly_ir"] = {
            "contract": "spike/assembly-ir/v1",
            "assembly_id": "invalid",
            "name": "Invalid",
            "boards": [{"id": "board-a", "design_id": ""}],
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProjectPackageError, "AssemblyIR payload is invalid"):
                write_spike_package(Path(directory) / "invalid.spike", payload)

    def test_assembly_part_requires_a_model_index_identity(self):
        payload = self.payload()
        payload["assembly_ir"] = AssemblyIRV1.from_dict({
            "assembly_id": "assembly", "name": "Missing model", "boards": [],
            "parts": [{
                "id": "case", "part_type": "enclosure", "model_id": "missing-model",
                "frame": {"frame_id": "case-frame", "parent_frame_id": "assembly"},
            }],
        }).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProjectPackageError, "missing model identities"):
                write_spike_package(Path(directory) / "invalid-model.spike", payload)

    def test_verified_artifacts_and_unknown_extensions_survive_resave(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.spike"
            resaved = Path(directory) / "resaved.spike"
            payload = self.payload()
            payload["extensions"] = {"vendor.example": {"future": True}}
            write_spike_package(
                original,
                payload,
                source_artifacts={"fixture.kicad_pcb": b"(kicad_pcb preserved)"},
                geometry_tables={"tracks": b"ARROW1-preserved"},
                model_artifacts={"fixture.step": b"STEP-preserved"},
                report_artifacts={"review.pdf": b"PDF-preserved"},
            )
            opened = read_spike_package(original, include_members=True)
            edited = dict(opened.payload)
            edited["project"] = {**edited["project"], "name": "Resaved"}
            write_spike_package(resaved, edited, preserved_members=opened.members)
            reopened = read_spike_package(resaved, include_members=True)

        self.assertEqual(reopened.payload["project"]["name"], "Resaved")
        self.assertTrue(reopened.payload["extensions"]["vendor.example"]["future"])
        for member in (
            next(name for name in opened.members if name.startswith("sources/")),
            "geometry/tracks.arrow",
            "models/artifacts/fixture.step",
            "reports/artifacts/review.pdf",
        ):
            self.assertEqual(reopened.members[member], opened.members[member])
        self.assertEqual(reopened.payload["geometry"], opened.payload["geometry"])

    def test_model_index_requires_matching_embedded_artifact(self):
        payload = self.payload()
        payload["models"] = {
            "contract": "spike/model-index/v1",
            "models": [{
                "id": "model-a",
                "name": "Enclosure",
                "model_type": "step",
                "uri": "package:models/artifacts/enclosure.step",
                "digest": "0" * 64,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ProjectPackageError, "artifact is missing"):
                write_spike_package(root / "missing.spike", payload)
            with self.assertRaisesRegex(ProjectPackageError, "digest does not match"):
                write_spike_package(
                    root / "mismatch.spike",
                    payload,
                    model_artifacts={"enclosure.step": b"ISO-10303-21;END-ISO-10303-21;"},
                )

    def test_model_index_round_trip_preserves_typed_metadata(self):
        artifact = b"ISO-10303-21;END-ISO-10303-21;"
        import hashlib
        payload = self.payload()
        payload["models"] = {
            "contract": "spike/model-index/v1",
            "models": [{
                "id": "model-a",
                "source_id": "native-a",
                "name": "Enclosure",
                "model_type": "step",
                "uri": "package:models/artifacts/enclosure.step",
                "digest": hashlib.sha256(artifact).hexdigest(),
                "vendor_extension": {"retained": True},
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.spike"
            write_spike_package(path, payload, model_artifacts={"enclosure.step": artifact})
            reopened = read_spike_package(path)
        self.assertEqual(reopened.payload["models"]["contract"], "spike/model-index/v1")
        self.assertTrue(reopened.payload["models"]["models"][0]["vendor_extension"]["retained"])

    def test_visual_model_reader_is_targeted_bounded_and_type_gated(self):
        import hashlib

        gltf = b'{"asset":{"version":"2.0"},"scenes":[{}],"nodes":[]}'
        step = b"ISO-10303-21;END-ISO-10303-21;"
        payload = self.payload()
        payload["models"] = {
            "contract": "spike/model-index/v1",
            "models": [
                {
                    "id": "visual-model",
                    "model_type": "gltf",
                    "uri": "package:models/artifacts/visual.gltf",
                    "digest": hashlib.sha256(gltf).hexdigest(),
                },
                {
                    "id": "visual-model-instance",
                    "model_type": "gltf",
                    "uri": "package:models/artifacts/visual.gltf",
                    "digest": hashlib.sha256(gltf).hexdigest(),
                },
                {
                    "id": "step-model",
                    "model_type": "step",
                    "uri": "package:models/artifacts/source.step",
                    "digest": hashlib.sha256(step).hexdigest(),
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "visual.spike"
            manifest = write_spike_package(
                path,
                payload,
                model_artifacts={"visual.gltf": gltf, "source.step": step},
                manifest_signer=lambda _: {
                    "algorithm": "ed25519", "key_id": "visual-reader-key",
                    "signature_base64url": "visual_reader_signature",
                },
            )
            with self.assertRaisesRegex(ProjectPackageError, "trusted manifest verifier"):
                read_visual_model_artifacts(
                    path, ["visual-model"],
                    expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
                    require_signature=True,
                )
            with self.assertRaisesRegex(ProjectPackageError, "signature verification failed"):
                read_visual_model_artifacts(
                    path, ["visual-model"],
                    expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
                    signature_verifier=lambda *_: False,
                )
            artifacts = read_visual_model_artifacts(
                path,
                ["visual-model", "visual-model-instance"],
                expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
                max_total_bytes=len(gltf),
                signature_verifier=lambda *_: True,
                require_signature=True,
            )
            with self.assertRaisesRegex(ProjectPackageError, "STEP requires tessellation"):
                read_visual_model_artifacts(
                    path, ["step-model"],
                    expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
                )
            with self.assertRaisesRegex(ProjectPackageError, "viewport limit"):
                read_visual_model_artifacts(
                    path, ["visual-model"],
                    expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
                    max_total_bytes=len(gltf) - 1,
                )
            with self.assertRaisesRegex(ProjectPackageError, "not indexed"):
                read_visual_model_artifacts(
                    path, ["missing-model"],
                    expected_manifest_payload_sha256=manifest["manifest_payload_sha256"],
                )
            with self.assertRaisesRegex(ProjectPackageError, "changed after its opened manifest identity"):
                read_visual_model_artifacts(
                    path, ["visual-model"],
                    expected_manifest_payload_sha256="0" * 64,
                )

            external = b'{"asset":{"version":"2.0"},"buffers":[{"uri":"https://example.invalid/model.bin","byteLength":4}]}'
            external_payload = self.payload()
            external_payload["models"] = {
                "contract": "spike/model-index/v1",
                "models": [{
                    "id": "external-model",
                    "model_type": "gltf",
                    "uri": "package:models/artifacts/external.gltf",
                    "digest": hashlib.sha256(external).hexdigest(),
                }],
            }
            external_path = Path(directory) / "external.spike"
            external_manifest = write_spike_package(
                external_path, external_payload, model_artifacts={"external.gltf": external},
            )
            with self.assertRaisesRegex(ProjectPackageError, "external resources"):
                read_visual_model_artifacts(
                    external_path, ["external-model"],
                    expected_manifest_payload_sha256=external_manifest["manifest_payload_sha256"],
                )

        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["model_id"], "visual-model")
        self.assertEqual(artifacts[0]["model_ids"], ["visual-model", "visual-model-instance"])
        self.assertEqual(artifacts[0]["artifact"], gltf)

    def test_targeted_source_and_model_readers_reject_underreported_zip_members_before_retention(self):
        gltf = b'{"asset":{"version":"2.0"},"scenes":[{}],"nodes":[]}'
        step = b"ISO-10303-21;END-ISO-10303-21;"
        source_bytes = b"(kicad_pcb (version 20240108))"
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        payload = self.payload()
        payload["design_ir"]["source"].update({
            "source_digest": source_digest,
            "artifact_path": f"package:sources/{source_digest}.kicad_pcb",
        })
        payload["models"] = {
            "contract": "spike/model-index/v1",
            "models": [
                {"id": "visual-model", "model_type": "gltf", "uri": "package:models/artifacts/visual.gltf", "digest": hashlib.sha256(gltf).hexdigest()},
                {"id": "step-model", "model_type": "step", "uri": "package:models/artifacts/source.step", "digest": hashlib.sha256(step).hexdigest()},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid.spike"
            write_spike_package(
                valid, payload, source_artifacts={"fixture.kicad_pcb": source_bytes},
                model_artifacts={"visual.gltf": gltf, "source.step": step},
            )
            source_tampered = _write_underreported_member(
                valid, root / "underreported-source.spike", f"sources/{source_digest}.kicad_pcb",
            )
            visual_tampered = _write_underreported_member(
                valid, root / "underreported-visual.spike", "models/artifacts/visual.gltf",
            )
            step_tampered = _write_underreported_member(
                valid, root / "underreported-step.spike", "models/artifacts/source.step",
            )

            with patch.object(project_model_artifacts, "_verify_member_stream", wraps=project_model_artifacts._verify_member_stream) as verify:
                with self.assertRaisesRegex(ProjectPackageError, "source exceeds"):
                    read_project_source_artifact(
                        root / "underreported-source.spike", f"package:sources/{source_digest}.kicad_pcb",
                        expected_manifest_payload_sha256=source_tampered["manifest_payload_sha256"],
                        expected_source_sha256=source_digest, max_bytes=len(source_bytes) - 1,
                    )
                verify.assert_not_called()

            for archive_path, identity, model_id, member_path, budget in (
                (root / "underreported-visual.spike", visual_tampered["manifest_payload_sha256"], "visual-model", "models/artifacts/visual.gltf", len(gltf) - 1),
                (root / "underreported-step.spike", step_tampered["manifest_payload_sha256"], "step-model", "models/artifacts/source.step", len(step) - 1),
            ):
                with self.subTest(member_path=member_path), patch.object(project_model_artifacts, "_verify_member_stream", wraps=project_model_artifacts._verify_member_stream) as verify:
                    with self.assertRaisesRegex(ProjectPackageError, "viewport limit"):
                        if model_id == "visual-model":
                            project_model_artifacts.read_visual_model_artifacts(
                                archive_path, [model_id], expected_manifest_payload_sha256=identity,
                                max_total_bytes=budget,
                            )
                        else:
                            read_step_model_artifact(
                                archive_path, model_id, expected_manifest_payload_sha256=identity,
                                max_total_bytes=budget,
                            )
                    self.assertFalse(any(call.args[1].filename == member_path for call in verify.call_args_list))

    def test_model_index_rejects_unsafe_uri_type_extension_and_transform(self):
        import hashlib

        artifact = b"ISO-10303-21;END-ISO-10303-21;"
        base_model = {
            "id": "model-a",
            "model_type": "step",
            "uri": "package:models/artifacts/enclosure.step",
            "digest": hashlib.sha256(artifact).hexdigest(),
        }
        invalid_cases = (
            ({**base_model, "uri": "package:models/artifacts/../enclosure.step"}, "safe embedded"),
            ({**base_model, "uri": None}, "package URI must be a string"),
            ({**base_model, "uri": "package:models/artifacts/enclosure.STEP"}, "extension does not match"),
            ({**base_model, "uri": "package:models/artifacts/enclosure.glb"}, "extension does not match"),
            ({**base_model, "model_type": "obj"}, "model_type must be one of"),
            ({**base_model, "model_type": None}, "model_type must be one of"),
            ({**base_model, "digest": None}, "valid SHA-256"),
            ({**base_model, "id": 7}, "missing or duplicate identity"),
            ({**base_model, "transform": [1.0, 2.0]}, "empty or contain 16"),
            ({**base_model, "transform": "identity"}, "empty or contain 16"),
            ({**base_model, "transform": [0.0] * 15 + [float("inf")]}, "finite numeric"),
            ({**base_model, "extensions": []}, "extensions must be an object"),
            ({**base_model, "extensions": {"bad key": True}}, "invalid extension name"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for position, (model, message) in enumerate(invalid_cases):
                with self.subTest(model=model), self.assertRaisesRegex(ProjectPackageError, message):
                    payload = self.payload()
                    payload["models"] = {"contract": "spike/model-index/v1", "models": [model]}
                    write_spike_package(
                        Path(directory) / f"invalid-{position}.spike",
                        payload,
                        model_artifacts={"enclosure.step": artifact, "enclosure.glb": artifact},
                    )

    def test_model_index_allows_consistent_shared_artifact_instancing(self):
        import hashlib

        artifact = b"ISO-10303-21;END-ISO-10303-21;"
        digest = hashlib.sha256(artifact).hexdigest()
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        translated = [1, 0, 0, 25, 0, 1, 0, 0, 0, 0, 1, 5, 0, 0, 0, 1]
        payload = self.payload()
        payload["models"] = {
            "contract": "spike/model-index/v1",
            "models": [
                {
                    "id": "model-a",
                    "model_type": "step",
                    "uri": "package:models/artifacts/shared.step",
                    "digest": digest,
                    "transform": identity,
                },
                {
                    "id": "model-b",
                    "model_type": "step",
                    "uri": "package:models/artifacts/shared.step",
                    "digest": digest,
                    "transform": translated,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.spike"
            manifest = write_spike_package(path, payload, model_artifacts={"shared.step": artifact})
            reopened = read_spike_package(path)

        self.assertEqual(len(reopened.payload["models"]["models"]), 2)
        self.assertEqual(reopened.payload["models"]["models"][1]["transform"][3], 25.0)
        self.assertEqual(manifest["schemas"]["model_index"], "spike/model-index/v1")

    def test_model_index_rejects_inconsistent_shared_artifact_claims(self):
        import hashlib

        artifact = b"ISO-10303-21;END-ISO-10303-21;"
        payload = self.payload()
        payload["models"] = {
            "contract": "spike/model-index/v1",
            "models": [
                {
                    "id": "model-a", "model_type": "step",
                    "uri": "package:models/artifacts/shared.step",
                    "digest": hashlib.sha256(artifact).hexdigest(),
                },
                {
                    "id": "model-b", "model_type": "step",
                    "uri": "package:models/artifacts/shared.step",
                    "digest": "0" * 64,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProjectPackageError, "inconsistent digest or model_type"):
                write_spike_package(
                    Path(directory) / "inconsistent.spike",
                    payload,
                    model_artifacts={"shared.step": artifact},
                )

    def test_all_declared_profiles_round_trip_with_conforming_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            portable = self.payload()
            exchange = self.payload()
            exchange["results"] = {"contract": "spike/result-index/v1", "runs": []}
            exchange["reports"] = {"contract": "spike/report-index/v1", "reports": []}
            result = self.payload()
            result["results"] = {
                "contract": "spike/result-index/v1",
                "runs": [{"id": "run-1", "design_id": result["design_ir"]["design_id"]}],
            }
            for profile, payload in (
                ("portable_project", portable),
                ("design_exchange", exchange),
                ("result_bundle", result),
            ):
                path = root / f"{profile}.spike"
                write_spike_package(path, payload, profile=profile)
                reopened = read_spike_package(path)
                self.assertEqual(reopened.manifest["profile"], profile)

    def test_profile_semantics_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            populated_exchange = self.payload()
            populated_exchange["results"] = {"runs": [{"id": "run-1"}]}
            with self.assertRaisesRegex(ProjectPackageError, "design_exchange.*result metadata"):
                write_spike_package(root / "exchange.spike", populated_exchange, profile="design_exchange")

            empty_result = self.payload()
            with self.assertRaisesRegex(ProjectPackageError, "result_bundle.*result metadata"):
                write_spike_package(root / "empty-result.spike", empty_result, profile="result_bundle")

            unaudited_result = self.payload()
            unaudited_result["results"] = {"runs": [{"id": "run-1"}]}
            unaudited_result["audit"] = []
            with self.assertRaisesRegex(ProjectPackageError, "result_bundle.*audit event"):
                write_spike_package(root / "unaudited-result.spike", unaudited_result, profile="result_bundle")

            with self.assertRaisesRegex(ProjectPackageError, "Unknown SPIKE package profile"):
                write_spike_package(root / "unknown.spike", self.payload(), profile="unknown")

    def test_tampered_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.spike"
            damaged = Path(directory) / "damaged.spike"
            write_spike_package(original, self.payload())
            with zipfile.ZipFile(original, "r") as source, zipfile.ZipFile(damaged, "w") as target:
                for info in source.infolist():
                    data = source.read(info.filename)
                    if info.filename == "project/project.json":
                        data += b" "
                    target.writestr(info, data)
            with self.assertRaisesRegex(ProjectPackageError, "integrity check failed"):
                read_spike_package(damaged)

    def test_signed_manifest_round_trip_and_required_trust(self):
        signed_payloads = []

        def signer(payload):
            signed_payloads.append(payload)
            return {
                "algorithm": "ed25519",
                "key_id": "test-release-key",
                "signature_base64url": "unit_test_signature",
            }

        def verifier(payload, signature):
            return payload == signed_payloads[0] and signature == {
                "contract": "spike/manifest-signature/v1",
                "algorithm": "ed25519",
                "key_id": "test-release-key",
                "signed_payload_sha256": signature["signed_payload_sha256"],
                "signature_base64url": "unit_test_signature",
            }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "signed.spike"
            manifest = write_spike_package(path, self.payload(), manifest_signer=signer)
            unverified = read_spike_package(path)
            verified = read_spike_package(path, signature_verifier=verifier, require_signature=True)

        self.assertEqual(manifest["signature"]["algorithm"], "ed25519")
        self.assertTrue(unverified.signature_present)
        self.assertIsNone(unverified.signature_verified)
        self.assertTrue(verified.signature_verified)

    def test_signature_policy_and_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unsigned = root / "unsigned.spike"
            signed = root / "signed.spike"
            damaged = root / "damaged.spike"
            write_spike_package(unsigned, self.payload())
            with self.assertRaisesRegex(ProjectPackageError, "signed package manifest is required"):
                read_spike_package(unsigned, require_signature=True)

            write_spike_package(signed, self.payload(), manifest_signer=lambda _: {
                "algorithm": "ed25519",
                "key_id": "test-release-key",
                "signature_base64url": "valid_signature_shape",
            })
            with self.assertRaisesRegex(ProjectPackageError, "trusted manifest verifier"):
                read_spike_package(signed, require_signature=True)
            with self.assertRaisesRegex(ProjectPackageError, "signature verification failed"):
                read_spike_package(signed, signature_verifier=lambda *_: False)

            with zipfile.ZipFile(signed, "r") as source, zipfile.ZipFile(damaged, "w") as target:
                for info in source.infolist():
                    data = source.read(info.filename)
                    if info.filename == "manifest.json":
                        parsed = json.loads(data)
                        parsed["signature"]["signed_payload_sha256"] = "0" * 64
                        data = json.dumps(parsed).encode("utf-8")
                    target.writestr(info, data)
            with self.assertRaisesRegex(ProjectPackageError, "signed-payload digest is invalid"):
                read_spike_package(damaged)

    def test_targeted_manifest_signature_policy_matches_full_package_reads(self):
        manifest = {"format": "spike-project-package/v3", "contract": "spike/project-package/v3"}
        from python.spike_core.project_package import manifest_signature_payload
        signed_payload = manifest_signature_payload(manifest)
        signature = {
            "contract": "spike/manifest-signature/v1", "algorithm": "ed25519",
            "key_id": "targeted-test-key", "signed_payload_sha256": hashlib.sha256(signed_payload).hexdigest(),
            "signature_base64url": "targeted_test_signature",
        }
        signed_manifest = {**manifest, "signature": signature}

        validate_targeted_manifest_signature(manifest)
        with self.assertRaisesRegex(ProjectPackageError, "signed package manifest is required"):
            validate_targeted_manifest_signature(manifest, require_signature=True)
        with self.assertRaisesRegex(ProjectPackageError, "trusted manifest verifier"):
            validate_targeted_manifest_signature(signed_manifest, require_signature=True)
        with self.assertRaisesRegex(ProjectPackageError, "signature verification failed"):
            validate_targeted_manifest_signature(signed_manifest, signature_verifier=lambda *_: False)
        with self.assertRaisesRegex(ProjectPackageError, "signature verification failed"):
            validate_targeted_manifest_signature(
                signed_manifest, signature_verifier=lambda *_: (_ for _ in ()).throw(RuntimeError("boom")),
            )
        observed = []
        validate_targeted_manifest_signature(
            signed_manifest,
            signature_verifier=lambda payload, envelope: observed.append((payload, envelope)) or True,
            require_signature=True,
        )
        self.assertEqual(observed, [(signed_payload, signature)])
        with self.assertRaisesRegex(ProjectPackageError, "signature must be an object"):
            validate_targeted_manifest_signature({**manifest, "signature": None})
        with self.assertRaisesRegex(ProjectPackageError, "signature algorithm"):
            validate_targeted_manifest_signature({**signed_manifest, "signature": {**signature, "algorithm": "rsa"}})

    def test_traversal_and_duplicate_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            traversal = Path(directory) / "traversal.spike"
            with zipfile.ZipFile(traversal, "w") as archive:
                archive.writestr("manifest.json", "{}")
                archive.writestr("../escape", "bad")
            with self.assertRaisesRegex(ProjectPackageError, "Unsafe package member"):
                read_spike_package(traversal)

            duplicate = Path(directory) / "duplicate.spike"
            with zipfile.ZipFile(duplicate, "w") as archive:
                archive.writestr("manifest.json", "{}")
                # The malformed fixture deliberately triggers zipfile's warning.
                # Assert it locally so -W error still exercises reader rejection.
                with self.assertWarnsRegex(UserWarning, "Duplicate name"):
                    archive.writestr("manifest.json", "{}")
            with self.assertRaisesRegex(ProjectPackageError, "Duplicate package member"):
                read_spike_package(duplicate)

    def test_expanded_size_limit_is_enforced_before_member_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.spike"
            write_spike_package(path, self.payload())
            with self.assertRaisesRegex(ProjectPackageError, "expanded size"):
                read_spike_package(path, limits=PackageLimits(max_total_bytes=100))

    def test_large_artifacts_are_verified_with_streaming_reads(self):
        artifact = random.Random(17).randbytes(3 * 1024 * 1024)
        original_read = zipfile.ZipFile.read

        def manifest_only_read(archive, name, *args, **kwargs):
            member_name = name.filename if isinstance(name, zipfile.ZipInfo) else str(name)
            if member_name != "manifest.json":
                raise AssertionError(f"Whole-member read used for {member_name}")
            return original_read(archive, name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.spike"
            write_spike_package(path, self.payload(), source_artifacts={"large.bin": artifact})
            with patch.object(zipfile.ZipFile, "read", autospec=True, side_effect=manifest_only_read):
                verified = read_spike_package(path)
                retained = read_spike_package(path, include_members=True)

        source_name = next(name for name in retained.members if name.startswith("sources/"))
        self.assertEqual(verified.members, {})
        self.assertEqual(retained.members[source_name], artifact)

    def test_v2_json_migrates_in_memory_and_preserves_unknown_fields(self):
        legacy = {
            "format": "spike-project-package/v2",
            "project": {"name": "legacy.spike"},
            "design": {"source_file": "legacy.kicad_pcb", "source_board": "(kicad_pcb)", "layers": [], "nets": []},
            "analysis": {"mode": "dc"},
            "future_vendor_field": {"keep": True},
        }
        migrated = migrate_legacy_payload(legacy)
        self.assertEqual(migrated["design_ir"]["contract"], "spike/design-ir/v2")
        self.assertTrue(migrated["extensions"]["legacy"]["future_vendor_field"]["keep"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.spike"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            result = read_project(path)
        self.assertTrue(result.migrated)
        self.assertEqual(result.source_format, "spike-project-package/v2")


if __name__ == "__main__":
    unittest.main()
