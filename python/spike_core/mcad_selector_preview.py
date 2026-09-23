"""Bounded exact-BREP selector-preview generation and independent validation."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .assembly_package_shapes import MAX_PREVIEW_SELECTORS, PACKAGE_SHAPE_SELECTOR_PREVIEW_V1, selector_inventory_sha256
from .mcad_importer import McadImportError, validate_visual_mcad_artifact
from .mcad_tessellation import _freecad_path
from .sparselizard_process import SparseLizardAdapterError, run_adapter_process


class McadSelectorPreviewError(RuntimeError):
    """Raised when an exact selector preview fails its trust or resource contract."""


@dataclass(frozen=True)
class SelectorPreviewPolicy:
    max_topology_bytes: int = 256 * 1024**2
    max_output_bytes: int = 128 * 1024**2
    max_report_bytes: int = 4 * 1024**2
    max_selectors: int = MAX_PREVIEW_SELECTORS
    max_face_vertices: int = 2_000_000
    max_face_triangles: int = 2_000_000
    max_line_vertices: int = 2_000_000
    timeout_s: int = 300
    memory_limit_mb: int = 4096
    stream_limit_bytes: int = 1024**2
    linear_deflection_mm: float = 0.1

    def __post_init__(self) -> None:
        integers = (self.max_topology_bytes, self.max_output_bytes, self.max_report_bytes, self.max_selectors, self.max_face_vertices, self.max_face_triangles, self.max_line_vertices, self.timeout_s, self.memory_limit_mb, self.stream_limit_bytes)
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in integers):
            raise ValueError("Selector-preview resource limits must be positive integers.")
        if self.max_topology_bytes > 512 * 1024**2 or self.max_output_bytes > 128 * 1024**2 or self.max_report_bytes > 4 * 1024**2 or self.max_selectors > MAX_PREVIEW_SELECTORS:
            raise ValueError("Selector-preview limits exceed the reviewed ceiling.")
        if max(self.max_face_vertices, self.max_face_triangles, self.max_line_vertices) > 2_000_000 or self.timeout_s > 300 or self.memory_limit_mb > 4096 or self.stream_limit_bytes > 4 * 1024**2:
            raise ValueError("Selector-preview process or geometry limits exceed the reviewed ceiling.")
        if not math.isfinite(self.linear_deflection_mm) or not 0.001 <= self.linear_deflection_mm <= 10.0:
            raise ValueError("Selector-preview linear_deflection_mm must be within 0.001 through 10 mm.")


@dataclass(frozen=True)
class SelectorPreviewResult:
    source_sha256: str
    topology_artifact_sha256: str
    selector_inventory_sha256: str
    artifact_name: str
    artifact_sha256: str
    artifact_bytes: bytes
    freecad_version: str
    linear_deflection_mm: float
    face_count: int
    edge_count: int
    axis_count: int
    visual_only: bool = True
    solver_ready: bool = False
    contract: str = PACKAGE_SHAPE_SELECTOR_PREVIEW_V1

    def to_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key != "artifact_bytes"}


def _glb_document(payload: bytes) -> tuple[Mapping[str, Any], bytes]:
    try:
        validate_visual_mcad_artifact("glb", payload)
    except McadImportError as exc:
        raise McadSelectorPreviewError(str(exc)) from exc
    json_length, json_type = struct.unpack_from("<II", payload, 12)
    binary_offset = 20 + json_length
    if binary_offset + 8 > len(payload):
        raise McadSelectorPreviewError("Selector-preview GLB is missing its binary chunk.")
    binary_length, binary_type = struct.unpack_from("<II", payload, binary_offset)
    if json_type != 0x4E4F534A or binary_type != 0x004E4942 or binary_offset + 8 + binary_length != len(payload):
        raise McadSelectorPreviewError("Selector-preview GLB chunk layout is invalid.")
    document = json.loads(payload[20:20 + json_length].rstrip(b" \x00").decode("utf-8"))
    return document, payload[binary_offset + 8:]


def _validate_selector_glb(payload: bytes, entities: Sequence[Mapping[str, Any]], policy: SelectorPreviewPolicy) -> Dict[str, int]:
    document, binary = _glb_document(payload)
    nodes, meshes, accessors, views, buffers = (document.get(key) for key in ("nodes", "meshes", "accessors", "bufferViews", "buffers"))
    if not all(isinstance(value, list) for value in (nodes, meshes, accessors, views, buffers)) or len(buffers) != 1 or buffers[0].get("byteLength") != len(binary):
        raise McadSelectorPreviewError("Selector-preview GLB buffer structure is invalid.")
    for view in views:
        if not isinstance(view, Mapping):
            raise McadSelectorPreviewError("Selector-preview GLB buffer view is invalid.")
        offset, length = view.get("byteOffset", 0), view.get("byteLength")
        if isinstance(offset, bool) or isinstance(length, bool) or not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or length <= 0 or offset + length > len(binary):
            raise McadSelectorPreviewError("Selector-preview GLB buffer view exceeds its binary chunk.")
    expected = {item["topology_id"]: item for item in entities if item.get("kind") in {"face", "edge", "axis"}}
    if not expected or len(expected) > policy.max_selectors or len(nodes) != len(expected) or len(meshes) != len(expected):
        raise McadSelectorPreviewError("Selector-preview GLB selector count is invalid.")
    seen = set()
    counts = {"face_count": 0, "edge_count": 0, "axis_count": 0, "face_vertex_count": 0, "face_triangle_count": 0, "line_vertex_count": 0}
    for node in nodes:
        if not isinstance(node, Mapping) or set(node.get("extras", {})) != {"contract", "topology_id", "topology_kind", "native_persistent_id"}:
            raise McadSelectorPreviewError("Selector-preview GLB node metadata is invalid.")
        extras = node["extras"]
        topology_id = extras.get("topology_id")
        entity = expected.get(topology_id)
        if extras.get("contract") != "spike/package-shape-selector-node/v1" or entity is None or topology_id in seen or extras.get("topology_kind") != entity.get("kind") or extras.get("native_persistent_id") != entity.get("native_persistent_id"):
            raise McadSelectorPreviewError("Selector-preview GLB node does not resolve to the canonical inventory.")
        mesh_index = node.get("mesh")
        if isinstance(mesh_index, bool) or not isinstance(mesh_index, int) or not 0 <= mesh_index < len(meshes):
            raise McadSelectorPreviewError("Selector-preview GLB node mesh is invalid.")
        primitives = meshes[mesh_index].get("primitives") if isinstance(meshes[mesh_index], Mapping) else None
        if not isinstance(primitives, list) or len(primitives) != 1 or not isinstance(primitives[0], Mapping):
            raise McadSelectorPreviewError("Selector-preview GLB mesh must contain one primitive.")
        primitive = primitives[0]
        kind = entity["kind"]
        expected_mode = 4 if kind == "face" else 3 if kind == "edge" else 1
        position_index = primitive.get("attributes", {}).get("POSITION") if isinstance(primitive.get("attributes"), Mapping) else None
        if primitive.get("mode") != expected_mode or isinstance(position_index, bool) or not isinstance(position_index, int) or not 0 <= position_index < len(accessors):
            raise McadSelectorPreviewError("Selector-preview GLB primitive kind or position accessor is invalid.")
        position = accessors[position_index]
        if not isinstance(position, Mapping) or position.get("componentType") != 5126 or position.get("type") != "VEC3" or not isinstance(position.get("count"), int) or position["count"] < 2:
            raise McadSelectorPreviewError("Selector-preview GLB position accessor is invalid.")
        counts[f"{kind}_count"] += 1
        if kind == "face":
            index = primitive.get("indices")
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(accessors):
                raise McadSelectorPreviewError("Selector-preview face is missing triangle indices.")
            index_accessor = accessors[index]
            if not isinstance(index_accessor, Mapping) or index_accessor.get("componentType") != 5125 or index_accessor.get("type") != "SCALAR" or not isinstance(index_accessor.get("count"), int) or index_accessor["count"] <= 0 or index_accessor["count"] % 3:
                raise McadSelectorPreviewError("Selector-preview face triangle accessor is invalid.")
            counts["face_vertex_count"] += position["count"]
            counts["face_triangle_count"] += index_accessor["count"] // 3
        else:
            if "indices" in primitive:
                raise McadSelectorPreviewError("Selector-preview line primitives must be non-indexed.")
            counts["line_vertex_count"] += position["count"]
        seen.add(topology_id)
    if seen != set(expected) or counts["face_vertex_count"] > policy.max_face_vertices or counts["face_triangle_count"] > policy.max_face_triangles or counts["line_vertex_count"] > policy.max_line_vertices:
        raise McadSelectorPreviewError("Selector-preview GLB inventory or geometry budget is invalid.")
    return counts


def generate_selector_preview(
    topology_artifact: bytes, *, shape_id: str, source_sha256: str,
    entities: Sequence[Mapping[str, Any]], policy: SelectorPreviewPolicy | None = None,
    freecad_executable: str | Path | None = None, cancellation_event: threading.Event | None = None,
) -> SelectorPreviewResult:
    policy = policy or SelectorPreviewPolicy()
    if not isinstance(topology_artifact, bytes) or not topology_artifact or len(topology_artifact) > policy.max_topology_bytes or b"CASCADE Topology V" not in topology_artifact[:4096]:
        raise McadSelectorPreviewError("Selector preview requires one bounded Open CASCADE BREP artifact.")
    if not isinstance(shape_id, str) or not shape_id.strip() or not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(character not in "0123456789abcdef" for character in source_sha256):
        raise McadSelectorPreviewError("Selector preview requires canonical shape and source identities.")
    if not isinstance(entities, Sequence) or isinstance(entities, (str, bytes)) or not entities:
        raise McadSelectorPreviewError("Selector preview requires a canonical selector inventory.")
    preview_count = sum(item.get("kind") in {"face", "edge", "axis"} for item in entities if isinstance(item, Mapping))
    if preview_count <= 0 or preview_count > policy.max_selectors:
        raise McadSelectorPreviewError("Selector-preview inventory is empty or exceeds its configured selector limit.")
    topology_sha256 = hashlib.sha256(topology_artifact).hexdigest()
    inventory_sha256 = selector_inventory_sha256(entities)
    executable = _freecad_path(freecad_executable)
    helper = Path(__file__).with_name("freecad_package_shape_to_selector_preview.py").resolve(strict=True)
    common = Path(__file__).with_name("freecad_step_to_package_shape.py").resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="spike-selector-preview-") as directory:
        root = Path(directory)
        source, inventory_path, output, report_path = root / "source.spkshape", root / "inventory.json", root / "output.spkselect.glb", root / "report.json"
        source.write_bytes(topology_artifact)
        inventory_path.write_text(json.dumps(list(entities), sort_keys=True, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
        (root / "generate.py").write_bytes(helper.read_bytes())
        (root / "shape_common.py").write_bytes(common.read_bytes())
        arguments = [str(source), str(inventory_path), str(output), str(report_path), f"{policy.linear_deflection_mm:.12g}", str(policy.max_selectors), str(policy.max_face_vertices), str(policy.max_face_triangles), str(policy.max_line_vertices), str(policy.max_output_bytes)]
        stdin_payload = (
            "scope={'__name__':'spike_freecad_selector_preview'}\n"
            "exec(compile(open('shape_common.py',encoding='utf-8').read(),'shape_common.py','exec'),scope)\n"
            "exec(compile(open('generate.py',encoding='utf-8').read(),'generate.py','exec'),scope)\n"
            f"scope['generate']({arguments!r})\nraise SystemExit(0)\n"
        ).encode("utf-8")
        try:
            execution = run_adapter_process([str(executable), "--console", "--user-cfg", str(root / "user.cfg"), "--system-cfg", str(root / "system.cfg")], cwd=root, timeout_s=policy.timeout_s, memory_limit_mb=policy.memory_limit_mb, output_limit_bytes=policy.max_output_bytes, stream_limit_bytes=policy.stream_limit_bytes, cancellation_event=cancellation_event, stdin_payload=stdin_payload)
        except (OSError, SparseLizardAdapterError) as exc:
            raise McadSelectorPreviewError(str(exc).replace("SparseLizard adapter", "selector-preview generation")) from exc
        if execution["return_code"] != 0:
            diagnostic = str(execution.get("stderr") or execution.get("stdout") or "FreeCAD selector-preview generation failed.")[-4000:]
            raise McadSelectorPreviewError(f"FreeCAD selector-preview generation failed: {diagnostic}")
        if not output.is_file() or not report_path.is_file() or output.stat().st_size <= 0 or output.stat().st_size > policy.max_output_bytes or report_path.stat().st_size <= 0 or report_path.stat().st_size > policy.max_report_bytes:
            diagnostic = str(execution.get("stderr") or execution.get("stdout") or "No helper diagnostics were returned.")[-4000:]
            raise McadSelectorPreviewError(f"Selector-preview output or report violates its byte budget: {diagnostic}")
        artifact = output.read_bytes()
        counts = _validate_selector_glb(artifact, entities, policy)
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise McadSelectorPreviewError("Selector-preview report is not valid JSON.") from exc
        artifact_sha256 = hashlib.sha256(artifact).hexdigest()
        if not isinstance(report, Mapping) or report.get("contract") != "spike/freecad-package-shape-selector-preview-report/v1" or report.get("topology_artifact_sha256") != topology_sha256 or report.get("artifact_sha256") != artifact_sha256:
            raise McadSelectorPreviewError("Selector-preview report digest identity is invalid.")
        if report.get("visual_only") is not True or report.get("solver_ready") is not False:
            raise McadSelectorPreviewError("Selector-preview report must remain visual-only and not solver-ready.")
        for field in counts:
            if report.get(field) != counts[field]:
                raise McadSelectorPreviewError(f"Selector-preview report {field} does not match the GLB.")
        freecad_version = report.get("freecad_version")
        if not isinstance(freecad_version, str) or not freecad_version.strip() or report.get("linear_deflection_mm") != policy.linear_deflection_mm:
            raise McadSelectorPreviewError("Selector-preview FreeCAD identity or deflection is invalid.")
        artifact_name = f"{shape_id}-{artifact_sha256[:12]}.spkselect.glb"
        return SelectorPreviewResult(source_sha256, topology_sha256, inventory_sha256, artifact_name, artifact_sha256, artifact, freecad_version, policy.linear_deflection_mm, counts["face_count"], counts["edge_count"], counts["axis_count"])
