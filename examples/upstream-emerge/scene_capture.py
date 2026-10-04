"""Capture public EMerge geometry without changing its solver coordinate frame.

SPDX-License-Identifier: GPL-2.0-or-later
"""
import hashlib
import numpy as np


def physical_mesh(model, namespace, output, index):
    """Return complete material-bearing surface triangles, excluding air domains."""
    import gmsh
    regions = []
    excluded = []
    owners = {}
    # Surface materials take precedence over adjacent volume material skins.
    geometries = sorted(model.all_geos(), key=lambda item: -item.dim)
    for geometry in geometries:
        if geometry.dim not in (2, 3):
            continue
        material = geometry.material
        material_name = getattr(material, 'name', '') if material is not None else ''
        aliases = [key for key, value in namespace.items() if value is geometry]
        name = aliases[0] if aliases else geometry.name
        if material is None or material_name.casefold() in ('air', 'vacuum'):
            excluded.append({'name': name, 'reason': 'unassigned auxiliary surface' if material is None else 'air/vacuum simulation domain'})
            continue
        dimtags = list(geometry.dimtags)
        faces = gmsh.model.getBoundary(dimtags, combined=True, oriented=False) if geometry.dim == 3 else dimtags
        region = {'name': name, 'material': material_name, 'dimension': geometry.dim,
                  'entity_tags': [int(tag) for _, tag in dimtags]}
        regions.append(region)
        for dim, tag in faces:
            if dim == 2:
                owners[int(tag)] = len(regions) - 1
    tags, coordinates, _ = gmsh.model.mesh.getNodes()
    coordinates = np.asarray(coordinates).reshape(-1, 3)
    lookup = {int(tag): i for i, tag in enumerate(tags)}
    triangles = []
    compact_regions = []
    for region_index, region in enumerate(regions):
        start = len(triangles)
        face_tags = sorted(tag for tag, owner in owners.items() if owner == region_index)
        for tag in face_tags:
            types, _, elements = gmsh.model.mesh.getElements(2, tag)
            for element_type, nodes in zip(types, elements):
                properties = gmsh.model.mesh.getElementProperties(int(element_type))
                primary = properties[5]
                corners = np.asarray(nodes).reshape(-1, properties[3])[:, :primary]
                if primary == 3:
                    triangles.extend(corners.tolist())
                elif primary == 4:
                    for a, b, c, d in corners:
                        triangles.extend([[a, b, c], [a, c, d]])
                else:
                    raise ValueError('Unsupported physical surface element: ' + str(element_type))
        region.update(face_tags=face_tags, triangle_start=start, triangle_count=len(triangles)-start)
        if region['triangle_count']:
            compact_regions.append({key: region[key] for key in ('name', 'material', 'triangle_start', 'triangle_count')})
    if not triangles:
        return None, {'diagnostic': 'No assigned non-air physical surfaces; no model geometry was invented', 'excluded': excluded}
    faces = np.asarray(triangles, dtype=np.int64)
    used = np.unique(faces)
    local = {int(tag): i for i, tag in enumerate(used)}
    vertices = np.asarray([coordinates[lookup[int(tag)]] for tag in used])
    triangles = np.asarray([[local[int(tag)] for tag in face] for face in faces], dtype=np.int64)
    artifact = output / ('mesh-' + str(index) + '.npz')
    np.savez_compressed(artifact, node_tags=used, vertices=vertices, triangles=triangles,
                        triangles_node_tags=faces)
    metadata = {'file': artifact.name, 'coordinate_unit': 'm', 'nodes': len(used),
                'surface_triangles': len(faces), 'regions': regions, 'excluded': excluded,
                'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                'representation': 'complete physical surface primary-node triangles; no CAD/port fidelity claim'}
    # Refuse to punch holes in geometry through triangle striding.
    if len(vertices) > 10000 or len(triangles) > 10000 or 3*(len(vertices)+len(triangles)) > 45000:
        metadata['diagnostic'] = 'Physical mesh exceeds bounded scene budget; full mesh sidecar retained, preview unavailable'
        return None, metadata
    return (vertices.tolist(), triangles.tolist(), artifact.name, compact_regions), metadata
