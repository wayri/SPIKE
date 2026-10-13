# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original retained-volume admission and occurrence-to-world SI lowering."""
import heapq
import itertools
import math
import numpy as np

from .assembly_frames import IDENTITY, resolve_world, validate_rigid_transform
from .multiboard_identity import canonical_json_digest
from .tetra_mesh_refinement import _validate

MAX_CELLS = 100000
MAX_VERTICES = 100000


def identity(*values):
    return canonical_json_digest(list(values))


def keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value)-set(required)-set(optional):
        raise ValueError('ASSEMBLY_FIELD_FIELDS: unexpected or missing fields')


def number(value, *, positive=False):
    if type(value) not in (int, float):
        raise ValueError('ASSEMBLY_FIELD_NUMBER: expected finite number, not bool/text')
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError('ASSEMBLY_FIELD_NUMBER: unrepresentable number') from exc
    if not math.isfinite(result) or positive and result <= 0:
        raise ValueError('ASSEMBLY_FIELD_NUMBER: invalid finite positive property')
    return result


def thermal_tensor(value):
    if type(value) in (int, float):
        return np.eye(3)*number(value, positive=True)
    if not isinstance(value, list) or len(value) != 3 or any(not isinstance(row, list) or len(row) != 3 for row in value):
        raise ValueError('ASSEMBLY_FIELD_MATERIAL: expected scalar or SPD 3x3 thermal tensor')
    tensor = np.array([[number(item) for item in row] for row in value])
    eigenvalues = np.linalg.eigvalsh(tensor)
    if (not np.array_equal(tensor, tensor.T) or not np.isfinite(eigenvalues).all() or
        eigenvalues[0] <= 0 or eigenvalues[-1]/eigenvalues[0] > 1e12):
        raise ValueError('ASSEMBLY_FIELD_MATERIAL: thermal tensor must be symmetric positive definite')
    return tensor


def validate_frames(assembly):
    if assembly.frame.units != 'mm' or assembly.frame.handedness != 'right' or tuple(assembly.frame.transform) != IDENTITY or assembly.frame.parent_frame_id:
        raise ValueError('ASSEMBLY_FIELD_ROOT: require an identity millimetre assembly root')
    for occurrence in [*assembly.boards, *assembly.parts]:
        frame = occurrence.frame
        if frame.units != 'mm' or frame.handedness != 'right':
            raise ValueError('ASSEMBLY_FIELD_FRAME: require right-handed millimetre placements')
        for item in frame.transform:
            number(item)
        validate_rigid_transform(frame.transform, 'Field occurrence '+occurrence.id)
        rotation = np.array(frame.transform).reshape(4,4)[:3,:3]
        if np.max(np.abs(rotation@rotation.T-np.eye(3))) > 1e-12:
            raise ValueError('ASSEMBLY_FIELD_FRAME: rotation accuracy exceeds field handoff tolerance')


def lower_body(assembly, occurrence, body, material_ids, *, max_cells=MAX_CELLS, max_vertices=MAX_VERTICES,
               roundoff_aware=False, transform_audit=None):
    """Check both local and represented world geometry; retain separate nodes."""
    mesh, boundary = body['mesh'], body['boundary_faces']
    if not isinstance(boundary, list) or len(boundary) > 4*max_cells:
        raise ValueError('ASSEMBLY_FIELD_BOUNDARY: bounded complete exterior faces required')
    face_ids = set()
    for face in boundary:
        keys(face, ('id', 'vertices'))
        if not isinstance(face['id'], str) or not face['id'] or face['id'] in face_ids:
            raise ValueError('ASSEMBLY_FIELD_BOUNDARY: duplicate or invalid face identity')
        face_ids.add(face['id'])
    labels = [{'vertices': face['vertices'], 'label': face['id']} for face in boundary]
    _validate(mesh, labels, max_cells, max_vertices)
    used_sources = {source for cell in mesh['cells'] for source in cell['source_object_ids']}
    if used_sources != set(mesh['object_map']):
        raise ValueError('ASSEMBLY_FIELD_SOURCE: every declared mesh object must own cells')
    local_materials = {cell['material_id'] for cell in mesh['cells']}
    if not isinstance(body['material_map'], dict) or len(body['material_map']) > 1024 or set(body['material_map']) != local_materials:
        raise ValueError('ASSEMBLY_FIELD_MATERIAL: exact local material coverage required')
    if not set(body['material_map'].values()) <= material_ids:
        raise ValueError('ASSEMBLY_FIELD_MATERIAL: unknown physical material')
    scale = .001 if mesh['units'] == 'mm' else 1.
    matrix = np.array(resolve_world(assembly, occurrence.frame)).reshape(4,4)
    points = np.array(mesh['vertices'], dtype=float)*scale
    world = points@matrix[:3,:3].T + matrix[:3,3]*.001
    if not np.all(np.isfinite(world)) or np.max(np.abs(world)) > 1e6:
        raise ValueError('ASSEMBLY_FIELD_FRAME: world coordinates exceed representable SI budget')
    transformed = {**mesh, 'units': 'm', 'vertices': world.tolist()}
    _validate(transformed, labels, max_cells, max_vertices)
    volumes = []
    roundoff_cells=0; maximum_perturbation=0.
    maximum_condition=0.; maximum_volume_error=0.; maximum_inverse_error=0.; maximum_inverse_residual=0.
    try:
        for cell in mesh['cells']:
            p, q = points[cell['vertices']], world[cell['vertices']]
            local_j, world_j = (p[1:]-p[0]).T, (q[1:]-q[0]).T
            expected_j = matrix[:3,:3]@local_j
            expected_inv = np.linalg.inv(local_j)@matrix[:3,:3].T
            actual_inv = np.linalg.inv(world_j)
            ratio = np.linalg.det(world_j)/np.linalg.det(local_j)
            errors = (abs(ratio-1), np.linalg.norm(world_j-expected_j)/np.linalg.norm(expected_j),
                      np.linalg.norm(actual_inv-expected_inv)/np.linalg.norm(expected_inv))
            if roundoff_aware:
                maximum_condition=max(maximum_condition,float(np.linalg.norm(expected_j)*np.linalg.norm(expected_inv)))
                maximum_volume_error=max(maximum_volume_error,float(errors[0]))
                maximum_inverse_error=max(maximum_inverse_error,float(errors[2]))
            if not all(math.isfinite(error) and error <= 1e-9 for error in errors):
                # Fine routed copper contains source-grid (1 nm) edges at
                # global coordinates around 0.1 m. Translation roundoff can
                # exceed a fixed relative 1e-9 on those tiny edge differences.
                # EM-only: bound the absolute forward error, then apply the
                # inverse/determinant matrix perturbation bounds, with a
                # strict one-ppm cap. This does not relax ordinary FEM checks.
                delta=world_j-expected_j
                magnitude=np.max(np.abs(p))*np.max(np.sum(np.abs(matrix[:3,:3]),axis=1))+np.max(np.abs(matrix[:3,3]*.001))
                forward_bound=16*np.finfo(float).eps*max(magnitude,np.finfo(float).tiny)
                perturbation=float(np.linalg.norm(expected_inv@delta))
                # Residuals certify the *computed* inverses. Skinny source
                # cells have cancellation in inversion even when coordinates
                # and the actual Jacobian perturbation remain representable.
                inverse_residual=max(float(np.linalg.norm(np.eye(3)-expected_j@expected_inv)),
                                     float(np.linalg.norm(np.eye(3)-expected_inv@expected_j)),
                                     float(np.linalg.norm(np.eye(3)-world_j@actual_inv)),
                                     float(np.linalg.norm(np.eye(3)-actual_inv@world_j)))
                determinant_bound=(1+perturbation)**3-1+1e-12
                inverse_bound=(perturbation+2*inverse_residual)/(1-perturbation-inverse_residual)+1e-12 if perturbation+inverse_residual<1 else float('inf')
                admissible=(roundoff_aware and np.max(np.abs(delta))<=forward_bound and
                    math.isfinite(perturbation) and perturbation<=1e-6 and inverse_residual<=1e-6 and
                    errors[0]<=determinant_bound and errors[2]<=inverse_bound and
                    errors[1]<=3*forward_bound/np.linalg.norm(expected_j))
                if not admissible:
                    raise ValueError('ASSEMBLY_FIELD_FRAME: placement lost per-cell Jacobian accuracy; '
                        +str({'cell_id':cell['id'],'relative_errors':errors,'normalized_perturbation':perturbation,
                              'absolute_delta':float(np.max(np.abs(delta))),'forward_bound':forward_bound}))
                roundoff_cells+=1;maximum_perturbation=max(maximum_perturbation,perturbation)
                maximum_inverse_residual=max(maximum_inverse_residual,inverse_residual)
            volumes.append(float(np.linalg.det(world_j)/6))
    except np.linalg.LinAlgError as exc:
        raise ValueError('ASSEMBLY_FIELD_FRAME: unrepresentable transformed cell Jacobian') from exc
    final_volume = math.fsum(volumes)
    if transform_audit is not None:
        transform_audit.update(roundoff_aware=roundoff_aware,roundoff_bounded_cells=roundoff_cells,
                               maximum_normalized_jacobian_perturbation=maximum_perturbation,
                               maximum_frobenius_condition=maximum_condition,
                               maximum_relative_volume_error=maximum_volume_error,
                               maximum_relative_inverse_error=maximum_inverse_error,
                               maximum_inverse_residual=maximum_inverse_residual)
    return transformed, matrix, final_volume


def assert_disjoint_occurrences(mesh, cell_owners, max_comparisons=250000, *, spatial_index=False):
    """Independent convex-tetra SAT; no automatic welding/contact assumption.

    A bounded sweep excludes disjoint x intervals, then exact box separations.
    SAT uses face normals and cross-edge axes. Near-zero overlaps use a reported
    relative floating tolerance; this is not an exact CAD intersection proof.
    """
    points = np.array(mesh['vertices'])
    tets = [points[cell['vertices']] for cell in mesh['cells']]
    bounds = [(tet.min(axis=0), tet.max(axis=0)) for tet in tets]
    groups = {}
    for index, owner in enumerate(cell_owners):
        groups.setdefault(owner, []).append(index)
    owner_bounds = {owner: (np.min([bounds[i][0] for i in indices], axis=0),
                             np.max([bounds[i][1] for i in indices], axis=0))
                    for owner, indices in groups.items()}
    owner_order = sorted(groups, key=lambda owner: owner_bounds[owner][0][0])

    def tree(indices):
        lower=np.min([bounds[i][0] for i in indices],axis=0)
        upper=np.max([bounds[i][1] for i in indices],axis=0)
        if len(indices)<=8:return (lower,upper,indices,None)
        axis=int(np.argmax(upper-lower));ordered=sorted(indices,key=lambda i:bounds[i][0][axis]+bounds[i][1][axis])
        mid=len(ordered)//2
        return (lower,upper,None,(tree(ordered[:mid]),tree(ordered[mid:])))

    broadphase_checks=0
    def indexed_candidates():
        # Original bounded AABB hierarchy: prune in all three axes before
        # tetra SAT. Long cavity walls defeated the former x-only sweep.
        nonlocal broadphase_checks
        trees={}
        for offset,left in enumerate(owner_order):
            for right in owner_order[offset+1:]:
                lo,hi=owner_bounds[left],owner_bounds[right]
                if np.any(np.maximum(lo[0],hi[0])>=np.minimum(lo[1],hi[1])):continue
                for owner in (left,right):
                    if owner not in trees:trees[owner]=tree(groups[owner])
                pending=[(trees[left],trees[right])]
                while pending:
                    a,b=pending.pop();broadphase_checks+=1
                    if broadphase_checks>max_comparisons*64:
                        raise ValueError('ASSEMBLY_FIELD_WORK: spatial hierarchy work budget exceeded')
                    if np.any(np.maximum(a[0],b[0])>=np.minimum(a[1],b[1])):continue
                    if a[2] is not None and b[2] is not None:
                        for i in a[2]:
                            for j in b[2]:
                                if not np.any(np.maximum(bounds[i][0],bounds[j][0])>=np.minimum(bounds[i][1],bounds[j][1])):
                                    yield i,j
                    elif b[2] is not None or (a[2] is None and np.prod(a[1]-a[0])>=np.prod(b[1]-b[0])):
                        pending.extend((child,b) for child in a[3])
                    else:pending.extend((a,child) for child in b[3])

    def candidates():
        # First prune entire separated occurrences, including y/z separation.
        # A two-colour active sweep then yields only cross-occurrence pairs;
        # dense same-body meshes neither scan each other nor consume budget.
        for offset, left in enumerate(owner_order):
            for right in owner_order[offset+1:]:
                lo, hi = owner_bounds[left], owner_bounds[right]
                if hi[0][0] >= lo[1][0]:
                    break
                if np.any(np.maximum(lo[0], hi[0]) >= np.minimum(lo[1], hi[1])):
                    continue
                events = sorted([(bounds[i][0][0], 0, i) for i in groups[left]] +
                                [(bounds[i][0][0], 1, i) for i in groups[right]])
                active = [set(), set()]
                ends = [[], []]
                for x, side, index in events:
                    for colour in (0, 1):
                        while ends[colour] and ends[colour][0][0] <= x:
                            _, expired = heapq.heappop(ends[colour])
                            active[colour].remove(expired)
                    for other in sorted(active[1-side]):
                        yield index, other
                    active[side].add(index)
                    heapq.heappush(ends[side], (bounds[index][1][0], index))

    comparisons = 0
    for a, b in (indexed_candidates() if spatial_index else candidates()):
        comparisons += 1
        if comparisons > max_comparisons:
            raise ValueError('ASSEMBLY_FIELD_WORK: intersection comparison budget exceeded')
        if np.any(np.maximum(bounds[a][0],bounds[b][0]) >= np.minimum(bounds[a][1],bounds[b][1])):
            continue
        scale = max(np.ptp(np.vstack((tets[a],tets[b])), axis=0))
        p, q = (tets[a]-tets[a][0])/scale, (tets[b]-tets[a][0])/scale
        edges = lambda t: [t[j]-t[i] for i,j in itertools.combinations(range(4),2)]
        axes = [np.cross(t[j]-t[i],t[k]-t[i]) for t in (p,q) for i,j,k in itertools.combinations(range(4),3)]
        axes.extend(np.cross(e,f) for e in edges(p) for f in edges(q))
        separated = False
        for axis in axes:
            length = np.linalg.norm(axis)
            if length == 0:
                continue
            u, v = p@(axis/length), q@(axis/length)
            if min(max(u),max(v))-max(min(u),min(v)) <= 1e-12:
                separated = True
                break
        if not separated:
            raise ValueError('ASSEMBLY_FIELD_OVERLAP: occurrence volumes intersect; supply repaired nonoverlapping geometry')
    audit={'inter_occurrence_comparisons': comparisons, 'relative_sat_tolerance': 1e-12,
           'within_occurrence_global_intersection_check': False}
    if spatial_index:audit.update(spatial_index=True,broadphase_node_checks=broadphase_checks)
    return audit
