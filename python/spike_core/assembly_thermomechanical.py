# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original one-way steady thermal-to-elastic coupling on an identical mesh."""
import copy
import hashlib
import json

from .assembly_tetra_structural import run_assembly_tetra_structural
from .assembly_tetra_thermal import run_assembly_tetra_thermal


def _encoded(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError('THERMOMECHANICAL_JSON: finite JSON required') from exc


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def run_assembly_thermomechanical(request, *, cancel_check=None):
    """Execute both solvers; supplied result files are never accepted as temperatures."""
    if len(_encoded(request)) > 8 * 1024**2:
        raise ValueError('THERMOMECHANICAL_RESOURCE: request exceeds 8 MiB')
    if (not isinstance(request, dict) or set(request) != {'contract', 'thermal', 'structural'}
            or request['contract'] != 'spike/assembly-thermomechanical-request/v1'):
        raise ValueError('THERMOMECHANICAL_FIELDS: exact contract, thermal and structural required')
    raw = copy.deepcopy(request)
    input_digest = _digest(raw)
    thermal, structural = raw['thermal'], raw['structural']
    if not isinstance(thermal, dict) or not isinstance(structural, dict):
        raise ValueError('THERMOMECHANICAL_FIELDS: solver requests required')
    if 'mesh' not in thermal or _encoded(thermal['mesh']) != _encoded(structural.get('mesh')):
        raise ValueError('THERMOMECHANICAL_MESH: identical indexed mesh and ownership required')
    if 'nodal_temperatures_k' not in structural or structural['nodal_temperatures_k'] is not None:
        raise ValueError('THERMOMECHANICAL_TEMPERATURE: temperatures must come from the thermal solve')

    def check():
        if cancel_check is not None and cancel_check():
            raise ValueError('THERMOMECHANICAL_CANCELLED: no partial result')

    # Preflight structural admission before the more expensive thermal solve. This also
    # rejects rigid modes and unsupported materials before transferring any result.
    run_assembly_tetra_structural(structural, cancel_check=cancel_check)
    check()
    heat = run_assembly_tetra_thermal(thermal)
    check()
    structural['nodal_temperatures_k'] = {
        str(i): value for i, value in enumerate(heat['node_temperatures_k'])}
    mechanics = run_assembly_tetra_structural(structural, cancel_check=cancel_check)
    check()
    result = {
        'contract': 'spike/assembly-thermomechanical-result/v1',
        'model_status': 'experimental', 'production_qualified': False,
        'input_digest': input_digest, 'mesh_digest': _digest(thermal['mesh']),
        'context_digest': structural['context_digest'],
        'thermal_input_digest': _digest(thermal),
        'structural_input_digest': _digest(structural),
        'thermal': heat, 'structural': mechanics,
        'coupling': 'one_way_steady_same_mesh_temperature_to_eigenstrain',
        'limitations': [
            'No deformation feedback into heat, electrical or magnetic geometry.',
            'No contact, plasticity, fracture, fatigue, dynamics or lifetime qualification.',
            'Thermal cancellation is checked before and after its blocking solve.',
            'Context digest is supplied by the caller; no external CAD revision is queried.'],
    }
    if len(_encoded(result)) > 16 * 1024**2:
        raise ValueError('THERMOMECHANICAL_RESOURCE: result exceeds 16 MiB')
    return result
