# SPDX-License-Identifier: Apache-2.0
"""Author a total contact resistance on already conforming occurrence faces."""
import copy
import math
import numpy as np

from .assembly_field_handoff import bounded_json, prepare_assembly_field_handoff
from .assembly_field_geometry import number
from .spider_v2 import AssemblyIRV1


def prepare_assembly_thermal_contact_model(request, problem, contact_id, thermal_resistance_k_per_w):
    bounded_json(problem)
    resistance = number(thermal_resistance_k_per_w, positive=True)
    handoff = prepare_assembly_field_handoff(request)
    retained = next((c for c in AssemblyIRV1.from_dict(request['assembly']).thermal_contacts
                     if c.id == contact_id), None)
    if retained is None:
        raise ValueError('ASSEMBLY_FIELD_CONTACT: unknown retained contact')
    if retained.thermal_resistance_k_per_w is not None and not math.isclose(
            resistance, retained.thermal_resistance_k_per_w, rel_tol=1e-8):
        raise ValueError('ASSEMBLY_FIELD_CONTACT: resistance disagrees with retained thermal link')
    vertices = np.asarray(handoff['mesh']['vertices'])
    if not isinstance(problem, dict) or problem.get('contract') != 'spike/assembly-field-thermal-problem/v1':
        raise ValueError('ASSEMBLY_FIELD_CONTACT: thermal problem required')
    if not isinstance(problem.get('contacts'), list) or not isinstance(problem.get('boundaries'), list):
        raise ValueError('ASSEMBLY_FIELD_CONTACT: contacts and boundaries arrays required')
    occupied = {(b['face']['occurrence_id'], b['face']['face_id']) for b in problem['boundaries']}
    for existing in problem['contacts']:
        if existing.get('contact_id') != contact_id:
            for pair in existing['face_pairs']:
                occupied.update((pair[side]['occurrence_id'], pair[side]['face_id']) for side in ('left', 'right'))

    def points(face):
        return sorted(tuple(float(x) for x in vertices[i]) for i in face['vertices'])

    def signature(face):
        return tuple(tuple(round(x, 12) for x in p) for p in points(face))

    right = {}
    for face in handoff['boundary_faces']:
        if face['occurrence_id'] == retained.endpoint_b:
            right.setdefault(signature(face), []).append(face)
    pairs, area = [], 0.0
    for left in handoff['boundary_faces']:
        if left['occurrence_id'] != retained.endpoint_a:
            continue
        candidates = right.get(signature(left), [])
        if not candidates:
            continue
        if len(candidates) != 1:
            raise ValueError('ASSEMBLY_FIELD_CONTACT: ambiguous coincident contact triangles')
        match = candidates[0]
        if not np.allclose(points(left), points(match), rtol=0, atol=1e-12):
            continue
        if any((f['occurrence_id'], f['local_face_id']) in occupied for f in (left, match)):
            raise ValueError('ASSEMBLY_FIELD_CONTACT: matching interface face already has a boundary or another contact')
        xyz = vertices[left['vertices']]
        area += float(np.linalg.norm(np.cross(xyz[1]-xyz[0], xyz[2]-xyz[0]))/2)
        pairs.append({'left': {'occurrence_id': retained.endpoint_a, 'face_id': left['local_face_id']},
                      'right': {'occurrence_id': retained.endpoint_b, 'face_id': match['local_face_id']}})
    if not 1 <= len(pairs) <= 256 or area <= 0:
        raise ValueError('ASSEMBLY_FIELD_CONTACT: requires 1–256 matching triangles; remesh the interface conformingly')
    if retained.contact_area_mm2 is not None and not math.isclose(area*1e6, retained.contact_area_mm2, rel_tol=1e-8):
        raise ValueError('ASSEMBLY_FIELD_CONTACT: matched face area disagrees with retained link; review or remesh')
    if not isinstance(problem, dict) or problem.get('contract') != 'spike/assembly-field-thermal-problem/v1':
        raise ValueError('ASSEMBLY_FIELD_CONTACT: thermal problem required')
    updated = copy.deepcopy(problem)
    if not isinstance(updated.get('contacts'), list):
        raise ValueError('ASSEMBLY_FIELD_CONTACT: contacts array required')
    updated['contacts'] = [c for c in updated['contacts'] if c.get('contact_id') != contact_id]
    conductance = 1/(resistance*area)
    updated['contacts'].append({'contact_id': contact_id, 'face_pairs': pairs,
                               'thermal_contact_conductance_w_m2k': conductance})
    return {'problem': updated, 'contact_id': contact_id, 'face_pair_count': len(pairs),
            'contact_area_mm2': area*1e6, 'thermal_resistance_k_per_w': resistance,
            'thermal_contact_conductance_w_m2k': conductance,
            'endpoints': [retained.endpoint_a, retained.endpoint_b]}
