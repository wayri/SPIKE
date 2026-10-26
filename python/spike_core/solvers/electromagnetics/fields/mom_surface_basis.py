# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original oriented triangular-surface / full RWG basis foundation.

This is NOT an electromagnetic solver: no EFIE, singular integration,
material model, excitation or scattering solution is implemented. Open
surfaces are admitted, but boundary half-RWG functions are not constructed.
Topological manifold checks do not establish absence of geometric surface
intersections, watertight CAD identity, or physical applicability.

Method vocabulary: https://bempp.com/handbook/api/function_spaces.html
The implementation is independently authored from the RWG definition.
Coordinates are metres; basis functions are dimensionless, divergence is 1/m.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numbers

import numpy as np

MAX_VERTICES = 100_000
MAX_TRIANGLES = 200_000
MAX_EVALUATION_POINTS = 100_000


class SurfaceBasisError(ValueError):
    """Invalid, non-manifold, numerically unsafe or oversized surface input."""


@dataclass(frozen=True)
class RwgEdge:
    vertices: tuple[int, int]
    plus_face: int
    minus_face: int
    plus_free_vertex: int
    minus_free_vertex: int
    length_m: float


@dataclass(frozen=True)
class SurfaceBasis:
    vertices_m: tuple[tuple[float, float, float], ...]
    triangles: tuple[tuple[int, int, int], ...]
    areas_m2: tuple[float, ...]
    normals: tuple[tuple[float, float, float], ...]
    edges: tuple[RwgEdge, ...]
    boundary_edges: tuple[tuple[int, int], ...]
    connected_components: int
    intersection_free_proven: bool = False
    executable_em_solver: bool = False


def _index(value, count, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral):
        raise SurfaceBasisError(f"{name} must be an integer.")
    value = int(value)
    if value < 0 or value >= count:
        raise SurfaceBasisError(f"{name} is out of range.")
    return value


def _array(value, shape_tail, limit, name):
    # Object/string/bool arrays are deliberately not silently coerced.
    try:
        if not 1 <= len(value) <= limit:
            raise SurfaceBasisError(f"{name} count exceeds budget or is zero.")
        if isinstance(value, (list, tuple)):
            for row in value:
                if not isinstance(row, (list, tuple, np.ndarray)) or len(row) != shape_tail[0]:
                    raise SurfaceBasisError(f"{name} requires three entries per row.")
                if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, numbers.Real) for v in row):
                    raise SurfaceBasisError(f"{name} requires real, non-boolean entries.")
        arr = np.asarray(value)
        if arr.ndim != 2 or arr.shape[1:] != shape_tail or not 1 <= len(arr) <= limit:
            raise SurfaceBasisError(f"{name} has invalid shape or exceeds budget.")
        if arr.dtype.kind not in "fiu":
            raise SurfaceBasisError(f"{name} requires real numeric entries.")
        with np.errstate(all="raise"):
            arr = arr.astype(float)
        if not np.isfinite(arr).all():
            raise SurfaceBasisError(f"{name} contains non-finite entries.")
        return arr
    except (TypeError, OverflowError, FloatingPointError, ValueError) as exc:
        raise SurfaceBasisError(f"Invalid {name}: {exc}") from exc


def build_surface_basis(vertices_m, triangles) -> SurfaceBasis:
    """Canonicalize supplied oriented triangles and construct interior-edge RWGs.

    Canonical IDs depend on coordinate order, not input vertex/face numbering.
    Reversing a complete component's orientation is allowed and is NOT treated
    as the same oriented surface. No vertex welding or orientation repair occurs.
    Complexity is O(V log V + F log F), with O(V + F) retained storage.
    """
    xyz = _array(vertices_m, (3,), MAX_VERTICES, "vertices_m")
    try:
        count = len(triangles)
    except TypeError as exc:
        raise SurfaceBasisError("triangles must be a bounded sequence.") from exc
    if not 1 <= count <= MAX_TRIANGLES:
        raise SurfaceBasisError("triangle count exceeds budget or is zero.")
    coords = [tuple(float(v) for v in row) for row in xyz]
    if len(set(coords)) != len(coords):
        raise SurfaceBasisError("Coincident vertices require explicit upstream welding.")
    order = sorted(range(len(coords)), key=coords.__getitem__)
    remap = {old: new for new, old in enumerate(order)}
    vertices = tuple(coords[old] for old in order)
    faces, used, keys = [], set(), set()
    for raw in triangles:
        if not isinstance(raw, (tuple, list, np.ndarray)) or (isinstance(raw, np.ndarray) and raw.ndim != 1) or len(raw) != 3:
            raise SurfaceBasisError("Every triangle requires three vertex indices.")
        face = tuple(remap[_index(i, len(vertices), "vertex index")] for i in raw)
        key = tuple(sorted(face))
        if len(set(face)) != 3 or key in keys:
            raise SurfaceBasisError("Repeated triangle or repeated triangle vertex.")
        keys.add(key)
        used.update(face)
        start = face.index(min(face))
        faces.append(face[start:] + face[:start])
    if len(used) != len(vertices):
        raise SurfaceBasisError("Unused vertices are not admitted.")
    faces = tuple(sorted(faces))
    xyz = np.asarray(vertices)
    areas, normals, owners = [], [], {}
    incident = [[] for _ in vertices]
    try:
        with np.errstate(all="raise"):
            for fi, face in enumerate(faces):
                a, b, c = xyz[list(face)]
                ab, ac = b - a, c - a
                scale = max(float(np.max(np.abs(ab))), float(np.max(np.abs(ac))))
                if scale == 0:
                    raise SurfaceBasisError("Degenerate triangle.")
                cross = np.cross(ab / scale, ac / scale)
                magnitude = float(np.linalg.norm(cross))
                if magnitude <= 1e-14:
                    raise SurfaceBasisError("Degenerate or numerically singular triangle.")
                area = .5 * magnitude * scale * scale
                if not math.isfinite(area) or area <= 0:
                    raise SurfaceBasisError("Triangle area is not representable.")
                areas.append(area)
                normals.append(tuple(float(v) for v in cross / magnitude))
                for i in range(3):
                    incident[face[i]].append(fi)
                    directed = (face[i], face[(i + 1) % 3])
                    edge = tuple(sorted(directed))
                    owners.setdefault(edge, []).append((fi, directed == edge, face[(i + 2) % 3]))
    except (FloatingPointError, OverflowError) as exc:
        raise SurfaceBasisError("Surface geometry exceeds numerical range.") from exc
    adjacency = [set() for _ in faces]
    vertex_links = [{} for _ in vertices]
    edges, boundary = [], []
    for edge, attached in sorted(owners.items()):
        if len(attached) > 2:
            raise SurfaceBasisError("Non-manifold edge has more than two triangles.")
        if len(attached) == 1:
            boundary.append(edge)
            continue
        a, b = attached
        if a[1] == b[1]:
            raise SurfaceBasisError("Adjacent triangles have inconsistent orientation.")
        plus, minus = (a, b) if a[1] else (b, a)
        adjacency[a[0]].add(b[0])
        adjacency[b[0]].add(a[0])
        for vertex in edge:
            links = vertex_links[vertex]
            links.setdefault(a[0], set()).add(b[0])
            links.setdefault(b[0], set()).add(a[0])
        length = math.dist(vertices[edge[0]], vertices[edge[1]])
        if not math.isfinite(length) or length <= 0:
            raise SurfaceBasisError("Edge length is not representable.")
        # Reject under/overflow that would make basis/divergence meaningless.
        for face in (plus[0], minus[0]):
            ratio = length / areas[face]
            if not math.isfinite(ratio) or ratio == 0:
                raise SurfaceBasisError("RWG divergence is not representable.")
        edges.append(RwgEdge(edge, plus[0], minus[0], plus[2], minus[2], length))
    for attached, links in zip(incident, vertex_links):
        reached, pending = set(), [attached[0]]
        while pending:
            face = pending.pop()
            if face not in reached:
                reached.add(face)
                pending.extend(links.get(face, ()))
        if len(reached) != len(attached):
            raise SurfaceBasisError("Non-manifold vertex has disconnected triangle fans.")
    remaining, components = set(range(len(faces))), 0
    while remaining:
        components += 1
        pending = [next(iter(remaining))]
        while pending:
            face = pending.pop()
            if face in remaining:
                remaining.remove(face)
                pending.extend(adjacency[face])
    return SurfaceBasis(vertices, faces, tuple(areas), tuple(normals), tuple(edges), tuple(boundary), components)


def divergence(surface: SurfaceBasis, edge_index: int, face_index: int) -> float:
    """Constant surface divergence on a canonical triangle; zero off support."""
    edge = surface.edges[_index(edge_index, len(surface.edges), "edge index")]
    face = _index(face_index, len(surface.triangles), "face index")
    sign = 1 if face == edge.plus_face else -1 if face == edge.minus_face else 0
    if sign == 0:
        return 0.
    return sign * edge.length_m / surface.areas_m2[face]


def evaluate(surface: SurfaceBasis, edge_index: int, face_index: int, barycentric) -> np.ndarray:
    """Evaluate at barycentric points on one canonical triangle, shape (N,3)."""
    edge = surface.edges[_index(edge_index, len(surface.edges), "edge index")]
    face = _index(face_index, len(surface.triangles), "face index")
    weights = _array(barycentric, (3,), MAX_EVALUATION_POINTS, "barycentric points")
    if (weights < 0).any() or (weights > 1).any() or not np.allclose(weights.sum(axis=1), 1., rtol=0., atol=1e-14):
        raise SurfaceBasisError("Points must lie on the closed reference triangle.")
    if face not in (edge.plus_face, edge.minus_face):
        return np.zeros_like(weights)
    free = edge.plus_free_vertex if face == edge.plus_face else edge.minus_free_vertex
    sign = 1 if face == edge.plus_face else -1
    try:
        with np.errstate(all="raise"):
            # Relative coordinates avoid multiplying large absolute offsets.
            relative = np.asarray([np.subtract(surface.vertices_m[v], surface.vertices_m[free]) for v in surface.triangles[face]])
            result = (weights @ relative) * (sign * .5 * edge.length_m / surface.areas_m2[face])
        if not np.isfinite(result).all():
            raise SurfaceBasisError("Basis evaluation is not representable.")
        return result
    except (FloatingPointError, OverflowError) as exc:
        raise SurfaceBasisError("Basis evaluation exceeds numerical range.") from exc
