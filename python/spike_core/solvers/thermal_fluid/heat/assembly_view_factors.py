# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Experimental, geometry-derived diffuse view factors; not a thermal solver.

API: derive_assembly_view_factors(request), request contract
spike/assembly-view-factor-request/v1, units='m', surfaces=[{id, triangles}],
optional occluders=[triangle], quadrature={level, max_pair_evaluations,
max_visibility_tests, max_geometry_pairs}. Triangles contain three XYZ lists.
Each emitting surface is planar, nonoverlapping and consistently oriented;
different surfaces must be separated. Occluders are opaque on both sides.

Independent derivation: Lambertian radiance gives dH = cos_i cos_j dAi dAj /
(pi r^2). Integrate each triangle by equal-area midpoint subdivision and one
centroid per child. Compute H_ij once; dividing by each area makes reciprocity
algebraic. Visibility is segment/triangle plane intersection with barycentric
containment. All coarser levels are retained as change indicators, NEVER an
error bound (especially for discontinuous shadows). No row renormalization.

Reference geometry/oracle: Howell's catalog C-11, identical opposed rectangles,
https://www.thermalradiation.net/sectionc/C-11.html . The test independently
integrates the square separation kernel using its analytical antiderivative.
Original implementation and fixtures; no external source/code/data adapted.
Only opaque diffuse planar patches in a nonparticipating medium. No emissivity,
radiosity, specular reflection, airflow, temperatures or ambient sink is inferred.
Near contacts, intersecting geometry, slivers and resource excess fail closed.
Knowledgeable human numerical review remains required before release.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math

import numpy as np


class AssemblyViewFactorError(ValueError):
    """Malformed, unresolved or over-budget view-factor problem."""


def _require(condition, message):
    if not condition:
        raise AssemblyViewFactorError(message)


def _keys(value, required, optional=()):
    _require(isinstance(value, dict) and set(required) <= set(value)
             and set(value) <= set(required) | set(optional), "Unexpected contract fields.")


def _triangle(raw):
    _require(isinstance(raw, list) and len(raw) == 3, "Expected triangle XYZ vertices.")
    for point in raw:
        _require(isinstance(point, list) and len(point) == 3, "Expected three coordinates.")
        for value in point:
            _require(type(value) in (int, float) and abs(value) <= 1e12
                     and math.isfinite(value), "Coordinates must be finite SI numbers, not bool.")
    return np.asarray(raw, dtype=float)


def _inside(point, triangle, tolerance=1e-10):
    a, b, c = triangle
    v, w, p = b-a, c-a, point-a
    normal = np.cross(v, w)
    denominator = normal@normal
    u = np.cross(p, w)@normal/denominator
    t = np.cross(v, p)@normal/denominator
    return u >= -tolerance and t >= -tolerance and u+t <= 1+tolerance


def _segment_distance(a, b, c, d):
    # Minimize ||a+s(b-a)-c-t(d-c)|| on the unit square. The convex quadratic
    # minimum is either its stationary point or an edge minimum.
    u, v, w = b-a, d-c, a-c
    uu, uv, vv = u@u, u@v, v@v
    candidates = [(0., np.clip(w@v/vv, 0, 1)),
                  (1., np.clip((w+u)@v/vv, 0, 1)),
                  (np.clip(-w@u/uu, 0, 1), 0.),
                  (np.clip((v-w)@u/uu, 0, 1), 1.)]
    det = uu*vv-uv*uv
    if det > 1e-14*uu*vv:
        s = (uv*(w@v)-vv*(w@u))/det
        t = (uu*(w@v)-uv*(w@u))/det
        if 0 <= s <= 1 and 0 <= t <= 1:
            candidates.append((s, t))
    return min(float(np.linalg.norm(w+s*u-t*v)) for s, t in candidates)


def _distance(a, b):
    distances = []
    for source, target in ((a, b), (b, a)):
        normal = np.cross(target[1]-target[0], target[2]-target[0])
        normal /= np.linalg.norm(normal)
        signed = (source-target[0])@normal
        for point, height in zip(source, signed):
            if _inside(point-height*normal, target):
                distances.append(abs(float(height)))
        for i, j in ((0, 1), (1, 2), (2, 0)):
            if signed[i]*signed[j] < 0:
                fraction = signed[i]/(signed[i]-signed[j])
                if _inside(source[i]+fraction*(source[j]-source[i]), target):
                    return 0.
    for i, j in ((0, 1), (1, 2), (2, 0)):
        for k, l in ((0, 1), (1, 2), (2, 0)):
            distances.append(_segment_distance(a[i], a[j], b[k], b[l]))
    return min(distances)


def _coplanar_overlap(a, b, normal):
    # Convex half-plane clipping, used solely to reject duplicate/overlapping
    # triangles while admitting shared triangulation edges on the same patch.
    axis = int(np.argmax(abs(normal)))
    polygon = [np.delete(p, axis) for p in a]
    clip = np.delete(b, axis, axis=1)
    cross = lambda p, q: p[0]*q[1]-p[1]*q[0]
    sign = 1 if cross(clip[1]-clip[0], clip[2]-clip[0]) > 0 else -1
    for start, end in zip(clip, np.roll(clip, -1, axis=0)):
        previous = polygon
        polygon = []
        if not previous:
            return 0.
        for p, q in zip(previous, previous[1:]+previous[:1]):
            dp, dq = sign*cross(end-start, p-start), sign*cross(end-start, q-start)
            if dp >= 0:
                polygon.append(p)
            if (dp >= 0) != (dq >= 0):
                polygon.append(p+(q-p)*dp/(dp-dq))
    if len(polygon) < 3:
        return 0.
    return abs(sum(cross(p, q) for p, q in zip(polygon, polygon[1:]+polygon[:1])))/2


def _subdivide(triangles):
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, bc, ca = (a+b)/2, (b+c)/2, (c+a)/2
    return np.concatenate([np.stack(vertices, axis=1)
                           for vertices in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca))])


def _blocked(origins, directions, triangle):
    a, b, c = triangle
    normal = np.cross(b-a, c-a)
    denominator = directions@normal
    usable = abs(denominator) > 1e-13*np.linalg.norm(normal)*np.linalg.norm(directions, axis=1)
    fraction = np.divide((a-origins)@normal, denominator,
                         out=np.zeros(len(origins)), where=usable)
    points = origins+fraction[:, None]*directions
    v, w, p = b-a, c-a, points-a
    u = np.cross(p, w)@normal/(normal@normal)
    t = np.cross(v, p)@normal/(normal@normal)
    return usable & (fraction > 1e-10) & (fraction < 1-1e-10) & (u >= -1e-10) & (t >= -1e-10) & (u+t <= 1+1e-10)


def _exchange(left, right, normal_a, normal_b, blockers):
    centers_a, centers_b = left.mean(axis=1), right.mean(axis=1)
    areas_a = np.linalg.norm(np.cross(left[:, 1]-left[:, 0], left[:, 2]-left[:, 0]), axis=1)/2
    areas_b = np.linalg.norm(np.cross(right[:, 1]-right[:, 0], right[:, 2]-right[:, 0]), axis=1)/2
    pieces = []
    # At most 8192 rays in memory regardless of user mesh subdivision.
    chunk = max(1, 8192//len(right))
    for start in range(0, len(left), chunk):
        origin = np.repeat(centers_a[start:start+chunk], len(right), axis=0)
        delta = np.tile(centers_b, (len(origin)//len(right), 1))-origin
        r2 = np.sum(delta*delta, axis=1)
        weights = (areas_a[start:start+chunk, None]*areas_b[None, :]).ravel()
        kernel = np.maximum(delta@normal_a, 0)*np.maximum(-delta@normal_b, 0)/(math.pi*r2*r2)
        visible = kernel > 0
        for blocker in blockers:
            visible &= ~_blocked(origin, delta, blocker)
        pieces.append(float(np.sum(weights*kernel*visible)))
    return math.fsum(pieces)


def derive_assembly_view_factors(request):
    """Return reciprocal estimates and unresolved fractions, or fail closed.

    Limits: 2..32 planar surfaces, <=256 total input triangles, level 0..5,
    <=8192 refined triangles per surface,
    10 million quadrature pairs / 50 million visibility tests / 32768 geometry
    pairs. Coarse leaf diameter must be <=4 times geometry clearance at the
    requested level. This is an admission heuristic, not accuracy certification.
    """
    _keys(request, ('contract', 'units', 'surfaces', 'quadrature'), ('occluders',))
    _require(request['contract'] == 'spike/assembly-view-factor-request/v1'
             and request['units'] == 'm', 'Expected view-factor request in SI metres.')
    policy = request['quadrature']
    ceilings = {'level': 5, 'max_pair_evaluations': 10_000_000,
                'max_visibility_tests': 50_000_000, 'max_geometry_pairs': 32768}
    _keys(policy, ceilings)
    for key, ceiling in ceilings.items():
        _require(type(policy[key]) is int and (0 if key == 'level' else 1) <= policy[key] <= ceiling,
                 f'Invalid quadrature resource {key}.')
    surfaces, occluders = request['surfaces'], request.get('occluders', [])
    _require(isinstance(surfaces, list) and 2 <= len(surfaces) <= 32, 'Expected 2..32 surfaces.')
    _require(isinstance(occluders, list) and len(occluders) <= 256, 'Invalid occluder budget.')
    ids, groups = [], []
    for surface in surfaces:
        _keys(surface, ('id', 'triangles'))
        identity, triangles = surface['id'], surface['triangles']
        _require(isinstance(identity, str) and identity.strip() and len(identity) <= 128 and identity not in ids,
                 'Invalid or duplicate surface ID.')
        _require(isinstance(triangles, list) and 1 <= len(triangles) <= 256, 'Invalid triangle budget.')
        ids.append(identity)
        groups.append([_triangle(t) for t in triangles])
    groups.append([_triangle(t) for t in occluders])
    total = sum(map(len, groups))
    _require(total <= 256, 'Total triangle budget exceeded.')
    _require(total*(total-1)//2 <= policy['max_geometry_pairs'], 'Geometry pair budget exceeded.')
    flat = np.asarray([t for group in groups for t in group])
    lower, upper = flat.min(axis=(0, 1)), flat.max(axis=(0, 1))
    scale = float(np.linalg.norm(upper-lower))
    _require(1e-9 <= scale <= 1e9 and np.max(abs(flat))*np.finfo(float).eps < scale*1e-10,
             'Unresolved geometry scale/translation conditioning.')
    groups = [np.asarray([(t-lower)/scale for t in group]) for group in groups]
    flat = [(owner, t) for owner, group in enumerate(groups) for t in group]
    normals, areas, longest = [], [], []
    for owner, group in enumerate(groups):
        if not len(group):
            continue
        crosses = np.cross(group[:, 1]-group[:, 0], group[:, 2]-group[:, 0])
        lengths = np.linalg.norm(crosses, axis=1)
        edges = np.linalg.norm(group-np.roll(group, -1, axis=1), axis=2)
        _require(np.all(lengths > 1e-10*np.max(edges, axis=1)**2)
                 and np.all(lengths > 1e-20), 'Degenerate or unresolved sliver triangle.')
        if owner < len(surfaces):
            normal = crosses[0]/lengths[0]
            _require(np.all((crosses/lengths[:, None])@normal > 1-1e-10)
                     and np.max(abs((group-group[0, 0])@normal)) < 1e-10,
                     'Each surface must be planar and consistently oriented.')
            normals.append(normal)
            areas.append(float(lengths.sum()/2))
            longest.append(float(edges.max()))
    clearance = np.full((len(surfaces), len(surfaces)), np.inf)
    for (owner_a, a), (owner_b, b) in itertools.combinations(flat, 2):
        normal = np.cross(a[1]-a[0], a[2]-a[0])
        normal /= np.linalg.norm(normal)
        coplanar = np.max(abs((b-a[0])@normal)) < 1e-10
        if owner_a == owner_b and coplanar:
            projected_area = min(np.linalg.norm(np.cross(t[1]-t[0], t[2]-t[0]))/2
                                 for t in (a, b))*max(abs(normal))
            _require(_coplanar_overlap(a, b, normal) < projected_area*1e-10,
                     'Overlapping triangles within a surface/occluder mesh.')
            continue
        distance = _distance(a, b)
        _require(distance > 1e-9, 'Intersecting, contacting or unresolved near-contact geometry.')
        if owner_a < len(surfaces) and owner_b < len(surfaces):
            clearance[owner_a, owner_b] = min(clearance[owner_a, owner_b], distance)
    level = policy['level']
    _require(all(len(group)*4**level <= 8192 for group in groups[:-1]),
             'Refined surface triangle memory budget exceeded.')
    pair_work = sum(len(groups[i])*len(groups[j]) for i, j in itertools.combinations(range(len(surfaces)), 2))
    multiplier = sum(16**k for k in range(level+1))
    visibility_work = sum(len(groups[i])*len(groups[j])*(total-len(groups[i])-len(groups[j]))
                          for i, j in itertools.combinations(range(len(surfaces)), 2))*multiplier
    _require(pair_work*multiplier <= policy['max_pair_evaluations'], 'Quadrature pair budget exceeded.')
    _require(visibility_work <= policy['max_visibility_tests'], 'Visibility test budget exceeded.')
    for i, j in itertools.combinations(range(len(surfaces)), 2):
        _require(max(longest[i], longest[j])/2**level <= 4*clearance[i, j],
                 'Near-surface quadrature unresolved; refine geometry/quadrature.')
    history, previous = [], None
    for refinement in range(level+1):
        exchange = np.zeros((len(surfaces), len(surfaces)))
        for i, j in itertools.combinations(range(len(surfaces)), 2):
            blockers = [t for owner, t in flat if owner not in (i, j)]
            exchange[i, j] = exchange[j, i] = _exchange(groups[i], groups[j], normals[i], normals[j], blockers)
        factors = exchange/np.asarray(areas)[:, None]
        _require(np.isfinite(factors).all(), 'Nonfinite view-factor integration.')
        change = None if previous is None else float(np.max(abs(factors-previous)))
        history.append({'level': refinement, 'view_factors': factors.tolist(),
                        'max_absolute_change': change})
        previous = factors
        if refinement < level:
            groups = [_subdivide(group) if i < len(surfaces) else group for i, group in enumerate(groups)]
    row_sums = factors.sum(axis=1)
    _require(np.all(row_sums <= 1), 'View-factor row exceeds one; no renormalization permitted.')
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return {'contract': 'spike/assembly-view-factor-result/v1', 'status': 'experimental',
            'production_qualified': False, 'input_digest_sha256': digest, 'units': 'm',
            'surface_ids': ids, 'areas_m2': (np.asarray(areas)*scale**2).tolist(),
            'view_factors': factors.tolist(), 'exchange_areas_m2': (exchange*scale**2).tolist(),
            'unresolved_view_fractions': (1-row_sums).tolist(), 'unresolved_status': 'UNRESOLVED',
            'ambient_view_factors_inferred': False, 'quadrature_history': history,
            'error_bound': None, 'estimated_pair_evaluations': pair_work*multiplier,
            'estimated_visibility_tests': visibility_work,
            'admission': {'scene_span_m': scale, 'contact_tolerance_m': scale*1e-9,
                          'maximum_leaf_edge_over_clearance': 4.,
                          'maximum_refined_triangles_per_surface': 8192},
            'limitations': ['Planar diffuse opaque patches only; no thermal/radiosity solve.',
                            'Refinement changes are indicators, not guaranteed errors; shadows may alias.',
                            'Unresolved view includes unmodelled surroundings and nonemitting blockers; not ambient.']}
