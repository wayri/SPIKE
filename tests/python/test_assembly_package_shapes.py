"""Exact package-shape ownership, reference, and artifact-integrity regressions."""

from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from python.spike_core import project_model_artifacts
from python.spike_core.assembly_package_shapes import (
    AssemblyPackageShapeError,
    canonicalize_assembly_package_shapes,
    model_transform_sha256,
    selector_inventory_sha256,
)
from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import AssemblyIRV1, DesignIRV2
from python.spike_core.design_ir_v2_schema import canonical_uuid
from python.spike_core.project_package import ProjectPackageError, read_spike_package, write_spike_package
from python.spike_core.project_model_artifacts import read_package_shape_selector_previews
from python.spike_core.service_project_handlers import handle_project_request


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


def _selector_preview_glb(entities):
    selected = [item for item in entities if item["kind"] in {"axis", "face", "edge"}]
    binary = bytearray()
    views = []
    accessors = []
    meshes = []
    nodes = []
    for item in selected:
        positions = [0.0, 0.0, 0.0, 0.001, 0.0, 0.0]
        if item["kind"] == "face":
            positions = [0.0, 0.0, 0.0, 0.001, 0.0, 0.0, 0.0, 0.001, 0.0]
        raw = struct.pack(f"<{len(positions)}f", *positions)
        offset = len(binary); binary.extend(raw); binary.extend(b"\x00" * ((-len(binary)) % 4))
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw), "target": 34962})
        accessors.append({"bufferView": len(views) - 1, "componentType": 5126, "count": len(positions) // 3, "type": "VEC3"})
        primitive = {"attributes": {"POSITION": len(accessors) - 1}, "mode": 4 if item["kind"] == "face" else 3 if item["kind"] == "edge" else 1}
        if item["kind"] == "face":
            raw = struct.pack("<3I", 0, 1, 2)
            offset = len(binary); binary.extend(raw); binary.extend(b"\x00" * ((-len(binary)) % 4))
            views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw), "target": 34963})
            accessors.append({"bufferView": len(views) - 1, "componentType": 5125, "count": 3, "type": "SCALAR"})
            primitive["indices"] = len(accessors) - 1
        meshes.append({"primitives": [primitive]})
        nodes.append({"mesh": len(meshes) - 1, "extras": {
            "contract": "spike/package-shape-selector-node/v1", "topology_id": item["topology_id"],
            "topology_kind": item["kind"], "native_persistent_id": item["native_persistent_id"],
        }})
    document = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes, "buffers": [{"byteLength": len(binary)}], "bufferViews": views, "accessors": accessors}
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    binary.extend(b"\x00" * ((-len(binary)) % 4))
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return b"".join((struct.pack("<4sII", b"glTF", 2, total), struct.pack("<II", len(json_chunk), 0x4E4F534A), json_chunk, struct.pack("<II", len(binary), 0x004E4942), bytes(binary)))


class AssemblyPackageShapeTests(unittest.TestCase):
    def fixture(self):
        step_a = b"ISO-10303-21;A;END-ISO-10303-21;"
        step_b = b"ISO-10303-21;B;END-ISO-10303-21;"
        topology_a = b"SPKSHAPE-V1-A"
        topology_b = b"SPKSHAPE-V1-B"
        digest_a, digest_b = hashlib.sha256(step_a).hexdigest(), hashlib.sha256(step_b).hexdigest()
        model_a, model_b = "step-model-a", "step-model-b"
        shape_a = canonical_uuid("step", digest_a, "package-shape", model_a)
        shape_b = canonical_uuid("step", digest_b, "package-shape", model_b)

        def entity(source_digest, kind, native_id, *, axis=None, surface=None, curve=None, geometry=None):
            value = {
                "topology_id": canonical_uuid("step", source_digest, kind, native_id),
                "kind": kind,
                "native_persistent_id": native_id,
                "fingerprint_sha256": hashlib.sha256(f"{source_digest}:{kind}:{native_id}".encode()).hexdigest(),
                "support": {"surface_kind": surface, "curve_kind": curve, "axis_topology_id": axis},
            }
            if geometry is not None:
                value["geometry"] = geometry
            return value

        geometry_base = {"contract": "spike/package-shape-selector-geometry/v1", "coordinate_space": "shape_local_mm", "representation": "axis", "direction": [0.0, 0.0, 1.0], "radius_mm": None}
        axis_a = entity(digest_a, "axis", "axis:cylinder-1", geometry={**geometry_base, "origin_mm": [0.0, 0.0, 0.0]})
        face_a = entity(digest_a, "face", "face:cylinder-1", axis=axis_a["topology_id"], surface="cylinder")
        edge_a = entity(digest_a, "edge", "edge:circle-1", curve="circle")
        axis_b = entity(digest_b, "axis", "axis:cylinder-1", geometry={**geometry_base, "origin_mm": [10.0, 0.0, 0.0]})
        face_b = entity(digest_b, "face", "face:cylinder-1", axis=axis_b["topology_id"], surface="cylinder")
        edge_b = entity(digest_b, "edge", "edge:circle-1", curve="circle")
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "shape-assembly", "name": "Shape assembly", "boards": [],
            "parts": [
                {"id": "part-a", "part_type": "mechanical", "model_id": model_a, "frame": {"frame_id": "frame-a", "parent_frame_id": "assembly"}},
                {"id": "part-b", "part_type": "mechanical", "model_id": model_b, "frame": {"frame_id": "frame-b", "parent_frame_id": "assembly"}},
            ],
            "thermal_contacts": [{"id": "contact", "endpoint_a": "legacy-a", "endpoint_b": "legacy-b", "contact_type": "surface"}],
            "electrical_bonds": [{"id": "bond", "endpoint_a": "legacy-a", "endpoint_b": "legacy-b", "bond_type": "strap"}],
        }).to_dict()
        models = {
            "contract": "spike/model-index/v1",
            "models": [
                {"id": model_a, "source_id": "source-a", "name": "A", "model_type": "step", "uri": "package:models/artifacts/a.step", "digest": digest_a, "transform": [], "extensions": {}},
                {"id": model_b, "source_id": "source-b", "name": "B", "model_type": "step", "uri": "package:models/artifacts/b.step", "digest": digest_b, "transform": [], "extensions": {}},
            ],
        }

        def reference(part_id, shape_id, item):
            return {"ref_kind": "package_shape_topology", "part_id": part_id, "shape_id": shape_id, "topology_id": item["topology_id"], "topology_kind": item["kind"]}

        index = {
            "contract": "spike/assembly-package-shapes/v1",
            "assembly_id": assembly["assembly_id"],
            "shapes": [
                {
                    "shape_id": shape_a, "part_id": "part-a", "source_model_id": model_a,
                    "source_artifact_uri": "package:models/artifacts/a.step", "source_sha256": digest_a,
                    "topology_artifact_uri": f"package:geometry/package-shapes/{shape_a}.spkshape",
                    "topology_artifact_sha256": hashlib.sha256(topology_a).hexdigest(),
                    "kernel": {"id": "fixture-kernel", "contract": "spike/package-shape-kernel/v1", "version": "1.0"},
                    "extraction": {"status": "complete", "source_format": "step", "source_model_transform_sha256": model_transform_sha256([]), "topology_ready": True, "solver_ready": False},
                    "entities": [axis_a, face_a, edge_a], "extensions": {},
                },
                {
                    "shape_id": shape_b, "part_id": "part-b", "source_model_id": model_b,
                    "source_artifact_uri": "package:models/artifacts/b.step", "source_sha256": digest_b,
                    "topology_artifact_uri": f"package:geometry/package-shapes/{shape_b}.spkshape",
                    "topology_artifact_sha256": hashlib.sha256(topology_b).hexdigest(),
                    "kernel": {"id": "fixture-kernel", "contract": "spike/package-shape-kernel/v1", "version": "1.0"},
                    "extraction": {"status": "complete", "source_format": "step", "source_model_transform_sha256": model_transform_sha256([]), "topology_ready": True, "solver_ready": False},
                    "entities": [axis_b, face_b, edge_b], "extensions": {},
                },
            ],
            "constraints": [
                {"constraint_id": "concentric", "kind": "concentric", "references": [reference("part-a", shape_a, axis_a), reference("part-b", shape_b, axis_b)], "value_mm": None, "value_deg": None, "status": "defined"},
                {"constraint_id": "distance", "kind": "distance", "references": [reference("part-a", shape_a, face_a), reference("part-b", shape_b, face_b)], "value_mm": 1.5, "value_deg": None, "status": "defined"},
            ],
            "thermal_contact_bindings": [{"assembly_entity_id": "contact", "endpoint_a": reference("part-a", shape_a, face_a), "endpoint_b": reference("part-b", shape_b, face_b)}],
            "electrical_bond_bindings": [{"assembly_entity_id": "bond", "endpoint_a": reference("part-a", shape_a, edge_a), "endpoint_b": reference("part-b", shape_b, edge_b)}],
            "extensions": {}, "metadata": {},
        }
        return assembly, models, index, {"a.step": step_a, "b.step": step_b}, {f"{shape_a}.spkshape": topology_a, f"{shape_b}.spkshape": topology_b}

    def test_canonical_contract_resolves_shapes_constraints_and_bindings(self):
        assembly, models, index, _, _ = self.fixture()
        canonical = canonicalize_assembly_package_shapes(index, assembly, models)
        self.assertEqual(len(canonical["shapes"]), 2)
        self.assertEqual(canonical["constraints"][0]["kind"], "concentric")
        self.assertEqual(canonical["thermal_contact_bindings"][0]["assembly_entity_id"], "contact")
        self.assertFalse(canonical["shapes"][0]["extraction"]["solver_ready"])

    def test_foreign_part_wrong_kind_source_mismatch_and_nonfinite_value_fail(self):
        assembly, models, index, _, _ = self.fixture()
        invalid_cases = []
        foreign = {**index, "constraints": [dict(index["constraints"][0])]}
        foreign["constraints"][0]["references"] = [dict(item) for item in index["constraints"][0]["references"]]
        foreign["constraints"][0]["references"][0]["part_id"] = "part-b"
        invalid_cases.append((foreign, "does not own"))
        wrong_kind = {**index, "constraints": [dict(index["constraints"][0])]}
        wrong_kind["constraints"][0]["references"] = [dict(item) for item in index["constraints"][0]["references"]]
        wrong_kind["constraints"][0]["references"][0]["topology_kind"] = "face"
        invalid_cases.append((wrong_kind, "does not resolve"))
        source = {**index, "shapes": [dict(item) for item in index["shapes"]]}
        source["shapes"][0]["source_sha256"] = "0" * 64
        invalid_cases.append((source, "does not match"))
        nonfinite = {**index, "constraints": [dict(item) for item in index["constraints"]]}
        nonfinite["constraints"][1]["value_mm"] = float("nan")
        invalid_cases.append((nonfinite, "finite"))
        for invalid, message in invalid_cases:
            with self.subTest(message=message), self.assertRaisesRegex(AssemblyPackageShapeError, message):
                canonicalize_assembly_package_shapes(invalid, assembly, models)

    def test_package_save_reopen_is_digest_bound_and_lossless(self):
        assembly, models, index, model_artifacts, shape_artifacts = self.fixture()
        design = DesignIRV2.from_v1(DesignIR(
            design_id="shape-design", name="Shape design", source_format="neutral",
            layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "7" * 64},
        ))
        payload = {"project": {"id": "shape-project", "name": "Shape project"}, "design_ir": design.to_dict(), "assembly_ir": assembly, "models": models, "assembly_package_shapes": index}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shapes.spike"
            manifest = write_spike_package(path, payload, model_artifacts=model_artifacts, package_shape_artifacts=shape_artifacts)
            reopened = read_spike_package(path, include_members=True)
            with self.assertRaisesRegex(ProjectPackageError, "topology artifact is missing"):
                write_spike_package(Path(directory) / "missing.spike", payload, model_artifacts=model_artifacts)
            corrupt = dict(shape_artifacts)
            corrupt[next(iter(corrupt))] = b"corrupt"
            with self.assertRaisesRegex(ProjectPackageError, "digest does not match"):
                write_spike_package(Path(directory) / "corrupt.spike", payload, model_artifacts=model_artifacts, package_shape_artifacts=corrupt)
        self.assertEqual(manifest["schemas"]["assembly_package_shapes"], "spike/assembly-package-shapes/v1")
        self.assertEqual(reopened.payload["assembly_package_shapes"]["constraints"], index["constraints"])
        self.assertTrue(all(name in reopened.members for name in ("geometry/package-shapes/" + item for item in shape_artifacts)))

    def test_optional_selector_preview_is_source_topology_inventory_and_member_bound(self):
        assembly, models, index, model_artifacts, shape_artifacts = self.fixture()
        preview_bytes = b"glTF-selector-preview"
        first = index["shapes"][0]
        preview_name = f'{first["shape_id"]}.spkselect.glb'
        first["selector_preview"] = {
            "contract": "spike/package-shape-selector-preview/v1",
            "artifact_uri": f"package:geometry/package-shapes/{preview_name}",
            "artifact_sha256": hashlib.sha256(preview_bytes).hexdigest(),
            "source_sha256": first["source_sha256"],
            "topology_artifact_sha256": first["topology_artifact_sha256"],
            "selector_inventory_sha256": selector_inventory_sha256(first["entities"]),
            "freecad_version": "1.1.3",
            "linear_deflection_mm": 0.1,
            "face_count": 1,
            "edge_count": 1,
            "axis_count": 1,
            "visual_only": True,
            "solver_ready": False,
        }
        canonical = canonicalize_assembly_package_shapes(index, assembly, models)
        self.assertEqual(canonical["shapes"][0]["selector_preview"]["artifact_uri"], first["selector_preview"]["artifact_uri"])

        design = DesignIRV2.from_v1(DesignIR(
            design_id="shape-preview-design", name="Shape preview design", source_format="neutral",
            layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "8" * 64},
        ))
        payload = {"project": {"id": "shape-preview-project", "name": "Shape preview project"}, "design_ir": design.to_dict(), "assembly_ir": assembly, "models": models, "assembly_package_shapes": index}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.spike"
            write_spike_package(
                path, payload, model_artifacts=model_artifacts,
                package_shape_artifacts=shape_artifacts,
                package_shape_preview_artifacts={preview_name: preview_bytes},
            )
            reopened = read_spike_package(path, include_members=True)
            self.assertEqual(reopened.members[f"geometry/package-shapes/{preview_name}"], preview_bytes)
            with self.assertRaisesRegex(ProjectPackageError, "selector-preview artifact is missing"):
                write_spike_package(
                    Path(directory) / "missing-preview.spike", payload,
                    model_artifacts=model_artifacts, package_shape_artifacts=shape_artifacts,
                )
            with self.assertRaisesRegex(ProjectPackageError, "selector-preview artifact digest does not match"):
                write_spike_package(
                    Path(directory) / "corrupt-preview.spike", payload,
                    model_artifacts=model_artifacts, package_shape_artifacts=shape_artifacts,
                    package_shape_preview_artifacts={preview_name: b"corrupt"},
                )

        invalid_cases = []
        for field, value, message in (
            ("source_sha256", "0" * 64, "not bound"),
            ("topology_artifact_sha256", "0" * 64, "not bound"),
            ("selector_inventory_sha256", "0" * 64, "does not match"),
            ("face_count", 2, "face_count"),
            ("linear_deflection_mm", 0, "deflection"),
            ("solver_ready", True, "visual-only"),
        ):
            invalid = {**index, "shapes": [dict(item) for item in index["shapes"]]}
            invalid["shapes"][0]["selector_preview"] = dict(first["selector_preview"])
            invalid["shapes"][0]["selector_preview"][field] = value
            invalid_cases.append((invalid, message))
        unsafe = {**index, "shapes": [dict(item) for item in index["shapes"]]}
        unsafe["shapes"][0]["selector_preview"] = dict(first["selector_preview"])
        unsafe["shapes"][0]["selector_preview"]["artifact_uri"] = "package:geometry/package-shapes/../escape.spkselect.glb"
        invalid_cases.append((unsafe, "unsafe"))
        for invalid, message in invalid_cases:
            with self.subTest(message=message), self.assertRaisesRegex(AssemblyPackageShapeError, message):
                canonicalize_assembly_package_shapes(invalid, assembly, models)

    def test_selector_preview_reader_is_manifest_bound_and_worker_projects_bytes(self):
        assembly, models, index, model_artifacts, shape_artifacts = self.fixture()
        first = index["shapes"][0]
        preview_bytes = _selector_preview_glb(first["entities"])
        preview_name = f'{first["shape_id"]}.spkselect.glb'
        first["selector_preview"] = {
            "contract": "spike/package-shape-selector-preview/v1",
            "artifact_uri": f"package:geometry/package-shapes/{preview_name}",
            "artifact_sha256": hashlib.sha256(preview_bytes).hexdigest(),
            "source_sha256": first["source_sha256"],
            "topology_artifact_sha256": first["topology_artifact_sha256"],
            "selector_inventory_sha256": selector_inventory_sha256(first["entities"]),
            "freecad_version": "1.1.3", "linear_deflection_mm": 0.1,
            "face_count": 1, "edge_count": 1, "axis_count": 1,
            "visual_only": True, "solver_ready": False,
        }
        design = DesignIRV2.from_v1(DesignIR(
            design_id="shape-reader", name="Shape reader", source_format="neutral",
            layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "a" * 64},
        ))
        payload = {"project": {"id": "shape-reader", "name": "Shape reader"}, "design_ir": design.to_dict(), "assembly_ir": assembly, "models": models, "assembly_package_shapes": index}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reader.spike"
            manifest = write_spike_package(path, payload, model_artifacts=model_artifacts, package_shape_artifacts=shape_artifacts, package_shape_preview_artifacts={preview_name: preview_bytes})
            artifacts = read_package_shape_selector_previews(path, [first["shape_id"]], expected_manifest_payload_sha256=manifest["manifest_payload_sha256"])
            self.assertEqual(artifacts[0]["artifact"], preview_bytes)
            self.assertEqual(artifacts[0]["part_id"], first["part_id"])
            response = handle_project_request(
                "read_project_package_shape_selector_previews",
                {"path": str(path), "shape_ids": [first["shape_id"]], "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"]},
                request_id="preview-read", application_version="test",
            )
            self.assertTrue(response["ok"], response)
            self.assertEqual(response["result"]["contract"], "spike/project-package-shape-selector-previews/v1")
            with self.assertRaisesRegex(ProjectPackageError, "changed after"):
                read_package_shape_selector_previews(path, [first["shape_id"]], expected_manifest_payload_sha256="0" * 64)
            with self.assertRaisesRegex(ProjectPackageError, "duplicated"):
                read_package_shape_selector_previews(path, [first["shape_id"], first["shape_id"]], expected_manifest_payload_sha256=manifest["manifest_payload_sha256"])
            with self.assertRaisesRegex(ProjectPackageError, "no selector preview"):
                read_package_shape_selector_previews(path, [index["shapes"][1]["shape_id"]], expected_manifest_payload_sha256=manifest["manifest_payload_sha256"])

            underreported = _write_underreported_member(
                path, Path(directory) / "underreported-preview.spike",
                f"geometry/package-shapes/{preview_name}",
            )
            with patch.object(project_model_artifacts, "_verify_member_stream", wraps=project_model_artifacts._verify_member_stream) as verify:
                with self.assertRaisesRegex(ProjectPackageError, "byte limit"):
                    read_package_shape_selector_previews(
                        Path(directory) / "underreported-preview.spike", [first["shape_id"]],
                        expected_manifest_payload_sha256=underreported["manifest_payload_sha256"],
                        max_total_bytes=len(preview_bytes) - 1,
                    )
                self.assertFalse(any(
                    call.args[1].filename == f"geometry/package-shapes/{preview_name}"
                    for call in verify.call_args_list
                ))


if __name__ == "__main__":
    unittest.main()
