# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original explicit geometry/material/contact admission for coupled solids."""
import copy
import math
import numpy as np

from .assembly_field_geometry import identity, keys, number
from .assembly_field_handoff import bounded_json, prepare_assembly_field_handoff, text
from .multiboard_identity import canonical_json_digest
from .spider_v2 import AssemblyIRV1


def prepare_electrothermal(request):
    bounded_json(request)
    keys(request, ('contract','geometry','thermal_problem','electrical','heat_sources','iteration','loss_accounting'),
         ('thermal_engine','thermal_engine_options'))
    if request['contract'] != 'spike/assembly-electrothermal-request/v1':
        raise ValueError('ELECTROTHERMAL_CONTRACT: unsupported coupled request')
    if request['loss_accounting'] != 'explicit_nonoverlapping_losses':
        raise ValueError('ELECTROTHERMAL_LOSSES: explicit nonoverlapping loss inventory required')
    thermal_engine = request.get('thermal_engine', 'internal')
    if thermal_engine not in ('internal', 'calculix'):
        raise ValueError('ELECTROTHERMAL_ENGINE: thermal_engine must be internal or calculix')
    engine_options = request.get('thermal_engine_options', {})
    if thermal_engine == 'calculix':
        from .calculix_runtime import validate_calculix_options
        engine_options = validate_calculix_options(engine_options)
    elif not isinstance(engine_options, dict) or engine_options:
        raise ValueError('ELECTROTHERMAL_ENGINE: thermal_engine_options require the calculix engine')
    geometry = copy.deepcopy(request['geometry'])
    assembly = AssemblyIRV1.from_dict(geometry['assembly'])
    if geometry.get('domain') != 'thermal' or any(getattr(assembly,k) for k in ('harnesses','connector_mappings','rigid_flex_links')):
        raise ValueError('ELECTROTHERMAL_CONNECTIVITY: supplied solid meshes and explicit bonds only; unrepresented links rejected')
    electrical = request['electrical']
    keys(electrical, ('materials','terminals','contacts'))
    bonds = {b.id:b for b in assembly.electrical_bonds}
    # Only bonds fully compiled below may be removed from the thermal-only
    # adapter's unsupported-link list; original assembly remains hash-bound.
    geometry['assembly']['electrical_bonds'] = []
    handoff = prepare_assembly_field_handoff(geometry)
    mesh = copy.deepcopy(handoff['mesh'])
    traces = {t['occurrence_id']:t for t in handoff['source_traceability']}
    for trace in traces.values():
        for sid in trace['source_map'].values():
            mesh['object_map'][sid]['occurrence_id'] = trace['occurrence_id']
    faces = {(f['occurrence_id'],f['local_face_id']):f for f in handoff['boundary_faces']}

    def face(value):
        keys(value, ('occurrence_id','face_id'))
        answer = faces.get((text(value['occurrence_id']),text(value['face_id'])))
        if answer is None:
            raise ValueError('ELECTROTHERMAL_FACE: unknown occurrence-scoped exterior face')
        return answer

    physical = {m['id'] for m in geometry['materials']}
    if not isinstance(electrical['materials'],list) or len(electrical['materials']) != len(physical):
        raise ValueError('ELECTROTHERMAL_MATERIAL: exact physical material coverage required')
    properties = {}
    for item in electrical['materials']:
        keys(item, ('id','conductivity_s_m','temperature_coefficient_per_k','reference_temperature_k','temperature_range_k'))
        mid = text(item['id'])
        if mid not in physical or mid in properties:
            raise ValueError('ELECTROTHERMAL_MATERIAL: unknown or duplicate material')
        sigma,alpha,reference = number(item['conductivity_s_m']),number(item['temperature_coefficient_per_k']),number(item['reference_temperature_k'],positive=True)
        limits = item['temperature_range_k']
        if sigma < 0 or not isinstance(limits,list) or len(limits) != 2:
            raise ValueError('ELECTROTHERMAL_MATERIAL: conductivity or temperature envelope invalid')
        low,high = (number(t,positive=True) for t in limits)
        denominators = [1+alpha*(t-reference) for t in (low,high)]
        if not low <= reference <= high or low == high or not all(math.isfinite(d) and d > 0 for d in denominators):
            raise ValueError('ELECTROTHERMAL_MATERIAL: positive resistance law required throughout envelope')
        properties[mid] = (sigma,alpha,reference,low,high)
    laws,local_cells = {},{}
    for body in geometry['bodies']:
        trace = traces[body['occurrence_id']]
        for cell in body['mesh']['cells']:
            cid = trace['cell_map'][cell['id']]
            laws[cid] = properties[body['material_map'][cell['material_id']]]
            local_cells[(body['occurrence_id'],cell['id'])] = cid
    if not isinstance(electrical['terminals'],list) or not 1 <= len(electrical['terminals']) <= 64:
        raise ValueError('ELECTROTHERMAL_TERMINAL: bounded explicit terminal list required')
    terminals,seen = [],set()
    for entry in electrical['terminals']:
        keys(entry, ('id','face','voltage_v'))
        tid = text(entry['id'])
        if tid in seen:
            raise ValueError('ELECTROTHERMAL_TERMINAL: duplicate terminal id')
        seen.add(tid)
        resolved = face(entry['face'])
        terminals.append({'id':tid,'vertices':resolved['vertices'],'voltage_v':number(entry['voltage_v'])})
    if not isinstance(electrical['contacts'],list) or len(electrical['contacts']) != len(bonds):
        raise ValueError('ELECTROTHERMAL_BOND: every retained bond requires one contact model')
    contacts,seen,contact_faces = [],set(),set()
    for entry in electrical['contacts']:
        keys(entry, ('bond_id','face_pairs','electrical_contact_conductance_s_m2'))
        bid = text(entry['bond_id'])
        if bid not in bonds or bid in seen:
            raise ValueError('ELECTROTHERMAL_BOND: unknown or duplicate bond')
        seen.add(bid)
        if not isinstance(entry['face_pairs'],list) or not 1 <= len(entry['face_pairs']) <= 256:
            raise ValueError('ELECTROTHERMAL_BOND: bounded matched-face pairs required')
        conductance = number(entry['electrical_contact_conductance_s_m2'],positive=True)
        area = 0.
        for index,pair in enumerate(entry['face_pairs']):
            keys(pair, ('left','right'))
            left,right = face(pair['left']),face(pair['right'])
            bond = bonds[bid]
            if (bond.endpoint_a,bond.endpoint_b) != (left['occurrence_id'],right['occurrence_id']):
                raise ValueError('ELECTROTHERMAL_BOND: retained endpoint order mismatch')
            if left['id'] == right['id'] or {left['id'],right['id']} & contact_faces:
                raise ValueError('ELECTROTHERMAL_BOND: duplicated contact faces')
            contact_faces.update((left['id'],right['id']))
            xyz = np.array([mesh['vertices'][v] for v in left['vertices']])
            area += float(np.linalg.norm(np.cross(xyz[1]-xyz[0],xyz[2]-xyz[0]))/2)
            contacts.append({'id':identity('bond',bid,index),'left_vertices':left['vertices'],'right_vertices':right['vertices'],
                             'electrical_contact_conductance_s_m2':conductance})
        if bond.contact_area_mm2 is not None and not math.isclose(area*1e6,bond.contact_area_mm2,rel_tol=1e-8):
            raise ValueError('ELECTROTHERMAL_BOND: area disagrees with retained bond')
        if bond.electrical_resistance_ohm is not None and not math.isclose(1/(conductance*area),bond.electrical_resistance_ohm,rel_tol=1e-8):
            raise ValueError('ELECTROTHERMAL_BOND: resistance disagrees with retained bond')
    if not isinstance(request['heat_sources'],list) or len(request['heat_sources']) > 128:
        raise ValueError('ELECTROTHERMAL_SOURCE: bounded loss inventory required')
    options = request['iteration']
    keys(options, ('initial_temperature_k','max_iterations','relaxation','temperature_tolerance_k','power_relative_tolerance'))
    initial = number(options['initial_temperature_k'],positive=True)
    maximum = options['max_iterations']
    if type(maximum) is not int or not 1 <= maximum <= 50 or not 0 < number(options['relaxation']) <= 1:
        raise ValueError('ELECTROTHERMAL_ITERATION: invalid bounded iteration')
    number(options['temperature_tolerance_k'],positive=True)
    number(options['power_relative_tolerance'],positive=True)
    volumes = {}
    for cell in mesh['cells']:
        xyz = np.array([mesh['vertices'][v] for v in cell['vertices']])
        volumes[cell['id']] = float(np.linalg.det((xyz[1:]-xyz[0]).T)/6)
    # Check retained thermal face ownership, contact area and R=1/(h*A)
    # before any electrical solve. No inferred package/contact resistance.
    from .assembly_field_thermal import bind_assembly_field_thermal
    bind_assembly_field_thermal(geometry, request['thermal_problem'])
    return {'geometry':geometry,'handoff':handoff,'mesh':mesh,'traces':traces,'laws':laws,'local_cells':local_cells,
            'terminals':terminals,'contacts':contacts,'volumes':volumes,'initial_temperature_k':initial,
            'original_request_digest':canonical_json_digest(request),
            'thermal_engine':thermal_engine,'thermal_engine_options':engine_options}
