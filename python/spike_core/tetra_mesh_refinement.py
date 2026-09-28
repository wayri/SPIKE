# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded conforming edge-star bisection of an already conforming tetra mesh.

This is topology-preserving local refinement, not a CAD tetrahedralizer or an
intersection detector. Input must have no unrepresented geometric overlaps or
hanging entities. No vertex movement or solution transfer is performed.
"""
from __future__ import annotations

import copy
import itertools
import math

MAX_CELLS = 100_000
MAX_VERTICES = 100_000
MAX_EDGES = 256


class TetraRefinementError(ValueError):
    """Invalid topology, geometry, or refinement budget."""


def _require(condition, message):
    if not condition:
        raise TetraRefinementError(message)


def _keys(value, keys):
    _require(isinstance(value, dict) and set(value) == set(keys),
             "Object fields do not match the tetra refinement contract.")


def _indices(value, size, n):
    _require(isinstance(value, list) and len(value) == size and
             all(type(i) is int and 0 <= i < n for i in value) and
             len(set(value)) == size, "Invalid vertex indices.")


def _det(points, cell):
    a = points[cell[0]]
    b, c, d = [[points[i][j] - a[j] for j in range(3)] for i in cell[1:]]
    return (b[0] * (c[1]*d[2]-c[2]*d[1]) -
            b[1] * (c[0]*d[2]-c[2]*d[0]) +
            b[2] * (c[0]*d[1]-c[1]*d[0]))


def _validate_impl(mesh, boundary, max_cells, max_vertices):
    _keys(mesh, ('contract','units','coordinate_system','vertices','cells','counts','object_map'))
    _require(mesh['contract'] == 'spike/solver-mesh/v1' and
             mesh['units'] in ('m', 'mm') and
             mesh['coordinate_system'] == 'right_handed_xyz', 'Invalid mesh identity or units.')
    points, cells = mesh['vertices'], mesh['cells']
    _require(isinstance(points, list) and 4 <= len(points) <= max_vertices and
             isinstance(cells, list) and 1 <= len(cells) <= max_cells, 'Mesh resource budget exceeded.')
    _keys(mesh['counts'], ('vertices','cells'))
    _require(all(type(mesh['counts'][k]) is int for k in ('vertices','cells')) and
             mesh['counts'] == {'vertices':len(points),'cells':len(cells)}, 'Mesh counts mismatch.')
    for point in points:
        _require(isinstance(point, list) and len(point) == 3, 'Invalid coordinate.')
        for x in point:
            try:
                valid = type(x) in (int,float) and math.isfinite(x)
            except OverflowError:
                valid = False
            _require(valid, 'Coordinates must be finite numbers.')
    _require(len(set(map(tuple, points))) == len(points), 'Duplicate vertices.')
    objects = mesh['object_map']
    _require(isinstance(objects,dict) and len(objects) <= 100_000,'Invalid object map.')
    for key, metadata in objects.items():
        _require(isinstance(key,str) and isinstance(metadata,dict) and
                 'kind' in metadata and set(metadata) <= {'kind','net','layer'} and
                 all(isinstance(v,str) for v in metadata.values()) and bool(metadata['kind']),
                 'Invalid source metadata.')
    faces, seen, ids, volumes, qualities = {}, set(), set(), [], []
    for cell in cells:
        _keys(cell, ('id','kind','vertices','material_id','source_object_ids'))
        _require(isinstance(cell['id'],str) and 0 < len(cell['id']) <= 256 and
                 cell['id'] not in ids, 'Invalid or duplicate cell ID.')
        ids.add(cell['id'])
        _require(cell['kind'] == 'tetrahedron' and isinstance(cell['material_id'], str) and
                 0 < len(cell['material_id']) <= 256, 'Invalid cell kind or material.')
        sources = cell['source_object_ids']
        _require(isinstance(sources,list) and 1 <= len(sources) <= 1024 and
                 all(isinstance(s,str) and 0 < len(s) <= 1024 and s in objects for s in sources)
                 and len(set(sources)) == len(sources),'Invalid source ownership.')
        v = cell['vertices']
        _indices(v, 4, len(points))
        key = tuple(sorted(v))
        _require(key not in seen, 'Duplicate cells.')
        seen.add(key)
        determinant = _det(points, v)
        _require(math.isfinite(determinant) and determinant > 0, 'Inverted, degenerate, or unrepresentable tetrahedron.')
        volume = determinant / 6
        _require(math.isfinite(volume) and volume > 0, 'Unrepresentable cell volume.')
        volumes.append(volume)
        edge_sum = sum(sum((points[i][k]-points[j][k])**2 for k in range(3))
                       for i,j in itertools.combinations(v,2))
        _require(math.isfinite(edge_sum) and edge_sum > 0, 'Unrepresentable edge lengths.')
        # Mean-ratio quality, 1 for an equilateral tetrahedron, tending to 0 for a sliver.
        quality = 12 * (determinant / 2)**(2/3) / edge_sum
        _require(math.isfinite(quality) and quality > 0, 'Unrepresentable cell quality.')
        qualities.append(quality)
        for face in itertools.combinations(v, 3):
            f = tuple(sorted(face))
            opposite = next(i for i in v if i not in f)
            side = _det(points, list(f) + [opposite])
            _require(math.isfinite(side) and side != 0, 'Unrepresentable face orientation.')
            records = faces.setdefault(f, [])
            _require(len(records) < 2, 'Non-manifold face.')
            if records:
                _require((records[0] > 0) != (side > 0), 'Interior face owners lie on the same side.')
            records.append(side)
    _require(isinstance(boundary,list) and len(boundary) <= 4*max_cells, 'Invalid boundary array.')
    assigned = set()
    for item in boundary:
        _keys(item, ('vertices','label'))
        _indices(item['vertices'],3,len(points))
        _require(isinstance(item['label'],str) and 0 < len(item['label']) <= 128, 'Invalid boundary label.')
        f = tuple(sorted(item['vertices']))
        _require(f not in assigned and f in faces and len(faces[f]) == 1, 'Boundary face is duplicate, interior, or absent.')
        assigned.add(f)
    _require(assigned == {f for f, owners in faces.items() if len(owners)==1}, 'Boundary labels must cover every exterior face.')
    total = math.fsum(volumes)
    _require(math.isfinite(total) and total > 0, 'Unrepresentable volume.')
    return {'volume':total,'volume_units':mesh['units']+'^3',
            'minimum_mean_ratio':min(qualities),'minimum_cell_volume':min(volumes)}


def _validate(mesh, boundary, max_cells, max_vertices):
    try:
        return _validate_impl(mesh, boundary, max_cells, max_vertices)
    except (OverflowError, ZeroDivisionError) as exc:
        raise TetraRefinementError('Geometry is outside representable numerical range.') from exc


def refine_tetra_mesh(mesh, selected_edges, boundary_triangles, *,
                      max_cells=MAX_CELLS, max_vertices=MAX_VERTICES):
    """Bisect each selected existing edge in order across its complete cell star.

    Edge indices refer to the evolving vertex array; new vertices are appended.
    Returns a new mesh; the caller's mesh and boundary labels are never mutated.
    Repeated/nonexistent edges fail. Refinement does not promise improved shape
    quality: reported mean ratios allow a caller to reject a poorer candidate.
    """
    _require(type(max_cells) is int and 1 <= max_cells <= MAX_CELLS and
             type(max_vertices) is int and 4 <= max_vertices <= MAX_VERTICES,
             'Invalid resource budgets.')
    _require(isinstance(selected_edges,list) and len(selected_edges) <= MAX_EDGES,
             'Selected edge budget exceeded.')
    initial = _validate(mesh,boundary_triangles,max_cells,max_vertices)
    result, boundary = copy.deepcopy(mesh), copy.deepcopy(boundary_triangles)
    parents = {cell['id']:cell['id'] for cell in result['cells']}
    log = []
    for step, edge in enumerate(selected_edges):
        points, cells = result['vertices'], result['cells']
        _indices(edge,2,len(points))
        a,b = edge
        star = [cell for cell in cells if a in cell['vertices'] and b in cell['vertices']]
        _require(bool(star), 'Selected edge does not exist.')
        _require(len(points) < max_vertices and len(cells)+len(star) <= max_cells,
                 'Refinement resource budget exceeded.')
        midpoint = [points[a][k]/2 + points[b][k]/2 for k in range(3)]
        _require(tuple(midpoint) not in set(map(tuple,points)), 'Midpoint collapses onto an existing vertex.')
        mid = len(points)
        points.append(midpoint)
        new_cells, new_parents = [], {}
        for cell in cells:
            if not (a in cell['vertices'] and b in cell['vertices']):
                new_cells.append(cell)
                new_parents[cell['id']] = parents[cell['id']]
                continue
            for branch, replace in enumerate((b,a)):
                child = dict(cell)
                child['id'] = cell['id'] + f'__b{step}_{branch}'
                child['vertices'] = [mid if i==replace else i for i in cell['vertices']]
                new_cells.append(child)
                new_parents[child['id']] = parents[cell['id']]
        new_boundary = []
        for face in boundary:
            if a in face['vertices'] and b in face['vertices']:
                for replace in (b,a):
                    new_boundary.append({'label':face['label'],
                                         'vertices':[mid if i==replace else i for i in face['vertices']]})
            else:
                new_boundary.append(face)
        result['cells'] = new_cells
        result['counts'] = {'vertices':len(points),'cells':len(new_cells)}
        boundary, parents = new_boundary, new_parents
        quality = _validate(result,boundary,max_cells,max_vertices)
        _require(math.isclose(initial['volume'],quality['volume'],rel_tol=1e-12,abs_tol=0),
                 'Refinement volume conservation failed.')
        log.append({'edge':list(edge),'midpoint_vertex':mid,'split_cells':len(star)})
    return {'mesh':result,'boundary_triangles':boundary,'parent_cell_ids':parents,
            'refinement_log':log,'quality':{'before':initial,'after':_validate(result,boundary,max_cells,max_vertices)},
            'production_qualified':False}
