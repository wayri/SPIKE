# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original bounded, experimental Delaunay meshing of a point-cloud convex hull.

No CAD, surface constraints, holes, material interfaces, jitter, or shape-quality
guarantee. A finite enclosing tetrahedron is removed after insertion; if its
removal does not expose a certified supporting hull, the request fails closed.
Predicates use a conservative floating filter and exact binary-rational signs.
Cospherical ties use infinitesimal *lifted heights*, never moved coordinates.
"""
from __future__ import annotations

from fractions import Fraction
import itertools
import math
import sys

from .tetra_mesh_refinement import _validate, TetraRefinementError

MAX_POINTS = 128
MAX_CELLS = 5000
MAX_PREDICATES = 2_000_000
MAX_EXACT_PREDICATES = 100_000


class TetraGenerationError(ValueError):
    """Invalid input, exhausted budget, or uncertifiable tetrahedralization."""


def _require(condition, message):
    if not condition:
        raise TetraGenerationError(message)


def _det3(rows):
    a, b, c = rows
    return (a[0]*(b[1]*c[2]-b[2]*c[1]) -
            a[1]*(b[0]*c[2]-b[2]*c[0]) +
            a[2]*(b[0]*c[1]-b[1]*c[0]))


def _det4(rows):
    # Expand the same four cofactors without allocating their submatrices.
    # Preserve each minor's arithmetic order and the outer sum (including
    # compensated float summation on Python versions that provide it).
    a, b, c, d = rows
    return sum((
        a[0] * (b[1]*(c[2]*d[3]-c[3]*d[2]) -
                b[2]*(c[1]*d[3]-c[3]*d[1]) + b[3]*(c[1]*d[2]-c[2]*d[1])),
        -a[1] * (b[0]*(c[2]*d[3]-c[3]*d[2]) -
                 b[2]*(c[0]*d[3]-c[3]*d[0]) + b[3]*(c[0]*d[2]-c[2]*d[0])),
        a[2] * (b[0]*(c[1]*d[3]-c[3]*d[1]) -
                b[1]*(c[0]*d[3]-c[3]*d[0]) + b[3]*(c[0]*d[1]-c[1]*d[0])),
        -a[3] * (b[0]*(c[1]*d[2]-c[2]*d[1]) -
                 b[1]*(c[0]*d[2]-c[2]*d[0]) + b[2]*(c[0]*d[1]-c[1]*d[0])),
    ))


def _sign(value):
    return (value > 0) - (value < 0)


def _sphere_determinant(points, cell, point):
    """Lift differences with the original norm summation order."""
    origin = points[point]
    rows = []
    for index in cell:
        vertex = points[index]
        x, y, z = vertex[0]-origin[0], vertex[1]-origin[1], vertex[2]-origin[2]
        rows.append((x, y, z, sum((x*x, y*y, z*z))))
    return _det4(rows)


class _Predicates:
    def __init__(self, points, ranks):
        self.points = points
        self.exact = [tuple(Fraction(x) for x in p) for p in points]
        # Coordinates are immutable throughout one generation. This O(n)
        # metadata avoids repeatedly scanning every coordinate of each cell.
        self.magnitudes = [max(1., *(abs(x) for x in p)) for p in points]
        self.ranks = ranks
        self.calls = self.fallbacks = self.ties = 0

    def _count(self, exact=False):
        if exact:
            self.fallbacks += 1
            _require(self.fallbacks <= MAX_EXACT_PREDICATES, 'Exact predicate budget exceeded.')
        else:
            self.calls += 1
            _require(self.calls <= MAX_PREDICATES, 'Predicate work budget exceeded.')

    def _orientation_value(self, ids, exact=False):
        points = self.exact if exact else self.points
        origin = points[ids[0]]
        return _det3([[points[i][k]-origin[k] for k in range(3)] for i in ids[1:]])

    def orientation(self, ids):
        self._count()
        value = self._orientation_value(ids)
        magnitude = max(self.magnitudes[i] for i in ids)
        # Six degree-three monomials have magnitude <= (2M)^3. A deliberately
        # loose gamma_32 arithmetic bound is below 4096 eps M^3; M >= 1 also
        # covers absolute subnormal rounding error. Never use an uncertain sign.
        if abs(value) > 4096 * sys.float_info.epsilon * magnitude**3:
            return _sign(value)
        self._count(exact=True)
        return _sign(self._orientation_value(ids, exact=True))

    def sphere(self, cell, point, symbolic=True):
        """Positive means inside the sphere of a positively oriented cell."""
        self._count()
        value = _sphere_determinant(self.points, cell, point)
        magnitudes = self.magnitudes
        magnitude = max(magnitudes[cell[0]], magnitudes[cell[1]], magnitudes[cell[2]],
                        magnitudes[cell[3]], magnitudes[point])
        # Expansion has 72 degree-five monomials, each bounded by (2M)^5.
        # A loose gamma_128 bound on the expanded arithmetic is below
        # 2^20 eps M^5, including input subtraction error. M >= 1 also covers
        # absolute subnormal error. This is a correctness filter, not a fast
        # implementation of an optimized adaptive-predicate error bound.
        if abs(value) > 2**20 * sys.float_info.epsilon * magnitude**5:
            return -_sign(value)
        self._count(exact=True)
        value = _sphere_determinant(self.exact, cell, point)
        if value or not symbolic:
            return -_sign(value)
        self.ties += 1
        ids = (*cell, point)
        # Lift height h_i = |x_i|^2 - epsilon^(rank_i+1). The first nonzero
        # height-column cofactor is the exact lexicographic sign. Its minor
        # is minus the orientation of the remaining four ordered vertices.
        for row in sorted(range(5), key=lambda r: self.ranks[ids[r]]):
            remaining = [ids[r] for r in range(5) if r != row]
            coefficient = (-1 if (row+3) % 2 else 1) * self._orientation_value(remaining, True)
            if coefficient:
                return -_sign(coefficient)
        raise TetraGenerationError('Unresolvable degenerate sphere predicate.')


def _admit(points, units, material_id, source_object_id, boundary_label, max_cells):
    _require(type(max_cells) is int and 1 <= max_cells <= MAX_CELLS, 'Invalid cell budget.')
    _require(units in ('m', 'mm'), 'Units must be m or mm.')
    for value, limit, name in ((material_id, 256, 'material'), (source_object_id, 1024, 'source'),
                               (boundary_label, 128, 'boundary')):
        _require(isinstance(value, str) and 0 < len(value) <= limit, f'Invalid {name} identifier.')
    _require(isinstance(points, list) and 4 <= len(points) <= MAX_POINTS, 'Point budget is 4 to 128.')
    result = []
    for point in points:
        _require(isinstance(point, list) and len(point) == 3, 'Each point must contain three coordinates.')
        row = []
        for value in point:
            _require(type(value) in (int, float), 'Coordinates must be finite numbers, not bool.')
            try:
                number = float(value)
            except (OverflowError, ValueError) as exc:
                raise TetraGenerationError('Coordinate is not representable.') from exc
            _require(math.isfinite(number) and number == value, 'Coordinate is not exactly representable.')
            row.append(number)
        result.append(row)
    _require(len(set(map(tuple, result))) == len(result), 'Duplicate points are not permitted.')
    return result


def _normalized(points):
    # A power-of-two scaling is exact, unlike arbitrary normalization. Check
    # reversibility so extreme mixed scales cannot quietly discard coordinates.
    exponent = math.frexp(max(abs(x) for p in points for x in p))[1]
    scaled = [[math.ldexp(x, -exponent) for x in p] for p in points]
    _require(all(math.ldexp(y, exponent) == x for p, q in zip(points, scaled)
                 for x, y in zip(p, q)), 'Coordinate dynamic range is not representable.')
    center = [(min(p[k] for p in scaled)+max(p[k] for p in scaled))/2 for k in range(3)]
    radius = 64 * max(max(p[k] for p in scaled)-min(p[k] for p in scaled) for k in range(3))
    _require(radius > 0, 'Point cloud has no extent.')
    for offsets in ((1,1,1), (1,-1,-1), (-1,1,-1), (-1,-1,1)):
        scaled.append([center[k]+radius*offsets[k] for k in range(3)])
    return scaled


def _insert(cells, point, predicates, budget):
    removed = [cell for cell in cells if predicates.sphere(cell, point) > 0]
    _require(bool(removed), 'Point insertion has no certified cavity.')
    faces = {}
    for cell in removed:
        for face in itertools.combinations(cell, 3):
            key = tuple(sorted(face))
            faces[key] = faces.get(key, 0)+1
            _require(faces[key] <= 2, 'Non-manifold insertion cavity.')
    removed = set(removed)
    result = [cell for cell in cells if cell not in removed]
    for face, count in sorted(faces.items()):
        if count == 2:
            continue
        cell = (*face, point)
        orientation = predicates.orientation(cell)
        if orientation == 0:
            continue  # A flat cavity facet contributes zero volume, no tetrahedron.
        if orientation < 0:
            cell = (face[1], face[0], face[2], point)
        result.append(cell)
        _require(len(result) <= budget, 'Intermediate cell resource budget exceeded.')
    return result


def _certify(cells, n, predicates, boundary_label):
    _require(bool(cells) and {i for cell in cells for i in cell} == set(range(n)),
             'Coplanar input or omitted points: no complete 3D tetrahedralization.')
    faces, neighbours = {}, {cell: set() for cell in cells}
    for cell in cells:
        _require(predicates.orientation(cell) > 0, 'Nonpositive generated tetrahedron.')
        for face in itertools.combinations(cell, 3):
            faces.setdefault(tuple(sorted(face)), []).append(cell)
        for point in range(n):
            if point not in cell:
                _require(predicates.sphere(cell, point, symbolic=False) <= 0,
                         'Global empty-sphere certification failed.')
    boundary, edges = [], {}
    for face, owners in sorted(faces.items()):
        _require(len(owners) <= 2, 'Non-manifold output face.')
        if len(owners) == 2:
            neighbours[owners[0]].add(owners[1])
            neighbours[owners[1]].add(owners[0])
            continue
        opposite = next(i for i in owners[0] if i not in face)
        side = predicates.orientation((*face, opposite))
        _require(all(predicates.orientation((*face, i))*side >= 0 for i in range(n)),
                 'Finite enclosure did not yield a supporting convex hull; unsupported conditioning.')
        outward = list(face if side < 0 else (face[1], face[0], face[2]))
        boundary.append({'vertices': outward, 'label': boundary_label})
        for edge in itertools.combinations(face, 2):
            edges[edge] = edges.get(edge, 0)+1
    _require(bool(boundary) and all(count == 2 for count in edges.values()),
             'Exterior is not a closed two-manifold.')
    boundary_vertices = {i for face in boundary for i in face['vertices']}
    _require(len(boundary_vertices)-len(edges)+len(boundary) == 2,
             'Exterior does not have spherical hull topology.')
    for vertex in boundary_vertices:
        link = {}
        for item in boundary:
            face = item['vertices']
            if vertex in face:
                a, b = [i for i in face if i != vertex]
                link.setdefault(a, set()).add(b)
                link.setdefault(b, set()).add(a)
        reached, stack = set(), [next(iter(link))]
        while stack:
            current = stack.pop()
            if current not in reached:
                reached.add(current)
                stack.extend(link[current]-reached)
        _require(all(len(adjacent) == 2 for adjacent in link.values()) and len(reached) == len(link),
                 'Exterior vertex link is not a single manifold cycle.')
    seen, pending = set(), [cells[0]]
    while pending:
        cell = pending.pop()
        if cell not in seen:
            seen.add(cell)
            pending.extend(neighbours[cell]-seen)
    _require(len(seen) == len(cells), 'Disconnected tetrahedralization.')
    return boundary


def generate_tetra_mesh(points, *, units='m', material_id='solid', source_object_id='domain',
                        boundary_label='exterior', max_cells=MAX_CELLS):
    """Return a certified experimental convex-hull mesh, or raise without output.

    All input points are retained in their original order; insertion and ties
    are lexicographic-coordinate deterministic. Units are preserved, not
    converted. max_cells bounds the final mesh; intermediate enclosing cells
    additionally have a fixed allowance of 4*MAX_POINTS. No solver/release
    qualification is inferred from geometric certification.
    """
    vertices = _admit(points, units, material_id, source_object_id, boundary_label, max_cells)
    n = len(vertices)
    order = sorted(range(n), key=lambda i: tuple(vertices[i]))
    ranks = {i: rank for rank, i in enumerate(order+list(range(n, n+4)))}
    predicates = _Predicates(_normalized(vertices), ranks)
    super_cell = tuple(range(n, n+4))
    if predicates.orientation(super_cell) < 0:
        super_cell = (n+1, n, n+2, n+3)
    for face in itertools.combinations(super_cell, 3):
        opposite = next(i for i in super_cell if i not in face)
        side = predicates.orientation((*face, opposite))
        _require(side != 0 and all(predicates.orientation((*face, i))*side > 0 for i in range(n)),
                 'Unable to represent a strictly enclosing tetrahedron.')
    cells = [super_cell]
    for point in order:
        cells = _insert(cells, point, predicates, max_cells+4*MAX_POINTS)
    cells = sorted((cell for cell in cells if all(i < n for i in cell)), key=lambda c: tuple(sorted(c)))
    _require(len(cells) <= max_cells, 'Final cell resource budget exceeded.')
    boundary = _certify(cells, n, predicates, boundary_label)
    mesh = {'contract': 'spike/solver-mesh/v1', 'units': units,
            'coordinate_system': 'right_handed_xyz', 'vertices': vertices,
            'cells': [{'id': f'tetra_{i}', 'kind': 'tetrahedron', 'vertices': list(cell),
                       'material_id': material_id, 'source_object_ids': [source_object_id]}
                      for i, cell in enumerate(cells)],
            'counts': {'vertices': n, 'cells': len(cells)},
            'object_map': {source_object_id: {'kind': 'convex_point_cloud'}}}
    try:
        quality = _validate(mesh, boundary, max_cells, MAX_POINTS)
    except TetraRefinementError as exc:
        raise TetraGenerationError(str(exc)) from exc
    return {'mesh': mesh, 'boundary_triangles': boundary, 'quality': quality,
            'evidence': {'algorithm': 'internal_incremental_delaunay',
                         'domain': 'point_cloud_convex_hull', 'all_input_points_used': True,
                         'positive_cell_volumes': True, 'supporting_convex_boundary': True,
                         'closed_manifold_boundary': True, 'weak_delaunay': True,
                         'predicate_calls': predicates.calls, 'exact_fallbacks': predicates.fallbacks,
                         'symbolic_sphere_ties': predicates.ties,
                         'point_limit': MAX_POINTS, 'cell_limit': max_cells,
                         'predicate_limit': MAX_PREDICATES, 'exact_predicate_limit': MAX_EXACT_PREDICATES,
                         'coordinate_perturbation': False, 'surface_constraints': False,
                         'production_qualified': False},
            'production_qualified': False}
