# SPDX-License-Identifier: Apache-2.0
"""Conservative UI authoring of uniform volumetric power on retained bodies.

The handoff admits tetra geometry and converts coordinates to SI. Uniform
q=P/V makes sum(q*V_cell)=P; it does not infer die geometry or device losses.
"""
import copy
import math

from .assembly_field_geometry import keys, number
from .assembly_tetra_thermal_validation import MAX_CELLS
from .assembly_field_handoff import bounded_json, prepare_assembly_field_handoff, text


def assign_assembly_thermal_body_power(request, problem, occurrence_id, power_w,
                                       expected_request_digest, replace_existing=False):
    bounded_json(problem)
    keys(problem, ('contract', 'boundaries', 'contacts', 'heat_sources'))
    if request.get('domain') != 'thermal' or problem['contract'] != 'spike/assembly-field-thermal-problem/v1':
        raise ValueError('ASSEMBLY_BODY_POWER_CONTRACT: thermal geometry and problem required')
    power = number(power_w)
    if power < 0 or type(replace_existing) is not bool:
        raise ValueError('ASSEMBLY_BODY_POWER_INPUT: nonnegative watts and explicit boolean replacement required')
    handoff = prepare_assembly_field_handoff(request)
    if handoff['request_digest'] != expected_request_digest:
        raise ValueError('ASSEMBLY_BODY_POWER_STALE: geometry changed; validate volumes and review power again')
    traces = {row['occurrence_id']: row for row in handoff['source_traceability']}
    oid = text(occurrence_id)
    if oid not in traces:
        raise ValueError('ASSEMBLY_BODY_POWER_BODY: select a retained meshed occurrence')
    sources = problem['heat_sources']
    if not isinstance(sources, list) or len(sources) > MAX_CELLS:
        raise ValueError(f'ASSEMBLY_BODY_POWER_LIMIT: at most {MAX_CELLS} source cells supported')
    seen, preserved, existing = set(), [], 0
    for source in sources:
        keys(source, ('occurrence_id', 'cell_id', 'heat_source_w_m3'))
        owner, cell = text(source['occurrence_id']), text(source['cell_id'])
        if owner not in traces or cell not in traces[owner]['cell_map'] or (owner, cell) in seen:
            raise ValueError('ASSEMBLY_BODY_POWER_SOURCE: unknown or duplicate existing cell source')
        number(source['heat_source_w_m3'])
        seen.add((owner, cell))
        if owner == oid:
            existing += 1
        else:
            preserved.append(copy.deepcopy(source))
    if existing and not replace_existing:
        raise ValueError('ASSEMBLY_BODY_POWER_REPLACE: explicitly replace existing sources on this body')
    trace = traces[oid]
    volume = number(trace['volume_m3'], positive=True)
    density = power / volume
    if not math.isfinite(density) or (power > 0 and density <= 0):
        raise ValueError('ASSEMBLY_BODY_POWER_RANGE: power density is unrepresentable')
    source_count = len(trace['cell_map']) if power > 0 else 0
    if len(preserved) + source_count > MAX_CELLS:
        raise ValueError(f'ASSEMBLY_BODY_POWER_LIMIT: at most {MAX_CELLS} source cells supported; use a coarser mesh')
    generated = [{'occurrence_id': oid, 'cell_id': cell, 'heat_source_w_m3': density}
                 for cell in trace['cell_map']] if power > 0 else []
    result = copy.deepcopy(problem)
    result['heat_sources'] = preserved + generated
    output = {'contract': 'spike/assembly-thermal-body-power-result/v1',
              'problem': result, 'request_digest': handoff['request_digest'],
              'occurrence_id': oid, 'power_w': power, 'volume_m3': volume,
              'heat_source_w_m3': density, 'source_cells': len(generated),
              'replaced_source_cells': existing}
    bounded_json(output)
    return output
