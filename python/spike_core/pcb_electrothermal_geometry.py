# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Admit an already generated PCB tetra mesh as one retained assembly body.

This module does not compile PCB source geometry or generate a mesh.  It adds
the occurrence, stack and physical-material bindings required by the retained
assembly field handoff, and derives the complete exterior triangle inventory
from admitted tetrahedron connectivity.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any, Mapping

from .assembly_field_geometry import MAX_CELLS, MAX_VERTICES
from .assembly_field_handoff import bounded_json
from .multiboard_identity import canonical_json_digest
from .tetra_mesh_refinement import _validate

REQUEST_CONTRACT = "spike/pcb-electrothermal-geometry-request/v1"
RESULT_CONTRACT = "spike/pcb-electrothermal-geometry/v1"
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("PCB_ELECTROTHERMAL_GEOMETRY: " + message)


def _keys(value: Any, expected: set[str], label: str) -> None:
    _require(isinstance(value, dict) and set(value) == expected,
             f"{label} has unexpected or missing fields")


def _text(value: Any, label: str) -> str:
    _require(isinstance(value, str) and value.strip() and len(value) <= 256,
             f"{label} must be a bounded nonempty identity")
    return value


def _digest(value: Any, label: str) -> str:
    _require(isinstance(value, str) and _DIGEST.fullmatch(value) is not None,
             f"{label} must be a lowercase SHA-256 digest")
    return value


def _oriented_faces(vertices: list[int]) -> tuple[list[int], ...]:
    a, b, c, d = vertices
    return ([b, c, d], [a, d, c], [a, b, d], [a, c, b])


def _ownership(cell: Mapping[str, Any], objects: Mapping[str, Mapping[str, str]],
               material_map: Mapping[str, str], occurrence_id: str) -> dict[str, Any]:
    sources = list(cell["source_object_ids"])
    metadata = [objects[source] for source in sources]
    return {
        "occurrence_id": occurrence_id,
        "cell_id": cell["id"],
        "material_id": cell["material_id"],
        "physical_material_id": material_map[cell["material_id"]],
        "source_object_ids": sources,
        "net_ids": sorted({item["net"] for item in metadata if item.get("net")}),
        "layer_ids": sorted({item["layer"] for item in metadata if item.get("layer")}),
    }


def prepare_pcb_electrothermal_geometry(request: dict[str, Any]) -> dict[str, Any]:
    """Return one strict body accepted by ``prepare_assembly_field_handoff``.

    ``mesh`` must already be a complete ``spike/solver-mesh/v1`` tetra mesh.
    The helper preserves every vertex, cell and object metadata record.  It
    neither infers electrical conductivity nor creates connector/contact paths.
    """

    _keys(request, {
        "contract", "occurrence_id", "reference_id", "source_sha256",
        "stack_binding", "material_map", "mesh",
    }, "request")
    _require(request["contract"] == REQUEST_CONTRACT, "unsupported request contract")
    occurrence_id = _text(request["occurrence_id"], "occurrence_id")
    reference_id = _text(request["reference_id"], "reference_id")
    source_sha256 = _digest(request["source_sha256"], "source_sha256")
    stack = request["stack_binding"]
    _keys(stack, {"id", "source_sha256"}, "stack_binding")
    stack_binding = {"id": _text(stack["id"], "stack_binding.id"),
                     "source_sha256": _digest(stack["source_sha256"], "stack_binding.source_sha256")}

    mesh = request["mesh"]
    _keys(mesh, {"contract", "units", "coordinate_system", "vertices", "cells", "counts", "object_map"},
          "mesh")
    vertices, cells, objects = mesh["vertices"], mesh["cells"], mesh["object_map"]
    _require(mesh["contract"] == "spike/solver-mesh/v1" and mesh["units"] in {"m", "mm"} and
             mesh["coordinate_system"] == "right_handed_xyz", "invalid mesh identity or units")
    _require(isinstance(vertices, list) and 4 <= len(vertices) <= MAX_VERTICES and
             isinstance(cells, list) and 1 <= len(cells) <= MAX_CELLS,
             "mesh vertex or cell budget exceeded")
    for point in vertices:
        _require(isinstance(point, list) and len(point) == 3 and
                 all(type(value) in (int, float) and math.isfinite(value) for value in point),
                 "vertex coordinates must be finite numeric xyz arrays")
    _keys(mesh["counts"], {"vertices", "cells"}, "mesh counts")
    _require(all(type(value) is int for value in mesh["counts"].values()) and
             mesh["counts"] == {"vertices": len(vertices), "cells": len(cells)},
             "mesh counts do not match payload")
    _require(isinstance(objects, dict) and len(objects) <= MAX_CELLS,
             "object_map exceeds its budget")
    material_map = request["material_map"]
    _require(isinstance(material_map, dict) and 1 <= len(material_map) <= 1024,
             "material_map must be a bounded nonempty object")
    # Reject top-level resource excess before serializing, then apply the same
    # finite 8 MiB control-plane bound as the downstream assembly handoff.
    try:
        bounded_json(request)
    except ValueError as exc:
        raise ValueError("PCB_ELECTROTHERMAL_GEOMETRY: finite bounded JSON request required") from exc
    for source_id, metadata in objects.items():
        _text(source_id, "source object id")
        _require(isinstance(metadata, dict) and "kind" in metadata and
                 set(metadata) <= {"kind", "net", "layer"},
                 "source object metadata must retain only kind, net and layer")
        for name, value in metadata.items():
            _text(value, f"source object {name}")
    _require(all(isinstance(local, str) and local and isinstance(physical, str) and physical
                 and len(local) <= 256 and len(physical) <= 256
                 for local, physical in material_map.items()),
             "material_map identities must be bounded nonempty strings")
    cell_ids: set[str] = set()
    local_materials: set[str] = set()
    used_sources: set[str] = set()
    for cell in cells:
        _keys(cell, {"id", "kind", "vertices", "material_id", "source_object_ids"}, "mesh cell")
        cell_id = _text(cell["id"], "cell id")
        _require(cell_id not in cell_ids, "duplicate cell id")
        cell_ids.add(cell_id)
        _require(cell["kind"] == "tetrahedron", "only tetrahedron cells can be bridged")
        indices = cell["vertices"]
        _require(isinstance(indices, list) and len(indices) == 4 and
                 all(type(index) is int and 0 <= index < len(vertices) for index in indices) and
                 len(set(indices)) == 4, "cell vertices must be four distinct in-range integer indices")
        material_id = _text(cell["material_id"], "local material id")
        local_materials.add(material_id)
        sources = cell["source_object_ids"]
        _require(isinstance(sources, list) and 1 <= len(sources) <= 1024 and
                 all(isinstance(source, str) and source in objects for source in sources) and
                 len(set(sources)) == len(sources),
                 "cell source ownership must reference unique declared source ids")
        used_sources.update(sources)
    _require(set(material_map) == local_materials,
             "material_map must exactly cover all local cell materials")
    _require(used_sources == set(objects),
             "every declared source object must own at least one retained cell")

    face_owners: dict[tuple[int, int, int], list[tuple[dict[str, Any], list[int]]]] = {}
    for cell in cells:
        for oriented in _oriented_faces(cell["vertices"]):
            key = tuple(sorted(oriented))
            owners = face_owners.setdefault(key, [])
            _require(len(owners) < 2, "non-manifold face has more than two owning cells")
            owners.append((cell, oriented))

    boundary_faces = []
    face_ownership = []
    cell_ownership = {cell["id"]: _ownership(cell, objects, material_map, occurrence_id)
                      for cell in cells}
    for key, owners in sorted(face_owners.items()):
        if len(owners) != 1:
            continue
        cell, oriented = owners[0]
        face_id = "face-" + canonical_json_digest(list(key))
        boundary_faces.append({"id": face_id, "vertices": list(oriented)})
        face_ownership.append({"face_id": face_id, "vertices": list(oriented),
                               **cell_ownership[cell["id"]]})

    labels = [{"vertices": face["vertices"], "label": face["id"]} for face in boundary_faces]
    quality = _validate(mesh, labels, MAX_CELLS, MAX_VERTICES)
    body = {
        "occurrence_id": occurrence_id,
        "reference_id": reference_id,
        "source_sha256": source_sha256,
        "mesh": copy.deepcopy(mesh),
        "boundary_faces": boundary_faces,
        "material_map": dict(material_map),
        "stack_binding": stack_binding,
    }
    result = {
        "contract": RESULT_CONTRACT,
        "body": body,
        "cell_ownership": cell_ownership,
        "boundary_face_ownership": face_ownership,
        "mesh_sha256": canonical_json_digest(mesh),
        "quality": quality,
        "limitations": [
            "Input must be an already generated complete conforming tetrahedral PCB mesh.",
            "No CAD extraction, mesh generation, connector conductivity or contact is inferred.",
            "Terminal suitability still depends on explicitly supplied electrical material properties.",
        ],
    }
    return result


__all__ = ["prepare_pcb_electrothermal_geometry"]
