# SPDX-License-Identifier: Apache-2.0
"""Conforming barycentric tetrahedron-to-hexahedron mesh preparation.

The caller admits the source tetrahedra first. No original boundary moves:
each triangular face becomes three coplanar quadrilaterals. See the independent
method/evidence record in ASSEMBLY_AIRFLOW_SUBDIVISION_20261026.md.
"""
import math

HEX_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def subdivide_airflow_mesh(mesh, limits, *, cancellation_event=None):
    """Partition admitted tetrahedra, retaining source/region identities.

Limits apply to the resulting global CFD mesh, not just the input tetrahedra.
The four child volumes each equal one quarter of the parent volume. Shared
node keys use original vertex identities, never coordinate rounding.
"""
    source, parents = mesh['vertices'], mesh['cells']
    if 4 * len(parents) > limits['max_cells']:
        raise ValueError('AIRFLOW_RESOURCE: subdivided CFD cell limit exceeded')
    points = [list(point) for point in source]
    nodes = {(i,): i for i in range(len(source))}

    def node(vertices):
        key = tuple(sorted(vertices))
        if key not in nodes:
            if len(points) >= limits['max_vertices']:
                raise ValueError('AIRFLOW_RESOURCE: subdivided CFD vertex limit exceeded')
            nodes[key] = len(points)
            points.append([math.fsum(source[i][axis] for i in key) / len(key)
                           for axis in range(3)])
        return nodes[key]

    cells = []
    for index, cell in enumerate(parents):
        if index % 256 == 0 and cancellation_event is not None and cancellation_event.is_set():
            raise InterruptedError('AIRFLOW_CANCELLED: mesh subdivision cancelled')
        vertices = cell['vertices']
        for local, vertex in enumerate(vertices):
            a, b, c = [other for other in vertices if other != vertex]
            corners = ((vertex,), (vertex, a), (vertex, a, b), (vertex, b),
                       (vertex, c), (vertex, a, c), tuple(vertices), (vertex, b, c))
            cells.append({**cell, 'id': cell['id'] + '_sub_' + str(local),
                          'kind': 'hexahedron', 'vertices': [node(key) for key in corners]})
    return {**mesh, 'vertices': points, 'cells': cells,
            'subdivision': {'method': 'barycentric-tet-to-four-hex/v1',
                            'parent_cell_count': len(parents), 'cell_count': len(cells)}}
