# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Conservative interior-vertex quality smoothing; not CAD shape optimization."""
import copy
import itertools
import math

from .tetra_mesh_refinement import TetraRefinementError, _det, _require, _validate


def _quality(points, cell):
    try:
        determinant = _det(points, cell)
        denominator = sum(sum((points[a][k]-points[b][k])**2 for k in range(3))
                          for a,b in itertools.combinations(cell,2))
        if determinant <= 0 or not math.isfinite(determinant) or not math.isfinite(denominator):
            return -1.0
        return 12*(determinant/2)**(2/3)/denominator
    except (OverflowError,ZeroDivisionError):
        return -1.0


def optimize_tetra_mesh(mesh, boundary_triangles, *, protected_vertices=None, iterations=3):
    """Backtracked Laplacian motion, accepting only improved incident minimum quality.

    Exterior/material-interface/protected vertices never move. Connectivity and
    IDs stay unchanged. No new geometric-overlap admission is provided; supply
    an already conforming nonoverlapping mesh. At most 20,000 trial moves run.
    """
    _require(type(iterations) is int and 1 <= iterations <= 10,'Invalid iteration budget.')
    before = _validate(mesh,boundary_triangles,5000,10000)
    points = mesh['vertices']
    protected = [] if protected_vertices is None else protected_vertices
    _require(isinstance(protected,list) and len(protected) <= len(points) and
             all(type(i) is int and 0 <= i < len(points) for i in protected) and
             len(set(protected)) == len(protected), 'Invalid protected vertices.')
    result = copy.deepcopy(mesh)
    points = result['vertices']
    cells = result['cells']
    fixed = set(protected)
    for face in boundary_triangles:
        fixed.update(face['vertices'])
    owners, incident, neighbours = {}, {}, {}
    for index,cell in enumerate(cells):
        v = cell['vertices']
        for vertex in v:
            incident.setdefault(vertex,[]).append(index)
            neighbours.setdefault(vertex,set()).update(i for i in v if i != vertex)
        for face in itertools.combinations(v,3):
            owners.setdefault(tuple(sorted(face)),set()).add(cell['material_id'])
    for face,regions in owners.items():
        if len(regions)>1:
            fixed.update(face)
    moves, trials, exhausted = [], 0, False
    for sweep in range(iterations):
        changed = False
        for vertex in sorted(set(incident)-fixed):
            adjacent = incident[vertex]
            old = points[vertex][:]
            ids = sorted(neighbours[vertex])
            candidate = [math.fsum(points[i][k]/len(ids) for i in ids) for k in range(3)]
            old_quality = min(_quality(points,cells[i]['vertices']) for i in adjacent)
            for level in range(12):
                if trials >= 20000:
                    exhausted = True
                    break
                trials += 1
                fraction = 2.0**(-level)
                points[vertex] = [(1-fraction)*old[k]+fraction*candidate[k] for k in range(3)]
                new_quality = min(_quality(points,cells[i]['vertices']) for i in adjacent)
                if new_quality > old_quality + max(1e-14,abs(old_quality)*1e-12):
                    moves.append({'vertex':vertex,'sweep':sweep,'fraction':fraction,
                                  'before_mean_ratio':old_quality,'after_mean_ratio':new_quality})
                    changed = True
                    break
                points[vertex] = old
            if exhausted:
                points[vertex] = old
                break
        if exhausted or not changed:
            break
    after = _validate(result,boundary_triangles,5000,10000)
    _require(after['minimum_mean_ratio'] >= before['minimum_mean_ratio'], 'Global quality decreased.')
    _require(math.isclose(after['volume'],before['volume'],rel_tol=1e-12,abs_tol=0),
             'Smoothing volume conservation failed.')
    return {'mesh':result,'boundary_triangles':copy.deepcopy(boundary_triangles),
            'quality':{'before':before,'after':after},'moves':moves,
            'fixed_vertices':sorted(fixed),'trial_moves':trials,'budget_exhausted':exhausted,
            'production_qualified':False}
