"""FreeCAD-hosted STEP tessellation helper for SPIKE.

This file is executed by ``FreeCADCmd``.  It has no package or solver side
effects: one local STEP file is tessellated and written as one self-contained
GLB plus a small JSON report.
"""

from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

import FreeCAD as App  # type: ignore[import-not-found]
import Import  # type: ignore[import-not-found]


def _aligned(payload: bytes, padding: bytes = b"\x00") -> bytes:
    return payload + padding * ((-len(payload)) % 4)


def _write_glb(path: Path, positions: list[float], indices: list[int]) -> None:
    position_bytes = struct.pack(f"<{len(positions)}f", *positions)
    position_bytes = _aligned(position_bytes)
    index_offset = len(position_bytes)
    index_bytes = struct.pack(f"<{len(indices)}I", *indices)
    binary = _aligned(position_bytes + index_bytes)
    xs, ys, zs = positions[0::3], positions[1::3], positions[2::3]
    document = {
        "asset": {"version": "2.0", "generator": "SPIKE bounded FreeCAD STEP tessellator"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "STEP visual mesh"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": len(index_bytes), "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0, "componentType": 5126, "count": len(positions) // 3,
                "type": "VEC3", "min": [min(xs), min(ys), min(zs)],
                "max": [max(xs), max(ys), max(zs)],
            },
            {"bufferView": 1, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
        ],
    }
    json_chunk = _aligned(json.dumps(document, separators=(",", ":"), allow_nan=False).encode("utf-8"), b" ")
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary)
    payload = b"".join((
        struct.pack("<4sII", b"glTF", 2, total_length),
        struct.pack("<II", len(json_chunk), 0x4E4F534A), json_chunk,
        struct.pack("<II", len(binary), 0x004E4942), binary,
    ))
    path.write_bytes(payload)


def convert(arguments: list[str]) -> None:
    if len(arguments) != 7:
        raise RuntimeError("Expected input, output, report, deflection, max vertices, max triangles, and max output bytes.")
    source, output, report = map(Path, arguments[:3])
    deflection = float(arguments[3])
    max_vertices, max_triangles, max_output_bytes = map(int, arguments[4:])
    if not source.is_file() or source.suffix.lower() not in {".step", ".stp"}:
        raise RuntimeError("The converter input must be one local STEP/STP file.")
    if not math.isfinite(deflection) or not 0.001 <= deflection <= 10.0:
        raise RuntimeError("Linear deflection must be within 0.001 through 10 mm.")
    document = App.newDocument("SPIKE_STEP_TESSELLATION")
    try:
        Import.insert(str(source), document.Name)
        document.recompute()
        positions: list[float] = []
        indices: list[int] = []
        shape_count = 0
        for obj in document.Objects:
            shape = getattr(obj, "Shape", None)
            if shape is None or shape.isNull():
                continue
            vertices, triangles = shape.tessellate(deflection)
            if not triangles:
                continue
            base = len(positions) // 3
            for vertex in vertices:
                # Imported Feature.Shape already carries obj.Placement. Applying
                # the feature placement again would double-transform vertices.
                # glTF coordinates are metres; the canonical STEP/AssemblyIR
                # geometry is millimetres and the viewport converts back once.
                coordinates = (
                    float(vertex.x) / 1000.0,
                    float(vertex.y) / 1000.0,
                    float(vertex.z) / 1000.0,
                )
                if not all(math.isfinite(value) for value in coordinates):
                    raise RuntimeError("FreeCAD produced a non-finite mesh vertex.")
                positions.extend(coordinates)
            for triangle in triangles:
                if len(triangle) != 3:
                    raise RuntimeError("FreeCAD produced a non-triangular mesh face.")
                indices.extend(base + int(index) for index in triangle)
            shape_count += 1
            if len(positions) // 3 > max_vertices or len(indices) // 3 > max_triangles:
                raise RuntimeError("STEP tessellation exceeds the configured mesh budget.")
        if not positions or not indices:
            raise RuntimeError("STEP import produced no tessellatable solid or shell geometry.")
        _write_glb(output, positions, indices)
        if output.stat().st_size > max_output_bytes:
            output.unlink(missing_ok=True)
            raise RuntimeError("Tessellated GLB exceeds the configured output budget.")
        report.write_text(json.dumps({
            "contract": "spike/freecad-step-tessellation-report/v1",
            "freecad_version": ".".join(str(value) for value in App.Version()[:3]),
            "shape_count": shape_count,
            "vertex_count": len(positions) // 3,
            "triangle_count": len(indices) // 3,
            "linear_deflection_mm": deflection,
            "visual_only": True,
            "solver_ready": False,
        }, sort_keys=True), encoding="utf-8")
    finally:
        App.closeDocument(document.Name)


if __name__ == "__main__":
    convert(sys.argv[1:])
