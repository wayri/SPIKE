# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Closed material surfaces and explicit ports from an admitted EM volume.

Clean-room implementation: face cancellation follows tetrahedral incidence;
orientation follows the signed scalar triple product. The divergence theorem
provides the independent surface-volume oracle in the tests. CSXCAD's public
API is documented at https://docs.openems.de/en/latest/python/CSXCAD/
CSPrimitives/CSPrimPolyhedron.html . No external implementation was used.

This preserves the supplied piecewise planar solid, including cavities. It
neither extracts PCB copper nor certifies the supplied mesh against source CAD.
All coordinates, including those emitted to CSXCAD, are metres.
"""
from __future__ import annotations

import copy
import itertools
import math
from collections import defaultdict

from python.spike_core.assembly_field_handoff import bounded_json, field_resource_limits
from python.spike_core.multiboard_identity import canonical_json_digest

CONTRACT = 'spike/openems-retained-volume-geometry/v1'
MAX_SURFACE_FACES = 300_000


def _require(condition, detail):
    if not condition:
        raise ValueError('OPENEMS_RETAINED_GEOMETRY: ' + detail)


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _point(raw):
    _require(isinstance(raw, list) and len(raw) == 3 and
             all(type(x) in (int, float) and math.isfinite(x) for x in raw),
             'finite three-coordinate point required')
    return [float(x) for x in raw]


def _inside_triangle(point, triangle):
    """Scale-relative plane/barycentric checks, never a mesh-cell tolerance."""
    a, b, c = triangle
    u, v, w = _sub(b, a), _sub(c, a), _sub(point, a)
    normal = _cross(u, v)
    norm = math.sqrt(_dot(normal, normal))
    scale = max(math.sqrt(_dot(u, u)), math.sqrt(_dot(v, v)))
    _require(norm > 0 and scale > 0, 'degenerate terminal triangle')
    # Include coordinate roundoff but reject geometries whose precision is lost.
    roundoff = 32 * max(math.ulp(float(x)) for p in triangle for x in p)
    tolerance = max(scale * 1e-10, roundoff)
    _require(tolerance <= scale * 1e-7, 'terminal coordinates lack precision')
    if abs(_dot(w, normal)) > norm * tolerance:
        return False
    # Cross-product barycentrics avoid subtracting nearly equal Gram products.
    s = _dot(_cross(w, v), normal) / (norm * norm)
    t = _dot(_cross(u, w), normal) / (norm * norm)
    eps = tolerance * scale / norm
    _require(eps <= 1e-6, 'terminal triangle is ill-conditioned')
    return s >= -eps and t >= -eps and s + t <= 1 + eps


def _tetra_intersects_open_box(tetra, lower, upper):
    """Separating-axis test including degenerate line/plane port boxes.

    Coordinates are shifted to the port center. Terminal-plane-only cells
    are excluded by the caller. Other contacts conservatively count, including
    lines lying exactly on internal tetrahedral interfaces.
    Tetrahedron face normals, box normals and edge cross-products form the
    complete SAT axis set for these two convex polytopes.
    """
    center = [(a + b) / 2 for a, b in zip(lower, upper)]
    half = [(b - a) / 2 for a, b in zip(lower, upper)]
    points = [_sub(p, center) for p in tetra]
    box_axes = [[1.,0.,0.], [0.,1.,0.], [0.,0.,1.]]
    axes = list(box_axes)
    for a, b, c in itertools.combinations(range(4), 3):
        axes.append(_cross(_sub(points[b], points[a]), _sub(points[c], points[a])))
    for a, b in itertools.combinations(range(4), 2):
        edge = _sub(points[b], points[a])
        axes.extend(_cross(edge, axis) for axis in box_axes)
    for axis in axes:
        length = math.sqrt(_dot(axis, axis))
        if length == 0:
            continue
        axis = [v / length for v in axis]
        projected = [_dot(p, axis) for p in points]
        radius = sum(abs(v) * h for v, h in zip(axis, half))
        tolerance = 64 * math.ulp(max(abs(v) for v in projected + [radius]))
        if max(projected) < -radius - tolerance or min(projected) > radius + tolerance:
            return False
    return True


def _reject_intervening_conductors(handoff, ports):
    mesh = handoff['mesh']
    properties = {m['id']: m for m in handoff['materials']}
    conductors = []
    for cell in mesh['cells']:
        if properties[cell['material_id']]['conductivity_s_m'] > 0:
            tetra = [mesh['vertices'][i] for i in cell['vertices']]
            conductors.append((tetra, [min(p[i] for p in tetra) for i in range(3)],
                               [max(p[i] for p in tetra) for i in range(3)]))
    checks = 0
    for port in ports:
        lower = [min(a, b) for a, b in zip(port['start_m'], port['stop_m'])]
        upper = [max(a, b) for a, b in zip(port['start_m'], port['stop_m'])]
        axis = 'xyz'.index(port['direction'])
        for tetra, minimum, maximum in conductors:
            # Exclude only excitation-axis endpoint contact. Degenerate
            # transverse dimensions still need an interior intersection test.
            tolerance = 64 * math.ulp(max(abs(lower[axis]), abs(upper[axis])))
            if (maximum[axis] <= lower[axis] + tolerance or
                    minimum[axis] >= upper[axis] - tolerance or
                    any(maximum[i] < lower[i] or minimum[i] > upper[i] for i in range(3))):
                continue
            checks += 1
            _require(checks <= 100_000, 'port intersection work budget exceeded')
            _require(not _tetra_intersects_open_box(tetra, lower, upper),
                     'port interior intersects a conductor volume')


def _compile_ports(handoff, ports, exterior_conductors):
    expected = {p['id']: p for p in handoff['ports']}
    _require(isinstance(ports, list) and 1 <= len(ports) <= 64 and
             len(ports) == len(expected), 'one explicit definition per retained port required')
    faces = {f['id']: f for f in handoff['boundary_faces']}
    vertices = handoff['mesh']['vertices']
    result, seen = [], set()
    for port in ports:
        _require(isinstance(port, dict) and set(port) ==
                 {'id', 'start_m', 'stop_m', 'direction', 'excite'}, 'invalid port fields')
        pid = port['id']
        _require(isinstance(pid, str) and pid in expected and pid not in seen, 'unknown or duplicate port')
        seen.add(pid)
        start, stop = _point(port['start_m']), _point(port['stop_m'])
        direction = port['direction']
        _require(isinstance(direction, str) and direction in ('x', 'y', 'z') and
                 type(port['excite']) is bool, 'invalid port direction/excitation')
        axis = 'xyz'.index(direction)
        _require(start[axis] != stop[axis], 'port excitation span must be nonzero')
        retained = expected[pid]
        reference = retained['reference_impedance_ohm']
        _require(type(reference) in (int, float) and math.isfinite(reference) and
                 0 < reference <= 1e6, 'invalid port reference impedance')
        terminal_ids = [retained['return_face_id'], retained['signal_face_id']]
        _require(terminal_ids[0] != terminal_ids[1], 'signal and return must differ')
        transverse = [i for i in range(3) if i != axis]
        for endpoint, face_id in zip((start, stop), terminal_ids):
            _require(face_id in faces and face_id in exterior_conductors,
                     'port requires an exterior conductor face')
            face = faces[face_id]
            triangle = [vertices[i] for i in face['vertices']]
            for values in itertools.product(*[(start[i], stop[i]) for i in transverse]):
                corner = list(endpoint)
                for i, value in zip(transverse, values):
                    corner[i] = value
                _require(_inside_triangle(corner, triangle),
                         'all port terminal corners must lie on the declared conductor triangle')
        result.append({**copy.deepcopy(port), 'reference_impedance_ohm': float(reference),
                       'return_face_id': terminal_ids[0], 'signal_face_id': terminal_ids[1],
                       'terminal_convention': 'start_return_stop_signal'})
    _require(sum(p['excite'] for p in result) == 1, 'exactly one excited port required')
    return result


def compile_retained_volume_geometry(handoff, ports):
    """Compile freshly admitted EM handoff; digests detect accidental mutation.

    The caller must regenerate the handoff from the retained request. A digest
    is not authentication and this compiler is not a replacement mesh validator.
    Only same-material, same-occurrence shared faces are cancelled. Connected
    material regions become separate closed polyhedra, avoiding implicit unions.
    """
    bounded_json(handoff,max_bytes=field_resource_limits(handoff)['max_control_bytes'])
    _require(isinstance(handoff, dict) and handoff.get('contract') ==
             'spike/assembly-field-handoff/v1' and handoff.get('domain') == 'em',
             'admitted EM handoff required')
    unsigned = {k: v for k, v in handoff.items() if k != 'handoff_digest'}
    _require(canonical_json_digest(unsigned) == handoff.get('handoff_digest'), 'stale handoff digest')
    mesh = handoff['mesh']
    _require(mesh['units'] == 'm' and canonical_json_digest(mesh) == handoff['mesh_digest'],
             'stale mesh digest or non-SI mesh')
    _require(all(i.get('code') == 'ASSEMBLY_FIELD_BACKEND_UNAVAILABLE'
                 for i in handoff['execution_issues']), 'unsupported assembly connectivity')
    points, cells = mesh['vertices'], mesh['cells']
    materials = {m['id']: m for m in handoff['materials']}
    owners = {}
    for trace in handoff['source_traceability']:
        for cid in trace['cell_map'].values():
            _require(cid not in owners, 'ambiguous cell ownership')
            owners[cid] = trace['occurrence_id']
    parent = list(range(len(cells)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    incidences = defaultdict(list)
    groups = []
    for index, cell in enumerate(cells):
        _require(cell['id'] in owners and cell['material_id'] in materials,
                 'cell ownership/material missing')
        groups.append((owners[cell['id']], cell['material_id']))
        indices = cell['vertices']
        for omitted in range(4):
            face = [indices[j] for j in range(4) if j != omitted]
            a, b, c = [points[i] for i in face]
            side = _dot(_cross(_sub(b, a), _sub(c, a)), _sub(points[indices[omitted]], a))
            _require(math.isfinite(side) and side != 0, 'degenerate tetrahedral face')
            if side > 0:
                face[1], face[2] = face[2], face[1]
            key = tuple(sorted(face))
            incidences[key].append((index, face))
            _require(len(incidences[key]) <= 2, 'nonmanifold tetrahedral incidence')
    surface = []
    for records in incidences.values():
        if len(records) == 2 and groups[records[0][0]] == groups[records[1][0]]:
            left, right = root(records[0][0]), root(records[1][0])
            parent[right] = left
        else:
            surface.extend(records)
    surface_budget = 600_000 if handoff.get('resource_profile') == 'routed_pcb_em_v1' else MAX_SURFACE_FACES
    _require(len(surface) <= surface_budget, 'surface face budget exceeded')
    component_faces, component_cells = defaultdict(list), defaultdict(list)
    for index, face in surface:
        component_faces[root(index)].append(face)
    for index in range(len(cells)):
        component_cells[root(index)].append(index)
    primitives = []
    for component, faces in sorted(component_faces.items()):
        owner, material_id = groups[component]
        selected = sorted({i for face in faces for i in face})
        remap = {old: new for new, old in enumerate(selected)}
        edge_counts = defaultdict(list)
        for face in faces:
            for a, b in zip(face, face[1:] + face[:1]):
                edge_counts[tuple(sorted((a, b)))].append((a, b))
        _require(all(len(e) == 2 and e[0] == e[1][::-1] for e in edge_counts.values()),
                 'material surface is not a closed oriented manifold')
        members = [cells[i] for i in component_cells[component]]
        primitives.append({'occurrence_id': owner, 'material_id': material_id,
                           'material': copy.deepcopy(materials[material_id]),
                           'vertices_m': [list(points[i]) for i in selected],
                           'faces': [[remap[i] for i in face] for face in faces],
                           'cell_ids': [c['id'] for c in members],
                           'source_object_ids': sorted({s for c in members for s in c['source_object_ids']})})
    conductive_faces = set()
    for face in handoff['boundary_faces']:
        records = incidences.get(tuple(sorted(face['vertices'])), [])
        if len(records) == 1:
            cell = cells[records[0][0]]
            if (owners[cell['id']] == face['occurrence_id'] and
                    materials[cell['material_id']]['conductivity_s_m'] > 0):
                conductive_faces.add(face['id'])
    compiled_ports = _compile_ports(handoff, ports, conductive_faces)
    _reject_intervening_conductors(handoff, compiled_ports)
    result = {'contract': CONTRACT, 'units': 'm', 'primitives': primitives,
              'ports': compiled_ports, 'surface_face_count': len(surface),
              'bounds_m': {'start': [min(p[i] for p in points) for i in range(3)],
                           'stop': [max(p[i] for p in points) for i in range(3)]},
              'handoff_digest': handoff['handoff_digest'], 'mesh_digest': handoff['mesh_digest'],
              'request_digest': handoff['request_digest'], 'assembly_digest': handoff['assembly_digest'],
              'source_traceability': copy.deepcopy(handoff['source_traceability']),
              'production_qualified': False,
              'limitations': ['Supplied conductor-resolved volume only; no PCB/STEP extraction.',
                              'Axis-aligned lumped ports; no eigenmode or connector inference.',
                              'Exact supplied polyhedra; FDTD rasterization requires convergence.']}
    result['compiled_digest'] = canonical_json_digest(result)
    return result


def emit_retained_volume_geometry(csx, compiled):
    """Emit compiled polyhedra in metres into a new CSXCAD structure.

    Caller must use grid.SetDeltaUnit(1.0). Admission precedes all mutations;
    a native API failure still requires discarding the partially built structure.
    """
    # Standalone by design: the trusted isolated driver embeds this function.
    import hashlib
    import json

    def canonical(value):
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [canonical(item) for item in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    if (not isinstance(compiled, dict) or
            compiled.get('contract') != 'spike/openems-retained-volume-geometry/v1' or
            compiled.get('units') != 'm'):
        raise ValueError('OPENEMS_RETAINED_GEOMETRY: compiled geometry contract required')
    unsigned = {k: v for k, v in compiled.items() if k != 'compiled_digest'}
    digest = hashlib.sha256(json.dumps(canonical(unsigned), sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if digest != compiled.get('compiled_digest'):
        raise ValueError('OPENEMS_RETAINED_GEOMETRY: stale compiled geometry')
    for index, primitive in enumerate(compiled['primitives']):
        props = primitive['material']
        material = csx.AddMaterial('spike_retained_' + str(index),
                                   epsilon=props['relative_permittivity'],
                                   mue=props['relative_permeability'],
                                   kappa=props['conductivity_s_m'])
        polyhedron = material.AddPolyhedron(priority=10 if props['conductivity_s_m'] > 0 else 0)
        for vertex in primitive['vertices_m']:
            polyhedron.AddVertex(*vertex)
        for face in primitive['faces']:
            polyhedron.AddFace(face)
    return compiled
