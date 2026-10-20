# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Strict experimental SI tetra topology and optional OCC-result conversion.

No meshing, nonshared contact qualification, CAD authenticity or public route.
See docs/validation/CFD_TETRA_MESH_20261021.md for derivation and limitations.
"""
import copy
import hashlib
import itertools
import json
import math

import numpy as np

CONTRACT = "spike/cfd-tetra-mesh/v1"
MAX_CELLS = 4096
MAX_VERTICES = 4*MAX_CELLS
MAX_FACES = 4*MAX_CELLS
MAX_CONDITION = 1e6
_LOCAL_FACES = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))


class CfdTetraMeshError(ValueError):
    """Mesh geometry, topology, provenance or resource admission failed."""


def _require(condition, message):
    if not condition:
        raise CfdTetraMeshError(message)


def _indices(row, count, size):
    _require(isinstance(row, list) and len(row) == size
             and all(type(v) is int and 0 <= v < count for v in row)
             and len(set(row)) == size, "Invalid vertex connectivity")
    return tuple(row)


def _label(value):
    return isinstance(value, str) and 0 < len(value) <= 128 and not any(ord(c) < 32 for c in value)


def _boundary_manifold(faces):
    """A closed boundary has two triangles per edge and cyclic vertex links."""
    edges, links = {}, {}
    for face in faces:
        for a, b in itertools.combinations(face, 2):
            edge = tuple(sorted((a, b)))
            edges[edge] = edges.get(edge, 0)+1
        for v in face:
            a, b = (i for i in face if i != v)
            graph = links.setdefault(v, {})
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)
    _require(all(v == 2 for v in edges.values()), "Nonmanifold exterior edge")
    for graph in links.values():
        _require(all(len(v) == 2 for v in graph.values()), "Nonmanifold exterior vertex link")
        seen, pending = set(), [next(iter(graph))]
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(graph[node]-seen)
        _require(len(seen) == len(graph), "Disconnected exterior vertex link")


def _admit(mesh, cancel_check):
    if cancel_check and cancel_check():
        raise InterruptedError("Tetra mesh admission cancelled")
    _require(isinstance(mesh, dict) and set(mesh) == {
        "contract", "units", "vertices", "cells", "boundary_patches"},
        "Unexpected numerical mesh fields")
    _require(mesh["contract"] == CONTRACT and mesh["units"] == "m", "Invalid mesh contract or units")
    raw, cells = mesh["vertices"], mesh["cells"]
    _require(isinstance(raw, list) and 4 <= len(raw) <= MAX_VERTICES
             and isinstance(cells, list) and 1 <= len(cells) <= MAX_CELLS, "Mesh resource budget exceeded")
    for point in raw:
        _require(isinstance(point, list) and len(point) == 3 and all(
            type(v) in (int, float) and math.isfinite(v) for v in point), "Nonfinite or invalid vertex")
    _require(len(set(map(tuple, raw))) == len(raw), "Duplicate geometric vertices")
    connectivity = [_indices(row, len(raw), 4) for row in cells]
    _require(len({tuple(sorted(c)) for c in connectivity}) == len(cells), "Duplicate tetrahedra")
    _require(set(itertools.chain.from_iterable(connectivity)) == set(range(len(raw))), "Orphan vertices")
    patches = mesh["boundary_patches"]
    _require(isinstance(patches, dict) and 1 <= len(patches) <= MAX_FACES
             and all(_label(k) for k in patches), "Invalid boundary patch IDs")
    supplied, patch_keys = set(), {}
    for label, rows in patches.items():
        _require(isinstance(rows, list) and 1 <= len(rows) <= MAX_FACES, "Invalid boundary patch")
        patch_keys[label] = []
        for row in rows:
            key = tuple(sorted(_indices(row, len(raw), 3)))
            _require(key not in supplied and len(supplied) < MAX_FACES, "Duplicate or excessive boundary faces")
            supplied.add(key)
            patch_keys[label].append(key)
    vertices = np.array(raw, dtype=float)
    tetra = np.array(connectivity, dtype=np.int64)
    volumes, gradients, centroids, conditions = [], [], [], []
    face_ids, face_vertices, owners, areas, normals, centers = {}, [], [], [], [], []
    cell_faces = np.empty((len(cells), 4), dtype=np.int64)
    signs = np.empty((len(cells), 4), dtype=np.int8)
    adjacency = [set() for _ in cells]
    for t, cell in enumerate(tetra):
        if cancel_check and cancel_check():
            raise InterruptedError("Tetra mesh admission cancelled")
        points = vertices[cell]
        local = points-points[0]
        length = float(np.max(abs(local)))
        _require(length > 0., "Collapsed tetrahedron")
        normalized = local/length
        jacobian = normalized[1:].T
        condition = float(np.linalg.cond(jacobian))
        determinant = float(np.linalg.det(jacobian))
        _require(math.isfinite(condition) and condition <= MAX_CONDITION, "Tetrahedron condition exceeds 1e6")
        _require(determinant > 0., "Inverted or degenerate tetrahedron; orientation is not repaired")
        volume = float(np.multiply(np.multiply(length, length), length)*determinant/6.)
        _require(math.isfinite(volume) and volume > 0., "Unrepresentable cell volume")
        inverse = np.linalg.inv(jacobian)/length
        gradients.append(np.vstack((-inverse.sum(axis=0), inverse)))
        volumes.append(volume)
        centroids.append(points[0]+local.mean(axis=0))
        conditions.append(condition)
        area_vectors, local_centers = [], []
        for opposite, face in enumerate(_LOCAL_FACES):
            triangle = normalized[list(face)]
            vector = np.cross(triangle[1]-triangle[0], triangle[2]-triangle[0])/2.
            area = float(np.linalg.norm(vector))
            _require(area > 0., "Collapsed face")
            area_vectors.append(vector)
            local_centers.append(triangle.mean(axis=0))
            key = tuple(sorted(int(cell[i]) for i in face))
            normal = vector/area
            if key in face_ids:
                f = face_ids[key]
                _require(owners[f][1] == -1, "Nonmanifold face has more than two owners")
                # All face-local determinants are computed after subtraction.
                side = float(np.dot(normal, normalized[opposite]-triangle[0]))
                _require(side < 0. and float(np.dot(normals[f], normal)) < -1.+1e-10,
                         "Shared facet owners are not on opposite sides")
                owners[f][1] = t
                adjacency[t].add(owners[f][0])
                adjacency[owners[f][0]].add(t)
                signs[t, opposite] = -1
            else:
                f = len(face_vertices)
                face_ids[key] = f
                face_vertices.append([int(cell[i]) for i in face])
                owners.append([t, -1])
                areas.append(float(np.multiply(length, length)*area))
                normals.append(normal)
                centers.append(points[0]+length*triangle.mean(axis=0))
                signs[t, opposite] = 1
            cell_faces[t, opposite] = f
        vectors = np.array(area_vectors)
        closure = float(np.max(abs(vectors.sum(axis=0))))/sum(np.linalg.norm(v) for v in vectors)
        moment = float(np.sum(vectors*np.array(local_centers)))
        _require(closure <= 1e-12 and abs(moment-determinant/2.) <= 1e-10*determinant/2.,
                 "Cell geometric closure or first-moment identity failed")
    exterior = {key for key, f in face_ids.items() if owners[f][1] < 0}
    _require(supplied == exterior, "Boundary patches must cover every exterior facet exactly once")
    _boundary_manifold(exterior)
    from .cfd_tetra_intersections import screen_positive_volume_intersections
    screening = screen_positive_volume_intersections(
        vertices, tetra, owners, cancel_check=cancel_check)
    components, visited = [], set()
    for t in range(len(cells)):
        if t in visited:
            continue
        component, pending = [], [t]
        while pending:
            cell = pending.pop()
            if cell not in visited:
                visited.add(cell)
                component.append(cell)
                pending.extend(adjacency[cell]-visited)
        components.append(np.array(sorted(component), dtype=np.int64))
    normals, volumes = np.array(normals), np.array(volumes)
    return {"vertices": vertices, "cells": tetra, "volumes": volumes,
            "cell_volumes": volumes, "cell_centroids": np.array(centroids),
            "barycentric_gradients": np.array(gradients),
            "face_vertices": np.array(face_vertices, dtype=np.int64),
            "face_areas": np.array(areas), "face_normals": normals,
            "face_centroids": np.array(centers), "face_owners": np.array(owners, dtype=np.int64),
            "cell_faces": cell_faces, "cell_face_signs": signs,
            "cell_outward_normals": normals[cell_faces]*signs[..., None],
            "boundary_patches": {label: np.array([face_ids[k] for k in keys], dtype=np.int64)
                                 for label, keys in patch_keys.items()},
            "components": components, "maximum_cell_condition": max(conditions),
            "global_intersections_checked": False, "intersection_screening": screening,
            "production_qualified": False}


def admit_cfd_tetra_mesh(mesh, *, cancel_check=None):
    """Return copied SI topology/geometry or raise CfdTetraMeshError; no repairs."""
    try:
        with np.errstate(all="raise"):
            return _admit(mesh, cancel_check)
    except (ArithmeticError, TypeError, np.linalg.LinAlgError) as exc:
        raise CfdTetraMeshError("Unrepresentable or malformed tetra geometry") from exc
    except ValueError as exc:
        if isinstance(exc, CfdTetraMeshError):
            raise
        raise CfdTetraMeshError(str(exc)) from exc


def _snapshot(value):
    """Bound metadata serialization before retaining any encoded result."""
    pending, count = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        count += 1
        _require(count <= 250000 and depth <= 24, "OCC metadata nesting/count budget exceeded")
        if isinstance(item, dict):
            _require(len(item) <= MAX_FACES and all(isinstance(k, str) and len(k) <= 1024 for k in item),
                     "Invalid or excessive OCC metadata keys")
            pending.extend((v, depth+1) for v in item.values())
        elif isinstance(item, list):
            _require(len(item) <= MAX_FACES, "OCC metadata array budget exceeded")
            pending.extend((v, depth+1) for v in item)
        elif isinstance(item, str):
            _require(len(item) <= 4096, "OCC metadata string budget exceeded")
        else:
            _require(item is None or type(item) is bool or
                     (type(item) in (int, float) and math.isfinite(item)), "Invalid OCC metadata scalar")
    parts, size = [], 0
    for part in json.JSONEncoder(sort_keys=True, allow_nan=False, separators=(",", ":")).iterencode(value):
        size += len(part.encode("utf-8"))
        _require(size <= 8*1024**2, "OCC result exceeds 8 MiB bridge budget")
        parts.append(part)
    payload = "".join(parts)
    return json.loads(payload), hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _prepare(occ_result, assignments):
    _require(isinstance(occ_result, dict) and occ_result.get("contract") in (
        "spike/gmsh-occ-mesh-result/v1", "spike/gmsh-occ-mesh-result/v2")
        and occ_result.get("status") == "completed"
        and occ_result.get("production_qualified") is False, "Invalid experimental OCC result")
    source = occ_result.get("mesh", {})
    _require(isinstance(source, dict) and isinstance(source.get("cells"), list)
             and 1 <= len(source["cells"]) <= MAX_CELLS
             and isinstance(source.get("vertices"), list)
             and 4 <= len(source["vertices"]) <= MAX_VERTICES, "OCC bridge resource budget exceeded")
    result, digest = _snapshot(occ_result)
    source = result["mesh"]
    _require(source.get("units") == "mm", "OCC bridge requires millimetres")
    _require(result.get("interface_faces") == [], "CAD interfaces are not admitted for single-fluid CFD")
    boundary = result.get("boundary_faces")
    _require(isinstance(boundary, list) and 1 <= len(boundary) <= MAX_FACES, "Invalid CAD boundary records")
    from .tetra_mesh_refinement import _validate
    _validate(source, [{"vertices": f["vertices"], "label": "cad"} for f in boundary],
              MAX_CELLS, MAX_VERTICES)
    cells = source["cells"]
    _require(len({c["material_id"] for c in cells}) == 1, "Multiple materials are not admitted")
    sources = {s for c in cells for s in c["source_object_ids"]}
    _require(sources == set(source["object_map"]), "Source object map does not match cell coverage")
    tags, patches, actual_owners = set(), {}, {}
    for cell in cells:
        for face in itertools.combinations(cell["vertices"], 3):
            actual_owners.setdefault(tuple(sorted(face)), []).append(cell)
    for face in boundary:
        _require(set(face) == {"vertices", "cad_surface_tag", "cell_ids", "material_ids", "source_object_ids"},
                 "Unexpected CAD boundary fields")
        tag = face["cad_surface_tag"]
        _require(type(tag) is int and tag > 0, "Invalid CAD surface tag")
        tags.add(tag)
        owner = actual_owners[tuple(sorted(face["vertices"]))][0]
        _require(face["cell_ids"] == [owner["id"]] and face["material_ids"] == [owner["material_id"]]
                 and face["source_object_ids"] == sorted(owner["source_object_ids"]),
                 "CAD boundary membership does not match tetra owner")
    _require(isinstance(assignments, dict) and set(assignments) == tags
             and all(type(k) is int and _label(v) for k, v in assignments.items()),
             "Explicit patch assignments must cover every CAD surface tag exactly")
    _require(result.get("boundary_triangles") == [f["vertices"] for f in boundary],
             "Redundant CAD boundary triangle membership mismatch")
    for face in boundary:
        patches.setdefault(assignments[face["cad_surface_tag"]], []).append(face["vertices"])
    ownership = result.get("fragment_ownership")
    _require(isinstance(ownership, dict) and 1 <= len(ownership) <= MAX_CELLS, "Missing fragment provenance")
    signatures, cad_volumes = {}, {}
    for tag, own in ownership.items():
        _require(isinstance(tag, str) and tag.isdigit() and int(tag) > 0
                 and isinstance(own, dict) and set(own) == {"source_object_ids", "material_id", "cad_volume_mm3"},
                 "Invalid CAD fragment ownership")
        ids = own["source_object_ids"]
        _require(isinstance(ids, list) and ids and len(ids) == len(set(ids))
                 and all(isinstance(s, str) and s in sources for s in ids), "Invalid fragment source binding")
        signature = (own["material_id"], tuple(sorted(ids)))
        _require(signature not in signatures, "Ambiguous fragment membership without cell fragment IDs")
        signatures[signature] = tag
        volume = own["cad_volume_mm3"]
        _require(type(volume) in (int, float) and math.isfinite(volume) and volume > 0, "Invalid CAD volume")
        cad_volumes[tag] = volume
    per_fragment = {tag: 0. for tag in ownership}
    numerical = {"contract": CONTRACT, "units": "m",
                 "vertices": (np.array(source["vertices"])*.001).tolist(),
                 "cells": [c["vertices"] for c in cells], "boundary_patches": patches}
    admitted = admit_cfd_tetra_mesh(numerical)
    for cell, volume in zip(cells, admitted["cell_volumes"]):
        signature = (cell["material_id"], tuple(sorted(cell["source_object_ids"])))
        _require(signature in signatures, "Cell source/material has no CAD fragment binding")
        per_fragment[signatures[signature]] += float(volume)*1e9
    _require(all(v > 0. for v in per_fragment.values()), "Orphan CAD fragment")
    metrics = result.get("metrics", {})
    def agrees(actual, expected):
        return type(actual) in (int, float) and math.isfinite(actual) and math.isclose(
            actual, expected, rel_tol=1e-9, abs_tol=0.)
    _require(isinstance(metrics, dict)
             and agrees(metrics.get("cad_volume_mm3"), sum(cad_volumes.values()))
             and agrees(metrics.get("tetrahedron_volume_mm3"), sum(per_fragment.values()))
             and isinstance(metrics.get("fragment_mesh_volumes_mm3"), dict)
             and set(metrics["fragment_mesh_volumes_mm3"]) == set(per_fragment)
             and all(agrees(metrics["fragment_mesh_volumes_mm3"][k], v) for k, v in per_fragment.items()),
             "CAD/mesh volume provenance mismatch")
    expected_sources = {s: sum(v for tag, v in cad_volumes.items()
                              if s in ownership[tag]["source_object_ids"]) for s in sources}
    _require(isinstance(metrics.get("source_cad_volumes_mm3"), dict)
             and set(metrics["source_cad_volumes_mm3"]) == sources
             and all(agrees(metrics["source_cad_volumes_mm3"][s], v) for s, v in expected_sources.items()),
             "CAD source-volume binding mismatch")
    if "request_sha256" in result:
        _require(isinstance(result["request_sha256"], str) and len(result["request_sha256"]) == 64
                 and all(c in "0123456789abcdef" for c in result["request_sha256"]),
                 "Malformed OCC request digest")
    return {"mesh": numerical, "provenance": {
        "occ_result_sha256": digest, "source_units": "mm", "target_units": "m",
        "original_cell_records": copy.deepcopy(cells), "object_map": copy.deepcopy(source["object_map"]),
        "fragment_ownership": copy.deepcopy(ownership), "cad_surface_patches": dict(assignments),
        "request_sha256": result.get("request_sha256"),
        "runtime_provenance": copy.deepcopy(result.get("runtime_provenance")),
        "source_authenticity_verified": False},
        "geometry_diagnostics": {
            "cad_volume_mm3": sum(cad_volumes.values()), "tetrahedron_volume_mm3": sum(per_fragment.values()),
            "relative_cad_tetra_volume_difference": abs(sum(per_fragment.values())-sum(cad_volumes.values()))
                                                   /sum(cad_volumes.values()),
            "global_intersections_checked": False,
            "intersection_screening": dict(admitted["intersection_screening"])},
        "production_qualified": False}


def prepare_cfd_tetra_mesh(occ_result, patch_assignments):
    """Convert an admitted single-fluid OCC result with explicit surface labels."""
    try:
        with np.errstate(all="raise"):
            return _prepare(occ_result, patch_assignments)
    except (ArithmeticError, TypeError, KeyError, RecursionError, ValueError) as exc:
        if isinstance(exc, CfdTetraMeshError):
            raise
        raise CfdTetraMeshError("Invalid OCC bridge input: "+str(exc)) from exc
