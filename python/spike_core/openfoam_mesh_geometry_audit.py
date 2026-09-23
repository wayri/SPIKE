# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Geometric diagnostic for imported convex linear FV cells, not qualification.

Computes volume centroids and face nonorthogonality; detects nonplanar/concave
cells. Does not establish global intersection freedom or CFD convergence.
"""
import math
import re
from pathlib import Path
import numpy as np


def audit_polymesh_geometry(path):
    """Read bounded ASCII polyMesh arrays after caller's digest admission."""
    root = Path(path)
    def body(name):
        target = root/name
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 32*1024**2:
            raise ValueError('Missing or oversized geometry array')
        text = target.read_text(encoding='utf-8')
        if 'format ascii;' not in text:
            raise ValueError('Geometry audit requires ASCII arrays')
        match = re.search(r'\n(\d+)\s*\(\s*([\s\S]*)\)\s*$',text)
        if not match:
            raise ValueError('Malformed geometry array')
        return int(match[1]), match[2]
    count, text = body('points')
    points = [list(map(float,p.split())) for p in re.findall(r'\(([^()]*)\)',text)]
    if count != len(points): raise ValueError('Point count mismatch')
    count, text = body('faces')
    faces = []
    for n, value in re.findall(r'(\d+)\s*\(([^()]*)\)',text):
        face = list(map(int,value.split()))
        if len(face) != int(n): raise ValueError('Face count mismatch')
        faces.append(face)
    if count != len(faces): raise ValueError('Face count mismatch')
    labels = []
    for name in ('owner','neighbour'):
        count, text = body(name)
        values = list(map(int,text.split()))
        if len(values) != count: raise ValueError('Addressing count mismatch')
        labels.append(values)
    owner, neighbour = labels
    if len(owner) != len(faces) or len(neighbour) > len(faces): raise ValueError('Addressing mismatch')
    members = {}
    for index, face in enumerate(faces):
        for cell in [owner[index]] + ([neighbour[index]] if index < len(neighbour) else []):
            if cell < 0 or cell >= 100000: raise ValueError('Cell budget exceeded')
            members.setdefault(cell,[]).append(face)
    if set(members) != set(range(len(members))): raise ValueError('Noncontiguous cell addressing')
    cells = []
    for _, local_faces in sorted(members.items()):
        vertices = set(i for face in local_faces for i in face)
        if len(local_faces) == 4 and len(vertices) == 4 and all(len(face)==3 for face in local_faces):
            ids = local_faces[0] + list(vertices-set(local_faces[0]))
            kind = 'tetrahedron'
        elif len(local_faces)==6 and len(vertices)==8 and all(len(face)==4 for face in local_faces):
            base = local_faces[0]
            adjacency = {v:set() for v in vertices}
            for face in local_faces:
                for a,b in zip(face,face[1:]+face[:1]):
                    adjacency[a].add(b); adjacency[b].add(a)
            opposite = [adjacency[v]-set(base) for v in base]
            if any(len(values)!=1 for values in opposite): raise ValueError('Invalid hex topology')
            ids = base+[next(iter(values)) for values in opposite]
            kind = 'hexahedron'
        else: raise ValueError('Unsupported polyhedral cell topology')
        cells.append({'kind':kind,'vertices':ids})
    return audit_mesh_geometry({'contract':'spike/solver-mesh/v1','units':'m',
                               'coordinate_system':'right_handed_xyz','vertices':points,'cells':cells})


def audit_mesh_geometry(mesh):
    if not isinstance(mesh, dict) or mesh.get('contract') != 'spike/solver-mesh/v1':
        raise ValueError('Expected solver-mesh/v1')
    if mesh.get('units') not in ('m', 'mm') or mesh.get('coordinate_system') != 'right_handed_xyz':
        raise ValueError('Explicit physical units and frame required')
    raw = mesh.get('vertices')
    cells = mesh.get('cells')
    if not isinstance(raw, list) or not 4 <= len(raw) <= 100000 or not isinstance(cells, list) or not 1 <= len(cells) <= 100000:
        raise ValueError('Mesh exceeds diagnostic budget')
    if any(not isinstance(p, list) or len(p) != 3 or any(type(x) not in (int,float) for x in p) for p in raw):
        raise ValueError('Untyped mesh coordinates')
    try:
        points = np.asarray(raw, dtype=float) * (1e-3 if mesh['units'] == 'mm' else 1)
    except (ValueError, OverflowError) as exc:
        raise ValueError('Unrepresentable coordinates') from exc
    if not np.all(np.isfinite(points)) or np.max(np.abs(points)) > 1e6:
        raise ValueError('Nonfinite or out-of-range coordinates')
    templates = {'tetrahedron': [(0,1,2),(0,3,1),(1,3,2),(2,3,0)],
                 'hexahedron': [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]}
    centers, volumes, faces, seen = [], [], {}, set()
    for cell_index, cell in enumerate(cells):
        if not isinstance(cell,dict) or cell.get('kind') not in templates:
            raise ValueError('Only tetrahedra and convex planar-faced hexahedra supported')
        ids = cell.get('vertices')
        n = 4 if cell['kind'] == 'tetrahedron' else 8
        if not isinstance(ids,list) or len(ids) != n or any(type(i) is not int or not 0 <= i < len(points) for i in ids) or len(set(ids)) != n:
            raise ValueError('Invalid cell indices')
        key = tuple(sorted(ids))
        if key in seen:
            raise ValueError('Duplicate volume cell')
        seen.add(key)
        vertices = points[ids]
        seed = vertices.mean(axis=0)
        length = float(np.linalg.norm(np.ptp(vertices, axis=0)))
        if not math.isfinite(length) or length <= 1e-12:
            raise ValueError('Degenerate diagnostic cell scale')
        tolerance = 1e-10*length
        volume, moment = 0.0, np.zeros(3)
        for template in templates[cell['kind']]:
            face_ids = [ids[i] for i in template]
            face = points[face_ids]
            normal = np.cross(face[1]-face[0],face[2]-face[0])
            size = float(np.linalg.norm(normal))
            if size <= 1e-14*length**2:
                raise ValueError('Degenerate face')
            normal /= size
            if np.dot(normal,face[0]-seed) < 0:
                face_ids.reverse()
                face = points[face_ids]
                normal = -normal
            if np.max(np.abs((face-face[0]) @ normal)) > tolerance:
                raise ValueError('Nonplanar hexahedral face')
            if np.max((vertices-face[0]) @ normal) > tolerance:
                raise ValueError('Nonconvex or incorrectly ordered cell')
            area, face_moment = 0.0, np.zeros(3)
            for j in range(1,len(face)-1):
                a,b,c = face[0],face[j],face[j+1]
                triangle_area = float(np.dot(np.cross(b-a,c-a),normal))/2
                if triangle_area <= 0:
                    raise ValueError('Nonconvex face triangulation')
                tetra_volume = float(np.dot(a-seed,np.cross(b-seed,c-seed)))/6
                if tetra_volume <= 0:
                    raise ValueError('Inverted cell subvolume')
                area += triangle_area
                face_moment += triangle_area*(a+b+c)/3
                volume += tetra_volume
                moment += tetra_volume*(seed+a+b+c)/4
            record = (cell_index, face_moment/area, normal, area)
            faces.setdefault(tuple(sorted(face_ids)), []).append(record)
        if not math.isfinite(volume) or volume <= 0:
            raise ValueError('Nonfinite volume')
        centers.append(moment/volume)
        volumes.append(volume)
    angles = []
    interior = 0
    for records in faces.values():
        if len(records) > 2:
            raise ValueError('Nonmanifold face')
        owner, face_center, normal, _ = records[0]
        if len(records) == 2:
            other = records[1]
            if np.dot(normal,other[2]) > -1+1e-8:
                raise ValueError('Overlapping or same-side adjacent cells')
            delta = centers[other[0]]-centers[owner]
            interior += 1
        else:
            delta = face_center-centers[owner]
        distance = float(np.linalg.norm(delta))
        cosine = float(np.dot(normal,delta))/distance if distance > 0 else -1
        if not math.isfinite(cosine) or cosine <= 0:
            raise ValueError('Invalid face-centroid orientation')
        angles.append(math.degrees(math.acos(min(1,cosine))))
    maximum = max(angles)
    return {'contract':'spike/openfoam-mesh-geometry-diagnostic/v1', 'cell_count':len(cells),
            'interior_faces':interior, 'boundary_faces':len(faces)-interior,
            'volume_m3':sum(volumes), 'minimum_cell_volume_m3':min(volumes),
            'maximum_face_nonorthogonality_deg':maximum,
            'orthogonal_centroid_geometry':maximum <= 1e-5,
            'production_qualified':False,
            'scope':'convex_planar_faces_centroid_geometry_not_global_intersection_or_flux_qualification'}
