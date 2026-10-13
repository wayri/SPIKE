# SPDX-License-Identifier: Apache-2.0
"""Exact retained-mesh interface discovery; geometry never implies resistance."""
import copy
import itertools
import math
import numpy as np

from .assembly_field_handoff import bounded_json, prepare_assembly_field_handoff
from .multiboard_identity import canonical_json_digest
from .spider_v2 import AssemblyIRV1


def discover_assembly_thermal_links(request, problem):
    bounded_json(problem)
    if not isinstance(problem, dict) or problem.get('contract') != 'spike/assembly-field-thermal-problem/v1':
        raise ValueError('THERMAL_AUTOLINK_FIELDS: thermal problem required')
    if not isinstance(problem.get('boundaries'), list) or not isinstance(problem.get('contacts'), list):
        raise ValueError('THERMAL_AUTOLINK_FIELDS: boundaries and contacts arrays required')
    handoff = prepare_assembly_field_handoff(request)
    faces = handoff['boundary_faces']
    if len(faces) > 20000:
        raise ValueError('THERMAL_AUTOLINK_RESOURCE: at most 20000 exterior triangles supported')
    vertices = np.asarray(handoff['mesh']['vertices'])
    # Determine outward normal from the owning tetra, independently of input ordering.
    opposite = {}
    for cell in handoff['mesh']['cells']:
        for triangle in itertools.combinations(cell['vertices'], 3):
            key = tuple(sorted(triangle))
            value = next(i for i in cell['vertices'] if i not in triangle)
            opposite[key] = value if key not in opposite else None
    occupied = {(b['face']['occurrence_id'], b['face']['face_id']) for b in problem['boundaries']}
    retained = AssemblyIRV1.from_dict(request['assembly']).thermal_contacts
    by_pair = {}
    for contact in retained:
        by_pair.setdefault(tuple(sorted((contact.endpoint_a, contact.endpoint_b))), []).append(contact)
    buckets = {}
    for face in faces:
        xyz = vertices[face['vertices']]
        signature = tuple(sorted(tuple(round(float(x), 12) for x in p) for p in xyz))
        buckets.setdefault(signature, []).append(face)
    matches, ambiguous = {}, []
    for bucket in buckets.values():
        if len({f['occurrence_id'] for f in bucket}) < 2:
            continue
        if len(bucket) != 2:
            ambiguous.append({'occurrences': sorted({f['occurrence_id'] for f in bucket}),
                              'reason': 'More than two triangles occupy an interface; review overlapping volumes.'})
            continue
        left, right = bucket
        xyz = [vertices[f['vertices']] for f in bucket]
        points = [sorted(map(tuple, x)) for x in xyz]
        if not np.allclose(points[0], points[1], rtol=0, atol=1e-12):
            continue
        normals = []
        for face, p in zip(bucket, xyz):
            other = opposite.get(tuple(sorted(face['vertices'])))
            if other is None:
                raise ValueError('THERMAL_AUTOLINK_TOPOLOGY: boundary triangle has no unique tetra owner')
            normal = np.cross(p[1]-p[0], p[2]-p[0])
            if np.dot(normal, vertices[other]-p.mean(axis=0)) > 0:
                normal *= -1
            normals.append(normal / np.linalg.norm(normal))
        if np.dot(*normals) > -1+1e-8:
            ambiguous.append({'occurrences': sorted(f['occurrence_id'] for f in bucket),
                              'reason': 'Coincident faces have nonopposing outward normals; volumes may overlap.'})
            continue
        pair = tuple(sorted((left['occurrence_id'], right['occurrence_id'])))
        matches.setdefault(pair, []).append((left, right, float(np.linalg.norm(np.cross(xyz[0][1]-xyz[0][0], xyz[0][2]-xyz[0][0]))/2)))
    proposals = []
    for pair, triangles in sorted(matches.items()):
        contacts = by_pair.get(pair, [])
        area = math.fsum(row[2] for row in triangles)*1e6
        reason = ''
        if len(contacts) != 1:
            reason = 'Retain one explicit thermal link for these endpoints and supply reviewed resistance.'
        contact = contacts[0] if len(contacts) == 1 else None
        if contact and contact.thermal_resistance_k_per_w is None:
            reason = 'Supply reviewed total thermal resistance on the retained link.'
        if contact and contact.contact_area_mm2 is not None and not math.isclose(area, contact.contact_area_mm2, rel_tol=1e-8):
            reason = 'Matched mesh area differs from retained contact area; review/remesh.'
        if any((f['occurrence_id'], f['local_face_id']) in occupied for row in triangles for f in row[:2]):
            reason = 'Interface has assigned thermal boundaries; remove conflicts before linking.'
        other_contact_faces = {(p[side]['occurrence_id'], p[side]['face_id'])
                               for c in problem['contacts'] if not contact or c.get('contact_id') != contact.id
                               for p in c['face_pairs'] for side in ('left', 'right')}
        if any((f['occurrence_id'], f['local_face_id']) in other_contact_faces for row in triangles for f in row[:2]):
            reason = 'Interface is already assigned to another contact; review conflicts before linking.'
        if len(triangles) > 256:
            reason = 'Interface exceeds 256 face-pair budget; coarsen the interface mesh.'
        proposals.append({'endpoints': list(pair), 'contact_id': contact.id if contact else None,
                          'contact_area_mm2': area, 'face_pair_count': len(triangles),
                          'thermal_resistance_k_per_w': contact.thermal_resistance_k_per_w if contact else None,
                          'status': 'needs_review' if reason else 'ready', 'reason': reason})
    unmatched = [c.id for c in retained if tuple(sorted((c.endpoint_a, c.endpoint_b))) not in matches]
    result = {'contract': 'spike/thermal-autolink-preview/v1', 'proposals': proposals,
              'ambiguous_interfaces': ambiguous, 'unmatched_contact_ids': unmatched,
              'request_digest': canonical_json_digest(request), 'problem_digest': canonical_json_digest(problem),
              'model_status': 'experimental', 'production_qualified': False,
              'limitations': ['Exact conforming coincident triangles only; proximity does not establish contact.',
                             'No resistance, glue, gap, contact pressure or material law is inferred.']}
    bounded_json(result)
    return result


def autolink_assembly_thermal_contacts(request, problem, contact_ids):
    if not isinstance(contact_ids, list) or not 1 <= len(contact_ids) <= 64 or any(
            not isinstance(c, str) for c in contact_ids) or len(set(contact_ids)) != len(contact_ids):
        raise ValueError('THERMAL_AUTOLINK_FIELDS: select 1–64 unique retained contact IDs')
    preview = discover_assembly_thermal_links(request, problem)
    ready = {p['contact_id']: p for p in preview['proposals'] if p['status'] == 'ready'}
    if not set(contact_ids) <= set(ready):
        raise ValueError('THERMAL_AUTOLINK_REVIEW: only reviewed retained matching interfaces can be linked')
    from .assembly_thermal_contact_model import prepare_assembly_thermal_contact_model
    updated = copy.deepcopy(problem)
    evidence = []
    for cid in contact_ids:
        linked = prepare_assembly_thermal_contact_model(request, updated, cid, ready[cid]['thermal_resistance_k_per_w'])
        updated = linked.pop('problem')
        evidence.append(linked)
    return {'problem': updated, 'linked_contacts': evidence, 'request_digest': preview['request_digest'],
            'original_problem_digest': preview['problem_digest'], 'model_status': 'experimental'}
