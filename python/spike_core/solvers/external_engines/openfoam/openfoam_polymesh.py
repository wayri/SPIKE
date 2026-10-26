"""Digest-bound solver-neutral volume mesh to OpenFOAM ``polyMesh``.

Only explicit tetrahedra and standard-ordered convex hexahedra are admitted.
Every exterior face must be assigned exactly once to a named patch; coupled
interfaces require explicit mapped-wall neighbour ownership.  The translator
does not infer a contact, boundary, material, or solver qualification.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence


REQUEST_CONTRACT = "spike/openfoam-polymesh-request/v1"
RESULT_CONTRACT = "spike/openfoam-polymesh-result/v1"
MESH_CONTRACT = "spike/solver-mesh/v1"
MAX_VERTICES = 10_000_000
MAX_CELLS = 20_000_000
MAX_PATCHES = 4096
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class OpenFoamPolyMeshError(ValueError):
    """Raised when a neutral mesh cannot be translated without inference."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _safe_id(value: Any, label: str) -> str:
    result = str(value or "")
    if not _ID.fullmatch(result):
        raise OpenFoamPolyMeshError(f"{label} must use OpenFOAM-safe identifier syntax.")
    return result


def _point(value: Any, label: str, scale: float) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise OpenFoamPolyMeshError(f"{label} must contain XYZ coordinates.")
    try:
        point = tuple(float(item) * scale for item in value)
    except (TypeError, ValueError) as exc:
        raise OpenFoamPolyMeshError(f"{label} coordinates must be numeric.") from exc
    if not all(math.isfinite(item) for item in point):
        raise OpenFoamPolyMeshError(f"{label} coordinates must be finite.")
    return point  # type: ignore[return-value]


def _sub(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _cross(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return (left[1] * right[2] - left[2] * right[1], left[2] * right[0] - left[0] * right[2], left[0] * right[1] - left[1] * right[0])


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _centroid(indices: Iterable[int], points: Sequence[Sequence[float]]) -> tuple[float, float, float]:
    values = list(indices)
    return tuple(sum(points[index][axis] for index in values) / len(values) for axis in range(3))  # type: ignore[return-value]


def _face_normal(face: Sequence[int], points: Sequence[Sequence[float]]) -> tuple[float, float, float]:
    origin = points[face[0]]
    normal = [0.0, 0.0, 0.0]
    for index in range(1, len(face) - 1):
        value = _cross(_sub(points[face[index]], origin), _sub(points[face[index + 1]], origin))
        for axis in range(3):
            normal[axis] += value[axis]
    if _dot(normal, normal) <= 1e-30:
        raise OpenFoamPolyMeshError("Volume mesh contains a degenerate face.")
    return tuple(normal)  # type: ignore[return-value]


def _cell_faces(kind: str, vertices: list[int], points: Sequence[Sequence[float]]) -> list[tuple[int, ...]]:
    templates = {
        "tetrahedron": ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)),
        "hexahedron": ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)),
    }
    expected = 4 if kind == "tetrahedron" else 8 if kind == "hexahedron" else 0
    if not expected or len(vertices) != expected:
        raise OpenFoamPolyMeshError("OpenFOAM field meshes accept only four-node tetrahedra and eight-node hexahedra.")
    if len(vertices) != len(set(vertices)):
        raise OpenFoamPolyMeshError("A volume cell cannot repeat a vertex.")
    cell_center = _centroid(vertices, points)
    faces = []
    for template in templates[kind]:
        face = tuple(vertices[index] for index in template)
        normal = _face_normal(face, points)
        direction = _sub(_centroid(face, points), cell_center)
        if abs(_dot(normal, direction)) <= 1e-24:
            raise OpenFoamPolyMeshError("Volume mesh contains a zero-volume or non-convex cell.")
        if _dot(normal, direction) < 0:
            face = tuple(reversed(face))
        faces.append(face)
    return faces


def _foam_header(class_name: str, object_name: str, location: str = "constant/polyMesh") -> str:
    return f"FoamFile\n{{\n    version 2.0;\n    format ascii;\n    class {class_name};\n    location \"{location}\";\n    object {object_name};\n}}\n"


def compile_polymesh(request: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(request, Mapping) or request.get("contract") != REQUEST_CONTRACT:
        raise OpenFoamPolyMeshError(f"Expected {REQUEST_CONTRACT}.")
    region_id = _safe_id(request.get("region_id"), "region_id")
    mesh = request.get("mesh")
    evidence = request.get("mesh_evidence")
    if not isinstance(mesh, Mapping) or mesh.get("contract") != MESH_CONTRACT:
        raise OpenFoamPolyMeshError(f"mesh must use {MESH_CONTRACT}.")
    if not isinstance(evidence, Mapping) or evidence.get("qualified") is not True or evidence.get("contract") != MESH_CONTRACT:
        raise OpenFoamPolyMeshError("mesh_evidence must qualify the solver mesh contract.")
    digest = hashlib.sha256(_canonical(mesh)).hexdigest()
    if not _SHA256.fullmatch(str(evidence.get("sha256") or "")) or evidence.get("sha256") != digest:
        raise OpenFoamPolyMeshError("mesh evidence digest does not match the canonical solver mesh.")
    units = str(mesh.get("units") or "")
    if units not in {"m", "mm"} or mesh.get("coordinate_system") != "right_handed_xyz":
        raise OpenFoamPolyMeshError("mesh requires explicit m/mm units and right_handed_xyz coordinates.")
    raw_points = mesh.get("vertices")
    raw_cells = mesh.get("cells")
    if not isinstance(raw_points, list) or not 4 <= len(raw_points) <= MAX_VERTICES:
        raise OpenFoamPolyMeshError(f"mesh vertices must contain 4..{MAX_VERTICES} points.")
    if not isinstance(raw_cells, list) or not 1 <= len(raw_cells) <= MAX_CELLS:
        raise OpenFoamPolyMeshError(f"mesh cells must contain 1..{MAX_CELLS} volumes.")
    counts = mesh.get("counts")
    if not isinstance(counts, Mapping) or counts.get("vertices") != len(raw_points) or counts.get("cells") != len(raw_cells):
        raise OpenFoamPolyMeshError("mesh counts do not match its arrays.")
    scale = 0.001 if units == "mm" else 1.0
    points = [_point(value, f"vertices[{index}]", scale) for index, value in enumerate(raw_points)]
    if len(points) != len(set(points)):
        raise OpenFoamPolyMeshError("mesh contains duplicate vertex coordinates.")

    face_records: Dict[tuple[int, ...], Dict[str, Any]] = {}
    cell_ids: set[str] = set()
    for owner, raw in enumerate(raw_cells):
        if not isinstance(raw, Mapping):
            raise OpenFoamPolyMeshError("mesh cells must be objects.")
        cell_id = str(raw.get("id") or "")
        if not cell_id or cell_id in cell_ids:
            raise OpenFoamPolyMeshError("mesh cell IDs must be non-empty and unique.")
        cell_ids.add(cell_id)
        indices = raw.get("vertices")
        if not isinstance(indices, list) or any(not isinstance(item, int) or isinstance(item, bool) or not 0 <= item < len(points) for item in indices):
            raise OpenFoamPolyMeshError(f"cell {cell_id} has invalid vertex indices.")
        for face in _cell_faces(str(raw.get("kind") or ""), list(indices), points):
            key = tuple(sorted(face))
            existing = face_records.get(key)
            if existing is None:
                face_records[key] = {"face": face, "owner": owner, "neighbour": None}
            elif existing["neighbour"] is None:
                existing["neighbour"] = owner
            else:
                raise OpenFoamPolyMeshError("mesh contains a non-manifold face shared by more than two cells.")

    # OpenFOAM requires the internal owner/neighbour addressing in upper-
    # triangular order. Cells are visited monotonically, so owner < neighbour;
    # sort explicitly to make that invariant deterministic in the face list.
    interior = sorted(
        (record for record in face_records.values() if record["neighbour"] is not None),
        key=lambda item: (int(item["owner"]), int(item["neighbour"])),
    )
    exterior = {key: record for key, record in face_records.items() if record["neighbour"] is None}
    raw_patches = request.get("boundary_patches")
    if not isinstance(raw_patches, list) or not 1 <= len(raw_patches) <= MAX_PATCHES:
        raise OpenFoamPolyMeshError(f"boundary_patches must contain 1..{MAX_PATCHES} records.")
    assigned: set[tuple[int, ...]] = set()
    patches = []
    for raw_patch in raw_patches:
        if not isinstance(raw_patch, Mapping):
            raise OpenFoamPolyMeshError("boundary patches must be objects.")
        name = _safe_id(raw_patch.get("name"), "boundary patch name")
        patch_type = str(raw_patch.get("type") or "")
        if patch_type not in {"wall", "patch", "symmetryPlane", "empty", "mappedWall"}:
            raise OpenFoamPolyMeshError(f"boundary patch {name} has unsupported type.")
        raw_faces = raw_patch.get("faces")
        if not isinstance(raw_faces, list) or not raw_faces:
            raise OpenFoamPolyMeshError(f"boundary patch {name} requires explicit faces.")
        records = []
        for face in raw_faces:
            if not isinstance(face, list) or len(face) not in {3, 4} or any(not isinstance(item, int) or isinstance(item, bool) for item in face):
                raise OpenFoamPolyMeshError(f"boundary patch {name} has an invalid face.")
            key = tuple(sorted(face))
            if key not in exterior:
                raise OpenFoamPolyMeshError(f"boundary patch {name} references a face that is not an exterior volume face.")
            if key in assigned:
                raise OpenFoamPolyMeshError("an exterior face cannot belong to more than one boundary patch.")
            assigned.add(key)
            records.append(exterior[key])
        patch: Dict[str, Any] = {"name": name, "type": patch_type, "records": records}
        raw_groups = raw_patch.get("groups", [])
        if not isinstance(raw_groups, list) or len(raw_groups) > 16:
            raise OpenFoamPolyMeshError(f"boundary patch {name} groups must contain at most 16 identifiers.")
        groups = [_safe_id(value, f"boundary patch {name} group") for value in raw_groups]
        if len(groups) != len(set(groups)):
            raise OpenFoamPolyMeshError(f"boundary patch {name} groups must be unique.")
        if groups:
            patch["groups"] = groups
        if patch_type == "mappedWall":
            patch["neighbour_region"] = _safe_id(raw_patch.get("neighbour_region"), f"boundary patch {name} neighbour_region")
            patch["neighbour_patch"] = _safe_id(raw_patch.get("neighbour_patch"), f"boundary patch {name} neighbour_patch")
            patch["interface_id"] = _safe_id(raw_patch.get("interface_id"), f"boundary patch {name} interface_id")
        patches.append(patch)
    if assigned != set(exterior):
        raise OpenFoamPolyMeshError("every exterior volume face must be assigned exactly once to a boundary patch.")
    names = [item["name"] for item in patches]
    if len(names) != len(set(names)):
        raise OpenFoamPolyMeshError("boundary patch names must be unique.")

    raw_zones = request.get("cell_zones", [])
    if not isinstance(raw_zones, list) or len(raw_zones) > MAX_PATCHES:
        raise OpenFoamPolyMeshError(f"cell_zones must contain at most {MAX_PATCHES} records.")
    zones = []
    for raw_zone in raw_zones:
        if not isinstance(raw_zone, Mapping):
            raise OpenFoamPolyMeshError("cell zones must be objects.")
        name = _safe_id(raw_zone.get("name"), "cell zone name")
        raw_ids = raw_zone.get("cell_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise OpenFoamPolyMeshError(f"cell zone {name} requires explicit cell_ids.")
        if len(raw_ids) != len(set(str(item) for item in raw_ids)):
            raise OpenFoamPolyMeshError(f"cell zone {name} cannot repeat a cell ID.")
        missing = [str(item) for item in raw_ids if str(item) not in cell_ids]
        if missing:
            raise OpenFoamPolyMeshError(f"cell zone {name} references an unknown cell ID.")
        labels = [index for index, raw_cell in enumerate(raw_cells) if str(raw_cell.get("id")) in {str(item) for item in raw_ids}]
        zones.append({"name": name, "cell_labels": labels})
    zone_names = [item["name"] for item in zones]
    if len(zone_names) != len(set(zone_names)):
        raise OpenFoamPolyMeshError("cell zone names must be unique.")

    ordered_faces = list(interior)
    patch_summaries = []
    start = len(interior)
    for patch in patches:
        patch_summaries.append({key: value for key, value in patch.items() if key != "records"} | {"start_face": start, "face_count": len(patch["records"])})
        ordered_faces.extend(patch["records"])
        start += len(patch["records"])
    point_lines = "\n".join(f"({x:.17g} {y:.17g} {z:.17g})" for x, y, z in points)
    face_lines = "\n".join(f"{len(item['face'])}({' '.join(str(index) for index in item['face'])})" for item in ordered_faces)
    owner_lines = "\n".join(str(item["owner"]) for item in ordered_faces)
    neighbour_lines = "\n".join(str(item["neighbour"]) for item in interior)
    boundary_blocks = []
    for patch in patch_summaries:
        extra = ""
        if patch.get("groups"):
            extra += f"    inGroups {len(patch['groups'])}({' '.join(patch['groups'])});\n"
        if patch["type"] == "mappedWall":
            extra += f"    sampleMode nearestPatchFace;\n    sampleRegion {patch['neighbour_region']};\n    samplePatch {patch['neighbour_patch']};\n"
        boundary_blocks.append(f"{patch['name']}\n{{\n    type {patch['type']};\n{extra}    nFaces {patch['face_count']};\n    startFace {patch['start_face']};\n}}")
    boundary_text = "\n".join(boundary_blocks)
    files = {
        "points": _foam_header("vectorField", "points") + f"{len(points)}\n(\n{point_lines}\n)\n",
        "faces": _foam_header("faceList", "faces") + f"{len(ordered_faces)}\n(\n{face_lines}\n)\n",
        "owner": _foam_header("labelList", "owner") + f"{len(ordered_faces)}\n(\n{owner_lines}\n)\n",
        "neighbour": _foam_header("labelList", "neighbour") + f"{len(interior)}\n(\n{neighbour_lines}\n)\n",
        "boundary": _foam_header("polyBoundaryMesh", "boundary") + f"{len(patches)}\n(\n{boundary_text}\n)\n",
    }
    if zones:
        zone_blocks = []
        for zone in zones:
            labels = "\n".join(str(item) for item in zone["cell_labels"])
            zone_blocks.append(
                f"{zone['name']}\n{{\n    type cellZone;\n    cellLabels List<label>\n"
                f"    {len(zone['cell_labels'])}\n    (\n{labels}\n    );\n}}"
            )
        joined_zone_blocks = "\n".join(zone_blocks)
        files["cellZones"] = _foam_header("regIOobject", "cellZones") + f"{len(zones)}\n(\n{joined_zone_blocks}\n)\n"
    return {
        "contract": RESULT_CONTRACT, "region_id": region_id, "status": "compiled",
        "mesh_digest": digest, "counts": {"points": len(points), "cells": len(raw_cells), "faces": len(ordered_faces), "internal_faces": len(interior), "boundary_faces": len(exterior)},
        "patches": patch_summaries, "cell_zones": [{"name": item["name"], "cell_count": len(item["cell_labels"])} for item in zones], "files": files,
    }


def write_polymesh(request: Mapping[str, Any], output_dir: str | Path) -> Dict[str, Any]:
    compiled = compile_polymesh(request)
    root = Path(output_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise OpenFoamPolyMeshError("polyMesh output directory must be empty.")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise OpenFoamPolyMeshError("polyMesh output directory must not be a symbolic link.")
    digests = {}
    for name, content in compiled["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise OpenFoamPolyMeshError("polyMesh output escaped its directory.")
        path.write_text(content, encoding="utf-8", newline="\n")
        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    tree_digest = hashlib.sha256(_canonical(digests)).hexdigest()
    return {key: value for key, value in compiled.items() if key != "files"} | {
        "status": "materialized", "poly_mesh_dir": str(root), "file_digests": digests,
        "poly_mesh_digest": tree_digest,
        "poly_mesh_evidence": {"id": f"openfoam-polymesh:{compiled['region_id']}", "sha256": tree_digest, "contract": "spike/openfoam-polymesh/v1", "qualified": True},
    }


__all__ = ["MESH_CONTRACT", "OpenFoamPolyMeshError", "REQUEST_CONTRACT", "RESULT_CONTRACT", "compile_polymesh", "write_polymesh"]
