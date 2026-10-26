# SPDX-License-Identifier: Apache-2.0
"""Preserve original planar source interfaces across tolerant CAD booleans.

OCC can close a small real gap while fragmenting. A shared mesh face alone is
therefore not evidence that the original retained surfaces touched. Admit it
only if its points remain on original planar boundaries of both source owners.
"""
import math
import numpy as np

MAX_INTERFACE_ROUNDOFF_MM = 1e-10


def source_world_transform(solid):
    world = np.asarray(solid['transform'], dtype=float).reshape(4, 4)
    if solid['shape']['kind'] == 'step_solid':
        world = world @ np.asarray(solid['shape']['transform'], dtype=float).reshape(4, 4)
    return world


def _convex_face_edges(gmsh, tag, center, normal):
    """Prove a single finite convex polygon from the original straight edges.

Each edge must support all other vertices on one side; holes and concavities
therefore cannot pass. A connected degree-two boundary rules out loose wires.
"""
    edges, vertices, neighbours = [], {}, {}
    curves = gmsh.model.getBoundary([(2, tag)], combined=False, oriented=False)
    if not 3 <= len(curves) <= 2048:
        return []
    for dim, curve in curves:
        if dim != 1 or gmsh.model.getType(dim, curve).lower() != 'line':
            return []
        endpoints = gmsh.model.getBoundary([(1, curve)], combined=False, oriented=False)
        if len(endpoints) != 2:
            return []
        ids = [vertex for dimension, vertex in endpoints if dimension == 0]
        if len(ids) != 2 or ids[0] == ids[1]:
            return []
        for vertex in ids:
            vertices[vertex] = np.asarray(gmsh.model.getValue(0, vertex, []), dtype=float)
        a, b = ids
        neighbours.setdefault(a, set()).add(b)
        neighbours.setdefault(b, set()).add(a)
        edges.append((a, b))
    if any(len(n) != 2 for n in neighbours.values()):
        return []
    reached, pending = set(), [next(iter(vertices))]
    while pending:
        vertex = pending.pop()
        if vertex not in reached:
            reached.add(vertex)
            pending.extend(neighbours[vertex]-reached)
    if len(reached) != len(vertices):
        return []
    xyz = np.asarray(list(vertices.values()))
    tolerance = 64*np.finfo(float).eps*max(1., float(np.max(np.abs(xyz))))
    if tolerance > MAX_INTERFACE_ROUNDOFF_MM or np.max(np.abs((xyz-center) @ normal)) > tolerance:
        return []
    admitted = []
    for a, b in edges:
        start, end = vertices[a], vertices[b]
        inward = np.cross(normal, end-start)
        length = float(np.linalg.norm(inward))
        if length <= tolerance:
            return []
        inward /= length
        side = (xyz-start) @ inward
        if np.max(side) <= tolerance:
            inward = -inward
            side = -side
        if np.min(side) < -tolerance or np.max(side) <= tolerance:
            return []
        admitted.append((start, inward))
    return admitted


def capture_joint_source_boundaries(gmsh, solids, entities):
    """Capture original CAD planes before fragmentation can replace surfaces."""
    gmsh.model.occ.synchronize()
    captured, owners, count = {}, {}, 0
    for solid, entity in zip(solids, entities):
        sid = solid['id']
        owners[sid] = solid['occurrence_id']
        transform = source_world_transform(solid)
        rotation, translation = transform[:3, :3], transform[:3, 3]
        planes = []
        for dim, tag in gmsh.model.getBoundary([entity], combined=False, oriented=False):
            if dim != 2:
                continue
            count += 1
            if count > 8192:
                raise ValueError('ASSEMBLY_JOINT_INTERFACE_BUDGET: original CAD boundary budget exceeded')
            if gmsh.model.getType(2, tag).lower() != 'plane':
                continue
            center = np.asarray(gmsh.model.occ.getCenterOfMass(2, tag), dtype=float)
            uv = gmsh.model.getParametrization(2, tag, center.tolist())
            normal = np.asarray(gmsh.model.getNormal(tag, uv), dtype=float)
            norm = float(np.linalg.norm(normal))
            if (center.shape != (3,) or normal.shape != (3,) or
                    not np.isfinite(center).all() or not np.isfinite(normal).all() or
                    not math.isfinite(norm) or norm <= 0):
                raise ValueError('ASSEMBLY_JOINT_INTERFACE_SOURCE: invalid original CAD plane')
            normal /= norm
            edges = _convex_face_edges(gmsh, tag, center, normal)
            if edges:
                planes.append((rotation @ center + translation, rotation @ normal,
                               [(rotation @ start + translation, rotation @ inward) for start, inward in edges]))
        captured[sid] = planes
    return captured, owners


def verify_joint_source_interfaces(source_geometry, interfaces, points):
    """Reject CAD-created gap closure and unverified nonplanar interfaces.

Roundoff allowance is 64 machine epsilons times the local coordinate scale,
capped at 1e-10 mm (ten times stricter than 1e-12 m contact coincidence).
If a coordinate scale cannot support that cap, interface admission fails.
This is representation roundoff, not a permission to close physical gaps.
"""
    planes, owners = source_geometry
    checked, maximum_error, maximum_tolerance = 0, 0., 0.
    for face in interfaces:
        by_owner = {}
        for sid in face['source_object_ids']:
            by_owner.setdefault(owners[sid], []).extend(planes[sid])
        if len(by_owner) < 2:
            continue
        if len(by_owner) != 2:
            raise ValueError('ASSEMBLY_JOINT_INTERFACE_SOURCE: ambiguous original interface owners')
        xyz = np.asarray([points[i] for i in face['vertices']])
        normal = np.cross(xyz[1]-xyz[0], xyz[2]-xyz[0])
        norm = float(np.linalg.norm(normal))
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError('ASSEMBLY_JOINT_INTERFACE_SOURCE: degenerate shared triangle')
        normal /= norm
        for candidates in by_owner.values():
            accepted = []
            for center, source_normal, edges in candidates:
                if abs(float(normal @ source_normal)) < 1-1e-10:
                    continue
                scale = max(1., float(np.max(np.abs(center))), float(np.max(np.abs(xyz))))
                tolerance = 64*np.finfo(float).eps*scale
                if tolerance > MAX_INTERFACE_ROUNDOFF_MM:
                    continue
                if any(np.min((xyz-start) @ inward) < -tolerance for start, inward in edges):
                    continue
                error = float(np.max(np.abs((xyz-center) @ source_normal)))
                if error <= tolerance:
                    accepted.append((error, tolerance))
            if not accepted:
                raise ValueError('ASSEMBLY_JOINT_SOURCE_SEPARATION: shared mesh face was not on both original planar CAD boundaries; '
                                 'possible tolerance-closed gap, unsupported nonconvex/nonplanar contact or insufficient coordinate precision')
            error, tolerance = min(accepted)
            maximum_error = max(maximum_error, error)
            maximum_tolerance = max(maximum_tolerance, tolerance)
        checked += 1
    return {'method': 'original_convex_planar_face_projection', 'checked_interface_triangles': checked,
            'maximum_projection_error_mm': maximum_error, 'maximum_roundoff_allowance_mm': maximum_tolerance,
            'absolute_roundoff_cap_mm': MAX_INTERFACE_ROUNDOFF_MM}
