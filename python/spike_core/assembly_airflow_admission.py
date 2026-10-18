# SPDX-License-Identifier: Apache-2.0
"""Source-bound tetrahedral volume admission before CHT power normalization."""
import math

from .gmsh_occ_mesher import _det


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def admit_airflow_mesh(request, mesh):
    """Recompute mm^3 from vertices; supplied volumes never determine watts."""
    if not isinstance(mesh, dict) or mesh.get('units') != 'mm':
        raise ValueError('AIRFLOW_MESH: explicit millimetre units required')
    expected = {'solid_' + str(i): solid['id']
                for i, solid in enumerate(request['geometry']['solids'])}
    if mesh.get('source_ids') != expected:
        raise ValueError('AIRFLOW_SOURCE: mesh source identities do not match requested solids')
    regions = {'air', *expected}
    declared = mesh.get('volumes_mm3')
    cad = mesh.get('cad_volumes_mm3')
    if (not isinstance(declared, dict) or set(declared) != regions
            or not isinstance(cad, dict) or set(cad) != set(expected)
            or not all(_positive(v) for v in [*declared.values(), *cad.values()])):
        raise ValueError('AIRFLOW_VOLUME: complete positive mesh and CAD volumes required')
    points, cells = mesh.get('vertices'), mesh.get('cells')
    limits = request['geometry']['mesh']
    if (not isinstance(points, list) or not 4 <= len(points) <= limits['max_vertices']
            or not isinstance(cells, list) or not 1 <= len(cells) <= limits['max_cells']):
        raise ValueError('AIRFLOW_RESOURCE: mesh arrays exceed requested limits')
    for point in points:
        if (not isinstance(point, list) or len(point) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)):
            raise ValueError('AIRFLOW_MESH: finite XYZ coordinates required')
    if len({tuple(p) for p in points}) != len(points):
        raise ValueError('AIRFLOW_MESH: duplicate coordinates are not conforming shared vertices')
    contributions = {region: [] for region in regions}
    identities, tetrahedra, used = set(), set(), set()
    for cell in cells:
        if not isinstance(cell, dict) or cell.get('kind') != 'tetrahedron':
            raise ValueError('AIRFLOW_MESH: linear tetrahedra required')
        region, identity, nodes = cell.get('material_id'), cell.get('id'), cell.get('vertices')
        if not isinstance(region, str) or region not in regions:
            raise ValueError('AIRFLOW_SOURCE: unexpected mesh region')
        if not isinstance(identity, str) or not identity or identity in identities:
            raise ValueError('AIRFLOW_MESH: unique nonempty cell identities required')
        if (not isinstance(nodes, list) or len(nodes) != 4
                or any(type(v) is not int or not 0 <= v < len(points) for v in nodes)
                or len(set(nodes)) != 4):
            raise ValueError('AIRFLOW_MESH: four distinct valid tetrahedron vertices required')
        key = tuple(sorted(nodes))
        if key in tetrahedra:
            raise ValueError('AIRFLOW_MESH: duplicate tetrahedron across regions')
        determinant = _det(points, nodes)
        scale = max(abs(points[a][axis] - points[b][axis])
                    for a in nodes for b in nodes for axis in range(3))
        # Roundoff guard for the determinant's cubic length scale. This is
        # conditioning admission, not a substitute for native checkMesh.
        if not math.isfinite(determinant) or determinant <= 64 * math.ulp(1.0) * scale * scale * scale:
            raise ValueError('AIRFLOW_MESH: inverted, degenerate or ill-conditioned tetrahedron')
        contributions[region].append(determinant / 6)
        identities.add(identity)
        tetrahedra.add(key)
        used.update(nodes)
    if len(used) != len(points):
        raise ValueError('AIRFLOW_MESH: unused vertices are not admitted')
    volumes = {region: math.fsum(values) for region, values in contributions.items()}
    for region, volume in volumes.items():
        if not _positive(volume):
            raise ValueError('AIRFLOW_SOURCE: every requested solid and air region needs cells')
        if not math.isclose(volume, declared[region], rel_tol=1e-9, abs_tol=0):
            raise ValueError('AIRFLOW_VOLUME: reported volume differs from tetrahedral geometry')
        if region != 'air' and abs(volume - cad[region]) > .02 * cad[region]:
            raise ValueError('AIRFLOW_VOLUME: solid mesh differs from CAD by more than two percent; refine mesh')
    return volumes
