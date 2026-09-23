"""FreeCAD-hosted exact-BREP selector preview generator for SPIKE."""

from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

import FreeCAD as App  # type: ignore[import-not-found]
import Part  # type: ignore[import-not-found]

# The bounded adapter loads the reviewed exact-shape helper into this execution
# scope first, providing _axis_descriptor/_brep_bytes/_kind_name/_safe_attr/_sha256.


def _aligned(payload: bytes, padding: bytes = b"\x00") -> bytes:
    return payload + padding * ((-len(payload)) % 4)


def _reconstruct(shape, max_subshape_bytes: int):
    axes = {}
    raw = []
    surface_mapping = (("plane", "plane"), ("cylinder", "cylinder"), ("cone", "cone"), ("sphere", "sphere"), ("torus", "torus"), ("bspline", "nurbs"), ("bezier", "nurbs"))
    curve_mapping = (("line", "line"), ("circle", "circle"), ("ellipse", "ellipse"), ("bspline", "bspline"), ("bezier", "bspline"))
    for kind, subshapes in (("solid", shape.Solids), ("shell", shape.Shells), ("face", shape.Faces), ("edge", shape.Edges), ("vertex", shape.Vertexes)):
        for subshape in subshapes:
            fingerprint = _sha256(_brep_bytes(subshape, max_subshape_bytes))
            support = {"surface_kind": None, "curve_kind": None, "axis_key": None}
            geometry = None
            if kind == "face":
                geometry = _safe_attr(subshape, "Surface")
                if geometry is not None:
                    support["surface_kind"] = _kind_name(geometry, surface_mapping)
            elif kind == "edge":
                geometry = _safe_attr(subshape, "Curve")
                if geometry is not None:
                    support["curve_kind"] = _kind_name(geometry, curve_mapping)
            descriptor = _axis_descriptor(geometry) if geometry is not None else None
            if descriptor is not None:
                axis_key = _sha256(json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("ascii"))
                axes[axis_key] = descriptor
                support["axis_key"] = axis_key
            raw.append({"kind": kind, "fingerprint": fingerprint, "support": support, "subshape": subshape})
    records = []
    lookup = {}
    for axis_key in sorted(axes):
        native_id = f"axis:{axis_key}"
        record = {"native_persistent_id": native_id, "kind": "axis", "fingerprint_sha256": axis_key, "support": {"surface_kind": None, "curve_kind": None, "axis_native_persistent_id": None}}
        records.append(record)
        lookup[("axis", native_id)] = axes[axis_key]
    occurrences = {}
    for item in sorted(raw, key=lambda value: (value["kind"], value["fingerprint"], json.dumps(value["support"], sort_keys=True))):
        key = (item["kind"], item["fingerprint"])
        rank = occurrences.get(key, 0)
        occurrences[key] = rank + 1
        native_id = f"{item['kind']}:{item['fingerprint']}:{rank}"
        record = {
            "native_persistent_id": native_id, "kind": item["kind"], "fingerprint_sha256": item["fingerprint"],
            "support": {"surface_kind": item["support"]["surface_kind"], "curve_kind": item["support"]["curve_kind"], "axis_native_persistent_id": f"axis:{item['support']['axis_key']}" if item["support"]["axis_key"] else None},
        }
        records.append(record)
        lookup[(item["kind"], native_id)] = item["subshape"]
    return records, lookup


def _write_glb(path: Path, selectors: list[dict], max_output_bytes: int) -> tuple[int, int, int]:
    binary = bytearray()
    views = []
    accessors = []
    meshes = []
    nodes = []
    face_vertices = face_triangles = line_vertices = 0

    def add_data(values, fmt, component_type, value_type, target, dimensions):
        nonlocal binary
        raw = struct.pack(f"<{len(values)}{fmt}", *values)
        offset = len(binary)
        binary.extend(raw)
        binary.extend(b"\x00" * ((-len(binary)) % 4))
        view = len(views)
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw), "target": target})
        count = len(values) // dimensions
        accessor = {"bufferView": view, "componentType": component_type, "count": count, "type": value_type}
        if value_type == "VEC3":
            axes = [values[index::3] for index in range(3)]
            accessor["min"] = [min(axis) for axis in axes]
            accessor["max"] = [max(axis) for axis in axes]
        accessors.append(accessor)
        return len(accessors) - 1

    for selector in selectors:
        positions = selector["positions"]
        position_accessor = add_data(positions, "f", 5126, "VEC3", 34962, 3)
        primitive = {"attributes": {"POSITION": position_accessor}, "mode": selector["mode"]}
        if selector["indices"]:
            primitive["indices"] = add_data(selector["indices"], "I", 5125, "SCALAR", 34963, 1)
        mesh_index = len(meshes)
        meshes.append({"primitives": [primitive]})
        nodes.append({
            "mesh": mesh_index,
            "name": f"{selector['kind']}:{selector['native_id']}",
            "extras": {
                "contract": "spike/package-shape-selector-node/v1",
                "topology_id": selector["topology_id"], "topology_kind": selector["kind"],
                "native_persistent_id": selector["native_id"],
            },
        })
        if selector["kind"] == "face":
            face_vertices += len(positions) // 3
            face_triangles += len(selector["indices"]) // 3
        else:
            line_vertices += len(positions) // 3
    document = {
        "asset": {"version": "2.0", "generator": "SPIKE exact-BREP selector preview"},
        "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
        "buffers": [{"byteLength": len(binary)}], "bufferViews": views, "accessors": accessors,
    }
    json_chunk = _aligned(json.dumps(document, separators=(",", ":"), allow_nan=False).encode("utf-8"), b" ")
    binary_chunk = _aligned(bytes(binary))
    total = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    if total > max_output_bytes:
        raise RuntimeError("Selector-preview GLB exceeds its configured output budget.")
    path.write_bytes(b"".join((
        struct.pack("<4sII", b"glTF", 2, total),
        struct.pack("<II", len(json_chunk), 0x4E4F534A), json_chunk,
        struct.pack("<II", len(binary_chunk), 0x004E4942), binary_chunk,
    )))
    return face_vertices, face_triangles, line_vertices


def generate(arguments: list[str]) -> None:
    if len(arguments) != 10:
        raise RuntimeError("Expected BREP, inventory, output, report, deflection, and five resource limits.")
    source, inventory_path, output, report = map(Path, arguments[:4])
    deflection = float(arguments[4])
    max_selectors, max_face_vertices, max_face_triangles, max_line_vertices, max_output_bytes = map(int, arguments[5:])
    if not source.is_file() or source.suffix.lower() != ".spkshape" or not inventory_path.is_file():
        raise RuntimeError("Selector preview requires one local .spkshape and inventory file.")
    if not math.isfinite(deflection) or not 0.001 <= deflection <= 10.0:
        raise RuntimeError("Selector-preview deflection must be within 0.001 through 10 mm.")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(inventory, list) or not inventory:
        raise RuntimeError("Selector-preview inventory must be a non-empty array.")
    shape = Part.Shape()
    shape.importBrep(str(source))
    if shape.isNull():
        raise RuntimeError("Selector-preview BREP is empty.")
    reconstructed, lookup = _reconstruct(shape, max_output_bytes)
    expected_native = [{
        "native_persistent_id": item["native_persistent_id"], "kind": item["kind"],
        "fingerprint_sha256": item["fingerprint_sha256"],
        "support": {
            "surface_kind": item["support"]["surface_kind"], "curve_kind": item["support"]["curve_kind"],
            "axis_native_persistent_id": next((candidate["native_persistent_id"] for candidate in inventory if candidate["topology_id"] == item["support"]["axis_topology_id"]), None) if item["support"]["axis_topology_id"] else None,
        },
    } for item in inventory]
    preview_kinds = {"face", "edge", "axis"}
    reconstructed_preview = [item for item in reconstructed if item["kind"] in preview_kinds]
    expected_preview = [item for item in expected_native if item["kind"] in preview_kinds]
    if reconstructed_preview != expected_preview:
        mismatch = next((index for index, pair in enumerate(zip(reconstructed_preview, expected_preview)) if pair[0] != pair[1]), min(len(reconstructed_preview), len(expected_preview)))
        actual = reconstructed_preview[mismatch] if mismatch < len(reconstructed_preview) else None
        expected = expected_preview[mismatch] if mismatch < len(expected_preview) else None
        raise RuntimeError(f"Exact BREP does not reproduce the canonical previewable selector inventory at {mismatch}; counts {len(reconstructed_preview)}/{len(expected_preview)}; actual={actual!r}; expected={expected!r}.")
    previewable = [item for item in inventory if item["kind"] in {"face", "edge", "axis"}]
    if not previewable or len(previewable) > max_selectors:
        raise RuntimeError("Selector-preview inventory is empty or exceeds its configured selector limit.")
    diagonal = float(shape.BoundBox.DiagonalLength)
    axis_half_length = max(5.0, diagonal * 0.25)
    selectors = []
    for item in previewable:
        native_id, kind = item["native_persistent_id"], item["kind"]
        geometry = lookup.get((kind, native_id))
        if geometry is None:
            raise RuntimeError("Selector-preview geometry lookup is incomplete.")
        positions = []
        indices = []
        if kind == "face":
            vertices, triangles = geometry.tessellate(deflection)
            for vertex in vertices:
                positions.extend((float(vertex.x) / 1000.0, float(vertex.y) / 1000.0, float(vertex.z) / 1000.0))
            for triangle in triangles:
                indices.extend(int(index) for index in triangle)
            mode = 4
        elif kind == "edge":
            points = geometry.discretize(Deflection=deflection)
            for point in points:
                positions.extend((float(point.x) / 1000.0, float(point.y) / 1000.0, float(point.z) / 1000.0))
            mode = 3
        else:
            origin, direction = geometry["origin_mm"], geometry["direction"]
            for sign in (-1.0, 1.0):
                positions.extend((origin[0] + sign * axis_half_length * direction[0], origin[1] + sign * axis_half_length * direction[1], origin[2] + sign * axis_half_length * direction[2]))
            positions = [value / 1000.0 for value in positions]
            mode = 1
        if len(positions) < 6 or (kind == "face" and not indices) or not all(math.isfinite(value) for value in positions):
            raise RuntimeError("Selector-preview geometry is empty or non-finite.")
        selectors.append({"topology_id": item["topology_id"], "kind": kind, "native_id": native_id, "positions": positions, "indices": indices, "mode": mode})
    face_vertices, face_triangles, line_vertices = _write_glb(output, selectors, max_output_bytes)
    if face_vertices > max_face_vertices or face_triangles > max_face_triangles or line_vertices > max_line_vertices:
        output.unlink(missing_ok=True)
        raise RuntimeError("Selector-preview geometry exceeds its configured vertex or triangle budget.")
    counts = {kind: sum(item["kind"] == kind for item in previewable) for kind in ("face", "edge", "axis")}
    report.write_text(json.dumps({
        "contract": "spike/freecad-package-shape-selector-preview-report/v1",
        "topology_artifact_sha256": _sha256(source.read_bytes()),
        "artifact_sha256": _sha256(output.read_bytes()),
        "freecad_version": ".".join(str(value) for value in App.Version()[:3]),
        "linear_deflection_mm": deflection,
        "face_count": counts["face"], "edge_count": counts["edge"], "axis_count": counts["axis"],
        "face_vertex_count": face_vertices, "face_triangle_count": face_triangles, "line_vertex_count": line_vertices,
        "visual_only": True, "solver_ready": False,
    }, sort_keys=True, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    generate(sys.argv[1:])
