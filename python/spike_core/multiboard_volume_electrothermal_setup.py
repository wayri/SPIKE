# SPDX-License-Identifier: Apache-2.0
"""Admission for explicitly mapped reduced-circuit losses in retained solids."""
import copy
import json
import math
import numpy as np

from .assembly_field_geometry import keys, number
from .assembly_field_handoff import bounded_json, text
from .assembly_field_thermal import bind_assembly_field_thermal
from .multiboard_circuit import compile_multiboard_circuit
from .multiboard_identity import assembly_physics_digest
from .spider_v2 import AssemblyIRV1

REQUEST_CONTRACT = 'spike/multiboard-volume-electrothermal-request/v1'


def _prepare_multiboard_volume_electrothermal(request):
    bounded_json(request)
    keys(request, ('contract', 'geometry', 'thermal_problem', 'circuit', 'loss_bindings',
                   'iteration', 'loss_accounting'), ('thermal_engine', 'thermal_engine_options', 'ac_heating'))
    if request['contract'] != REQUEST_CONTRACT or request['loss_accounting'] != 'exhaustive_resistor_losses':
        raise ValueError('VOLUME_COUPLING_CONTRACT: explicit exhaustive resistor loss accounting required')
    circuit = request['circuit']
    compiled = compile_multiboard_circuit(circuit)
    geometry = copy.deepcopy(request['geometry'])
    if assembly_physics_digest(geometry['assembly']) != assembly_physics_digest(circuit['assembly']):
        raise ValueError('VOLUME_COUPLING_IDENTITY: electrical and thermal assemblies differ')
    # Compile and exhaustively bind links before removing their thermal-only
    # unsupported flags. The original assembly is retained in the parent digest.
    if any(m.get('kind') != 'connector-mate' for m in geometry['assembly'].get('connector_mappings', [])):
        raise ValueError('VOLUME_COUPLING_LINK: unsupported connector mapping')
    for field in ('harnesses', 'connector_mappings', 'electrical_bonds'):
        geometry['assembly'][field] = []
    geometry['assembly'] = AssemblyIRV1.from_dict(geometry['assembly']).to_dict()
    geometry['assembly'].get('extensions', {}).pop('spike.multiboard-studies', None)
    # Dataclass frame transforms may be tuples; public/persisted JSON uses lists.
    geometry = json.loads(json.dumps(geometry, allow_nan=False))
    if request['thermal_problem'].get('heat_sources') != []:
        raise ValueError('VOLUME_COUPLING_LOSS: background volumetric heating would duplicate mapped circuit losses')
    handoff, _, _, _ = bind_assembly_field_thermal(geometry, request['thermal_problem'])
    native = compiled['native_request']
    allowed = {'resistor', 'capacitor', 'inductor', 'voltage_source', 'current_source'}
    if any(e['type'] not in allowed for e in native['elements']):
        raise ValueError('VOLUME_COUPLING_DEVICE: active/controlled and nonlinear loss models unsupported')
    analysis = native['analysis']
    if circuit['domain'] == 'pi' and analysis['mode'] != 'operating_point':
        raise ValueError('VOLUME_COUPLING_ANALYSIS: PI requires DC operating point')
    factor = 1.
    if circuit['domain'] == 'si':
        heating = request.get('ac_heating')
        keys(heating, ('frequency_hz', 'phasor_convention'))
        frequency = number(heating['frequency_hz'], positive=True)
        if analysis.get('points') != 1 or analysis.get('start_hz') != frequency or analysis.get('stop_hz') != frequency:
            raise ValueError('VOLUME_COUPLING_AC: one explicitly selected heating frequency required')
        if heating['phasor_convention'] not in ('rms', 'peak'):
            raise ValueError('VOLUME_COUPLING_AC: explicit rms or peak phasor convention required')
        factor = 1. if heating['phasor_convention'] == 'rms' else .5
        if any(e.get('dc_value', e.get('value', 0)) != 0 for e in native['elements']
               if e['type'] in ('voltage_source', 'current_source')):
            raise ValueError('VOLUME_COUPLING_AC: nonzero DC offsets require a separate combined-loss model')
    elif 'ac_heating' in request:
        raise ValueError('VOLUME_COUPLING_AC: AC heating applies only to SI')
    engine = request.get('thermal_engine', 'internal')
    engine_options = request.get('thermal_engine_options', {})
    if engine == 'calculix':
        from .calculix_runtime import validate_calculix_options
        engine_options = validate_calculix_options(engine_options)
    elif engine != 'internal' or engine_options != {}:
        raise ValueError('VOLUME_COUPLING_ENGINE: internal or calculix with validated options required')
    options = request['iteration']
    keys(options, ('initial_temperature_k', 'max_iterations', 'relaxation',
                   'temperature_tolerance_k', 'power_relative_tolerance'))
    number(options['initial_temperature_k'], positive=True)
    if type(options['max_iterations']) is not int or not 1 <= options['max_iterations'] <= 50:
        raise ValueError('VOLUME_COUPLING_ITERATION: iteration budget is 1 through 50')
    if not 0 < number(options['relaxation']) <= 1:
        raise ValueError('VOLUME_COUPLING_ITERATION: relaxation must be in (0,1]')
    number(options['temperature_tolerance_k'], positive=True)
    number(options['power_relative_tolerance'], positive=True)
    local_cells = {(t['occurrence_id'], local): global_id for t in handoff['source_traceability']
                   for local, global_id in t['cell_map'].items()}
    cells = {c['id']: c for c in handoff['mesh']['cells']}
    volumes = {}
    for cid, cell in cells.items():
        xyz = np.asarray([handoff['mesh']['vertices'][i] for i in cell['vertices']])
        volumes[cid] = float(np.linalg.det((xyz[1:] - xyz[0]).T) / 6)
    resistors = {e['id']: e for e in native['elements'] if e['type'] == 'resistor'}
    bindings = request['loss_bindings']
    if not isinstance(bindings, list) or len(bindings) != len(resistors) or not resistors:
        raise ValueError('VOLUME_COUPLING_LOSS: bind every compiled resistor exactly once')
    admitted = {}
    for entry in bindings:
        keys(entry, ('element_id', 'distribution', 'temperature_law'))
        eid = text(entry['element_id'])
        if eid not in resistors or eid in admitted:
            raise ValueError('VOLUME_COUPLING_LOSS: unknown or duplicate resistor loss')
        law = entry['temperature_law']
        keys(law, ('temperature_coefficient_per_k', 'reference_temperature_k', 'temperature_range_k'))
        alpha = number(law['temperature_coefficient_per_k'])
        reference = number(law['reference_temperature_k'], positive=True)
        limits = law['temperature_range_k']
        if not isinstance(limits, list) or len(limits) != 2:
            raise ValueError('VOLUME_COUPLING_LAW: bounded temperature range required')
        low, high = [number(t, positive=True) for t in limits]
        if not low <= reference <= high or low == high or any(
                not math.isfinite(1 + alpha*(t-reference)) or 1 + alpha*(t-reference) <= 0 for t in limits):
            raise ValueError('VOLUME_COUPLING_LAW: positive resistance required throughout envelope')
        rows = entry['distribution']
        if not isinstance(rows, list) or not 1 <= len(rows) <= len(cells):
            raise ValueError('VOLUME_COUPLING_LOSS: bounded nonempty cell distribution required')
        distribution = {}
        for row in rows:
            keys(row, ('occurrence_id', 'cell_id', 'weight'))
            cid = local_cells.get((text(row['occurrence_id']), text(row['cell_id'])))
            if cid is None or cid in distribution:
                raise ValueError('VOLUME_COUPLING_LOSS: unknown or duplicate occurrence cell')
            distribution[cid] = number(row['weight'], positive=True)
        if not math.isclose(math.fsum(distribution.values()), 1., rel_tol=0, abs_tol=1e-12):
            raise ValueError('VOLUME_COUPLING_LOSS: distribution weights must sum to one')
        admitted[eid] = {'distribution': distribution, 'law': (alpha, reference, low, high),
                         'reference_resistance_ohm': resistors[eid]['resistance_ohm']}
    return {'compiled': compiled, 'geometry': geometry, 'handoff': handoff, 'cells': cells,
            'local_cells': local_cells, 'volumes': volumes, 'bindings': admitted,
            'thermal_engine': engine, 'thermal_engine_options': engine_options, 'ac_factor': factor}
