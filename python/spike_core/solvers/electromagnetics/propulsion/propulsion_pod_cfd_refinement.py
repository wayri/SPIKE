# SPDX-License-Identifier: Apache-2.0
"""Bounded nested tetra subdivision and unsolved P2/P1 initial guesses.

Centroid subdivision preserves every original vertex and triangle. Explicit
boundary-edge subdivision preserves their polyhedral support and ancestry.
Marking is not an error estimator, solver result, or convergence certificate.
See docs/validation/PROPULSION_POD_CFD_REFINEMENT_20261024.md.
"""
import copy
import itertools
from fractions import Fraction

import numpy as np

from ...thermal_fluid.flow.cfd_tetra_mesh import CONTRACT, MAX_CONDITION, CfdTetraMeshError, _indices, _label, _raw_mesh_encoding, _require, admit_cfd_tetra_mesh

MAX_CELLS = 40000
_EDGES = tuple(itertools.combinations(range(4), 2))


def _local_geometry(raw, budget):
    """Bounded schema/element checks only; explicitly not global admission."""
    _require(type(raw) is dict and set(raw) == {
        'contract', 'units', 'vertices', 'cells', 'boundary_patches'},
        'Unexpected numerical mesh fields')
    _require(raw['contract'] == CONTRACT and raw['units'] == 'm', 'Invalid contract/units')
    xyz, rows = raw['vertices'], raw['cells']
    _require(type(xyz) is list and 4 <= len(xyz) <= 4*budget
             and type(rows) is list and 1 <= len(rows) <= budget, 'Mesh budget exceeded')
    _require(all(type(p) is list and len(p) == 3 and all(
        type(v) in (int, float) for v in p) for p in xyz), 'Invalid coordinates')
    vertices = np.asarray(xyz, dtype=float)
    _require(np.isfinite(vertices).all(), 'Nonfinite coordinates')
    cells = np.asarray([_indices(c, len(xyz), 4) for c in rows], dtype=np.int64)
    _require(len({tuple(p) for p in xyz}) == len(xyz), 'Duplicate geometric vertices')
    _require(len({tuple(sorted(c)) for c in rows}) == len(rows), 'Duplicate cells')
    _require(set(cells.ravel()) == set(range(len(xyz))), 'Orphan vertices')
    patches = raw['boundary_patches']
    _require(type(patches) is dict and 1 <= len(patches) <= 4*budget
             and all(_label(k) for k in patches), 'Invalid boundary patches')
    seen = set()
    for faces in patches.values():
        _require(type(faces) is list and 1 <= len(faces) <= 4*budget, 'Invalid patch faces')
        for face in faces:
            key = tuple(sorted(_indices(face, len(xyz), 3)))
            _require(key not in seen and len(seen) < 4*budget, 'Duplicate/excess boundary face')
            seen.add(key)
    local = vertices[cells[:, 1:]]-vertices[cells[:, :1]]
    length = np.max(abs(local), axis=(1, 2))
    _require(np.all(length > 0), 'Collapsed tetrahedron')
    jacobian = (local/length[:, None, None]).transpose(0, 2, 1)
    determinant = np.linalg.det(jacobian)
    condition = np.linalg.cond(jacobian)
    _require(np.all(determinant > 0), 'Inverted/degenerate tetrahedron; no repair')
    _require(np.isfinite(condition).all() and np.max(condition) <= MAX_CONDITION,
             'Tetrahedron condition exceeds 1e6')
    volumes = length**3*determinant/6
    _require(np.isfinite(volumes).all() and np.all(volumes > 0), 'Invalid cell volume')
    return vertices, cells, volumes, float(np.max(condition))


def _p2_layout(vertices, cells):
    """Same first-encounter edge ordering as the existing Taylor-Hood owner."""
    points = vertices.tolist()
    edges, local = {}, []
    for cell in cells:
        row = list(map(int, cell))
        for i, j in _EDGES:
            key = tuple(sorted((int(cell[i]), int(cell[j]))))
            if key not in edges:
                edges[key] = len(points)
                points.append(((vertices[key[0]]+vertices[key[1]])*.5).tolist())
            row.append(edges[key])
        local.append(row)
    return np.asarray(points), np.asarray(local, dtype=np.int64), edges


def _transfer(source, refined, marks, fields):
    old_x, old_c = source
    new_x, new_c = refined
    old_nodes, old_local, old_edges = _p2_layout(old_x, old_c)
    new_nodes, new_local, new_edges = _p2_layout(new_x, new_c)
    for name, expected in (('P2_nodes_m', old_nodes), ('P1_nodes_m', old_x),
                           ('tetrahedra', old_c), ('cell_P2_nodes', old_local)):
        actual = np.asarray(fields[name])
        allowed = 'iu' if name in ('tetrahedra', 'cell_P2_nodes') else 'iuf'
        _require(actual.dtype.kind in allowed, 'Real numeric field layout required: '+name)
        _require(actual.shape == expected.shape and np.array_equal(actual, expected),
                 'Initial field source layout mismatch: '+name)
    old_u = np.asarray(fields['P2_velocity_m_s'])
    old_p = np.asarray(fields['P1_pressure_pa'])
    _require(old_u.dtype.kind in 'iuf' and old_p.dtype.kind in 'iuf',
             'Real numeric velocity/pressure fields required')
    old_u, old_p = old_u.astype(float, copy=False), old_p.astype(float, copy=False)
    _require(old_u.shape == (len(old_nodes), 3) and old_p.shape == (len(old_x),)
             and np.isfinite(old_u).all() and np.isfinite(old_p).all(), 'Invalid initial fields')
    u, p = np.empty((len(new_nodes), 3)), np.empty(len(new_x))
    u[:len(old_x)], p[:len(old_x)] = old_u[:len(old_x)], old_p
    for edge, index in old_edges.items():
        u[new_edges[edge]] = old_u[index]
    # Each new edge is wholly inside one parent; existing interface nodes are
    # copied by identity. No spatial nearest-neighbour search or extrapolation.
    for offset, parent in enumerate(marks):
        centroid = len(old_x)+offset
        indices = [centroid]+[new_edges[tuple(sorted((centroid, int(v))))]
                              for v in old_c[parent]]
        corners = old_x[old_c[parent]]
        jacobian = (corners[1:]-corners[0]).T
        tail = np.linalg.solve(jacobian, (new_nodes[indices]-corners[0]).T).T
        bary = np.column_stack((1-tail.sum(axis=1), tail))
        _require(np.isfinite(bary).all() and np.all(bary > 0)
                 and np.all(bary < 1), 'Transferred interior node outside parent')
        basis = np.column_stack([bary*(2*bary-1)]+
                                [(4*bary[:, i]*bary[:, j])[:, None] for i, j in _EDGES])
        u[indices] = basis@old_u[old_local[parent]]
        p[centroid] = bary[0]@old_p[old_c[parent]]
    _require(np.isfinite(u).all() and np.isfinite(p).all(), 'Nonfinite transfer')
    return {'P2_nodes_m': new_nodes, 'P2_velocity_m_s': u, 'P1_nodes_m': new_x.copy(),
            'P1_pressure_pa': p, 'tetrahedra': new_c.copy(), 'cell_P2_nodes': new_local,
            'status': 'unsolved_initial_guess', 'load_qualified': False,
            'nonlinear_source_kernel_energy_load_gates_required': True}


def refine_centroid_tetrahedra(raw_mesh, parent_cell_ids, *, max_cells=MAX_CELLS,
                              validate=True, initial_fields=None, cancel_check=None):
    """Return strict raw mesh, separate provenance and optional unsolved fields.

    Markers are unique zero-based existing cell IDs. Unselected cell indices
    survive: child0 replaces each selected parent; children1..3 are appended.
    ``validate=True`` runs unchanged full source AND destination admission.
    ``validate=False`` explicitly returns a locally checked, globally unadmitted
    candidate, useful for bounded preparation; it NEVER authorizes a flow run.
    Caller must retain any CAD/source ownership envelope separately, tied to
    source_mesh_sha256 and the parent/child map. Raw meshes have no CAD IDs.
    """
    _require(type(max_cells) is int and 1 <= max_cells <= MAX_CELLS, 'Invalid cell budget')
    _require(type(validate) is bool, 'Explicit boolean validation mode required')
    _require(type(parent_cell_ids) is list and 1 <= len(parent_cell_ids) <= max_cells
             and all(type(i) is int for i in parent_cell_ids), 'Invalid parent markers')
    _require(len(set(parent_cell_ids)) == len(parent_cell_ids), 'Duplicate parent markers')
    if cancel_check and cancel_check():
        raise InterruptedError('Tetra refinement cancelled')
    # Snapshot and hash before any callback; never modify the caller mesh.
    digest, raw = _raw_mesh_encoding(raw_mesh, retain=True)
    try:
        with np.errstate(all='raise'):
            vertices, cells, volumes, old_condition = _local_geometry(raw, max_cells)
            marks = sorted(parent_cell_ids)
            _require(0 <= marks[0] and marks[-1] < len(cells), 'Parent marker out of range')
            _require(len(cells)+3*len(marks) <= max_cells, 'Refined cell budget exceeded')
            if validate:
                admit_cfd_tetra_mesh(raw, max_cells=max_cells, cancel_check=cancel_check)
            result = copy.deepcopy(raw)
            parents = list(range(len(cells)))
            records = []
            for parent in marks:
                if cancel_check and cancel_check():
                    raise InterruptedError('Tetra refinement cancelled')
                corners = vertices[cells[parent]]
                point = corners[0]+(corners-corners[0]).mean(axis=0)
                tail = np.linalg.solve((corners[1:]-corners[0]).T, point-corners[0])
                bary = np.r_[1-tail.sum(), tail]
                _require(np.isfinite(bary).all() and np.all(bary > 0), 'Centroid outside parent')
                node = len(result['vertices'])
                result['vertices'].append(point.tolist())
                children = []
                for opposite in range(4):
                    child = raw['cells'][parent].copy()
                    child[opposite] = node
                    index = parent if opposite == 0 else len(result['cells'])
                    if opposite == 0:
                        result['cells'][parent] = child
                    else:
                        result['cells'].append(child)
                        parents.append(parent)
                    children.append(index)
                records.append({'parent_cell_id': parent, 'centroid_vertex_id': node,
                                'centroid_parent_barycentric': bary.tolist(),
                                'child_cell_ids': children})
            new_x, new_c, new_volumes, new_condition = _local_geometry(result, max_cells)
            error = 0.
            for record in records:
                parent = record['parent_cell_id']
                ratios = new_volumes[record['child_cell_ids']]/volumes[parent]
                defect = abs(float(ratios.sum())-1)
                _require(defect <= 1e-10 and np.max(abs(ratios-.25)) <= 1e-10,
                         'Parent-child volume partition failed')
                error = max(error, defect)
            if validate:
                admit_cfd_tetra_mesh(result, max_cells=max_cells, cancel_check=cancel_check)
            guess = None if initial_fields is None else _transfer(
                (vertices, cells), (new_x, new_c), marks, initial_fields)
    except (ArithmeticError, np.linalg.LinAlgError) as exc:
        raise CfdTetraMeshError('Unrepresentable refinement geometry/transfer') from exc
    result_digest, _ = _raw_mesh_encoding(result, retain=False)
    return {'mesh': result, 'initial_guess': guess, 'provenance': {
        'contract': 'spike/tetra-centroid-refinement/v1', 'source_mesh_sha256': digest,
        'refined_mesh_sha256': result_digest, 'source_cell_count': len(cells),
        'refined_cell_count': len(new_c), 'source_vertex_count': len(vertices),
        'refined_vertex_count': len(new_x), 'selected_parent_cell_ids': marks,
        'children': records, 'output_cell_parent_ids': parents,
        'original_vertices_and_boundary_triangles_unchanged': True,
        'maximum_relative_parent_volume_defect': error,
        'source_maximum_cell_condition': old_condition,
        'refined_maximum_cell_condition': new_condition,
        'full_source_and_destination_geometry_admitted': validate,
        'pressure_kernel_checked': False, 'load_qualified': False,
        'status': 'geometry_admitted_unsolved' if validate else 'globally_unadmitted_candidate',
        'construction_is_error_estimate': False, 'uniform_grid_GCI_evidence': False}}


def _edge_transfer(source, refined, cell_parents, records, fields):
    """Restrict old polynomials to nested children; global DOF IDs may change."""
    old_x, old_c = source
    new_x, new_c = refined
    old_nodes, old_local, old_edges = _p2_layout(old_x, old_c)
    new_nodes, new_local, new_edges = _p2_layout(new_x, new_c)
    for name, expected in (('P2_nodes_m', old_nodes), ('P1_nodes_m', old_x),
                           ('tetrahedra', old_c), ('cell_P2_nodes', old_local)):
        actual = np.asarray(fields[name])
        allowed = 'iu' if name in ('tetrahedra', 'cell_P2_nodes') else 'iuf'
        _require(actual.dtype.kind in allowed, 'Real numeric field layout required: '+name)
        _require(actual.shape == expected.shape and np.array_equal(actual, expected),
                 'Initial field source layout mismatch: '+name)
    old_u, old_p = np.asarray(fields['P2_velocity_m_s']), np.asarray(fields['P1_pressure_pa'])
    _require(old_u.dtype.kind in 'iuf' and old_p.dtype.kind in 'iuf',
             'Real numeric velocity/pressure fields required')
    old_u, old_p = old_u.astype(float, copy=False), old_p.astype(float, copy=False)
    _require(old_u.shape == (len(old_nodes), 3) and old_p.shape == (len(old_x),)
             and np.isfinite(old_u).all() and np.isfinite(old_p).all(), 'Invalid initial fields')
    u, p = np.full((len(new_nodes), 3), np.nan), np.full(len(new_x), np.nan)
    u[:len(old_x)], p[:len(old_x)] = old_u[:len(old_x)], old_p
    for edge, index in old_edges.items():
        if edge in new_edges:
            u[new_edges[edge]] = old_u[index]
    for record in records:
        edge, node = tuple(record['edge_vertex_ids']), record['midpoint_vertex_id']
        u[node] = old_u[old_edges[edge]]
        p[node] = old_p[list(edge)].mean()
    # The first containing output cell supplies a deterministic old parent.
    owners = {}
    for cell_id, row in enumerate(new_local):
        for node in row:
            if not np.isfinite(u[node]).all():
                owners.setdefault(int(node), cell_parents[cell_id])
    for node, parent in owners.items():
        corners = old_x[old_c[parent]]
        tail = np.linalg.solve((corners[1:]-corners[0]).T, new_nodes[node]-corners[0])
        bary = np.r_[1-tail.sum(), tail]
        _require(np.isfinite(bary).all() and bary.min() >= -1e-10
                 and bary.max() <= 1+1e-10, 'Transfer node outside recorded parent')
        basis = np.r_[bary*(2*bary-1), [4*bary[i]*bary[j] for i, j in _EDGES]]
        u[node] = basis@old_u[old_local[parent]]
    _require(np.isfinite(u).all() and np.isfinite(p).all(), 'Nonfinite transfer')
    return {'P2_nodes_m': new_nodes, 'P2_velocity_m_s': u, 'P1_nodes_m': new_x.copy(),
            'P1_pressure_pa': p, 'tetrahedra': new_c.copy(), 'cell_P2_nodes': new_local,
            'status': 'unsolved_initial_guess', 'load_qualified': False,
            'nonlinear_source_kernel_energy_load_gates_required': True}


def refine_boundary_edge_stars(raw_mesh, edge_stars, *, boundary_patch='rotor',
                               max_cells=MAX_CELLS, max_vertices=5000,
                               validate=True, initial_fields=None, cancel_check=None):
    """Split complete, cell-disjoint boundary edge stars at exact midpoints.

    Every marker is {'edge_vertex_ids': [a,b], 'parent_cell_ids': [all incident
    existing cell IDs]}. The explicit closure witness must equal the actual star.
    Nonrepresentable binary64 midpoints and patch seams are rejected. No snapping,
    smoothing or surface repair occurs. Default full source/destination admission
    is unchanged; validate=False returns a globally unadmitted candidate only.
    Source-face ancestry replaces any claim that split face IDs are unchanged.
    """
    _require(type(max_cells) is int and 1 <= max_cells <= MAX_CELLS, 'Invalid cell budget')
    _require(type(max_vertices) is int and 4 <= max_vertices <= 5000, 'Invalid vertex budget')
    _require(type(validate) is bool and _label(boundary_patch), 'Invalid refinement options')
    _require(type(edge_stars) is list and 1 <= len(edge_stars) <= max_vertices,
             'Invalid edge-star markers')
    if cancel_check and cancel_check():
        raise InterruptedError('Edge refinement cancelled')
    digest, raw = _raw_mesh_encoding(raw_mesh, retain=True)
    try:
        with np.errstate(all='raise'):
            vertices, cells, volumes, old_condition = _local_geometry(raw, max_cells)
            _require(boundary_patch in raw['boundary_patches'], 'Unknown boundary patch')
            stars, claimed, edges = [], set(), set()
            coordinate_keys = {tuple(point) for point in raw['vertices']}
            for marker in edge_stars:
                _require(type(marker) is dict and set(marker) == {
                    'edge_vertex_ids', 'parent_cell_ids'}, 'Invalid edge-star marker fields')
                edge = tuple(sorted(_indices(marker['edge_vertex_ids'], len(vertices), 2)))
                ids = marker['parent_cell_ids']
                _require(type(ids) is list and 1 <= len(ids) <= len(cells)
                         and all(type(i) is int for i in ids) and len(set(ids)) == len(ids),
                         'Invalid star parent IDs')
                actual = np.flatnonzero(np.any(cells == edge[0], axis=1)
                                        & np.any(cells == edge[1], axis=1)).tolist()
                _require(actual and sorted(ids) == actual, 'Incomplete/incorrect edge star')
                _require(edge not in edges and claimed.isdisjoint(actual),
                         'Duplicate/overlapping edge stars')
                boundary_faces = [(patch, i) for patch, faces in raw['boundary_patches'].items()
                                  for i, f in enumerate(faces) if all(v in f for v in edge)]
                _require(len(boundary_faces) == 2 and all(p == boundary_patch for p, _ in boundary_faces),
                         'Edge must have two boundary faces in the named patch; no patch seams')
                exact = [(Fraction(float(vertices[edge[0], j]))+
                          Fraction(float(vertices[edge[1], j])))/2 for j in range(3)]
                midpoint = [float(q) for q in exact]
                _require(all(Fraction(x) == q for x, q in zip(midpoint, exact)),
                         'Boundary midpoint is not exactly representable')
                _require(tuple(midpoint) not in coordinate_keys,
                         'New midpoint coincides with an existing/new vertex')
                coordinate_keys.add(tuple(midpoint))
                stars.append((edge, actual, midpoint))
                edges.add(edge); claimed.update(actual)
            _require(len(cells)+len(claimed) <= max_cells, 'Refined cell budget exceeded')
            _require(len(vertices)+len(stars) <= max_vertices, 'Refined vertex budget exceeded')
            if validate:
                admit_cfd_tetra_mesh(raw, max_cells=max_cells, cancel_check=cancel_check)
            result, parents, records = copy.deepcopy(raw), list(range(len(cells))), []
            face_parents = {p: list(range(len(f))) for p, f in raw['boundary_patches'].items()}
            for edge, actual, midpoint in sorted(stars):
                if cancel_check and cancel_check():
                    raise InterruptedError('Edge refinement cancelled')
                node = len(result['vertices']); result['vertices'].append(midpoint)
                child_records = []
                for parent in actual:
                    a = raw['cells'][parent].index(edge[0]); b = raw['cells'][parent].index(edge[1])
                    first, second = raw['cells'][parent].copy(), raw['cells'][parent].copy()
                    first[a], second[b] = node, node
                    child = len(result['cells']); result['cells'][parent] = first
                    result['cells'].append(second); parents.append(parent)
                    child_records.append({'parent_cell_id': parent, 'child_cell_ids': [parent, child]})
                patch_faces = []
                for face_id, face in enumerate(raw['boundary_patches'][boundary_patch]):
                    if all(v in face for v in edge):
                        first, second = face.copy(), face.copy()
                        first[face.index(edge[0])], second[face.index(edge[1])] = node, node
                        child = len(result['boundary_patches'][boundary_patch])
                        result['boundary_patches'][boundary_patch][face_id] = first
                        result['boundary_patches'][boundary_patch].append(second)
                        face_parents[boundary_patch].append(face_id)
                        patch_faces.append({'source_face_id': face_id, 'child_face_ids': [face_id, child]})
                records.append({'edge_vertex_ids': list(edge), 'midpoint_vertex_id': node,
                                'source_parent_cell_ids': actual, 'children': child_records,
                                'boundary_face_children': patch_faces})
            new_x, new_c, new_volumes, new_condition = _local_geometry(result, max_cells)
            error = 0.
            for record in records:
                for child in record['children']:
                    ratios = new_volumes[child['child_cell_ids']]/volumes[child['parent_cell_id']]
                    defect = abs(float(ratios.sum())-1)
                    _require(defect <= 1e-10 and np.max(abs(ratios-.5)) <= 1e-10,
                             'Edge parent-child volume partition failed')
                    error = max(error, defect)
            if validate:
                admit_cfd_tetra_mesh(result, max_cells=max_cells, cancel_check=cancel_check)
            guess = None if initial_fields is None else _edge_transfer(
                (vertices, cells), (new_x, new_c), parents, records, initial_fields)
    except (ArithmeticError, np.linalg.LinAlgError) as exc:
        raise CfdTetraMeshError('Unrepresentable edge refinement geometry/transfer') from exc
    result_digest, _ = _raw_mesh_encoding(result, retain=False)
    return {'mesh': result, 'initial_guess': guess, 'provenance': {
        'contract': 'spike/tetra-boundary-edge-refinement/v1', 'source_mesh_sha256': digest,
        'refined_mesh_sha256': result_digest, 'source_cell_count': len(cells),
        'refined_cell_count': len(new_c), 'source_vertex_count': len(vertices),
        'refined_vertex_count': len(new_x), 'edge_stars': records,
        'output_cell_parent_ids': parents, 'output_patch_face_parent_ids': face_parents,
        'original_vertices_unchanged': True, 'boundary_polyhedral_support_exactly_preserved': True,
        'split_boundary_triangles_unchanged': False, 'exact_binary64_midpoints': True,
        'wall_normal_altitudes_reduced_by_edge_split': False,
        'maximum_relative_parent_volume_defect': error,
        'source_maximum_cell_condition': old_condition,
        'refined_maximum_cell_condition': new_condition,
        'full_source_and_destination_geometry_admitted': validate,
        'pressure_kernel_checked': False, 'load_qualified': False,
        'status': 'geometry_admitted_unsolved' if validate else 'globally_unadmitted_candidate',
        'construction_is_error_estimate': False, 'uniform_grid_GCI_evidence': False}}
