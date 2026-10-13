# SPDX-License-Identifier: Apache-2.0
"""Offline residual and observable checks for a saved single-point MNA solve.

Reassemble A and b and evaluate A*x-b from returned node voltages and branch
currents. No linear system is solved and no external engine is executed.
"""
import cmath
import math
import numpy as np

from .native_mna import _assemble, _element_currents, _element_powers, validate_native_mna_request


def verify_volume_mna_result(request, result):
    mode = request['analysis']['mode']
    if (result.get('contract') != 'spike/native-mna-result/v1' or result.get('status') != 'completed'
            or result.get('model_status') != 'experimental' or result.get('mode') != mode
            or result.get('issues') != []):
        raise ValueError('VOLUME_COUPLING_MNA_RESULT: invalid saved circuit status or mode')
    validation = validate_native_mna_request(request)
    if not validation['valid'] or result.get('validation') != validation:
        raise ValueError('VOLUME_COUPLING_MNA_RESULT: changed circuit validation')
    frequency = request['analysis']['start_hz'] if mode == 'ac' else 0.
    matrix, rhs, nodes, branches, _ = _assemble(request, mode=mode, frequency_hz=frequency)
    values = result.get('data')
    expected_fields = {'node_voltage_v', 'branch_current_a', 'element_current_a'} | (
        {'frequency_hz', 'element_complex_power_va'} if mode == 'ac' else {'element_power_w'})
    if not isinstance(values, dict) or set(values) != expected_fields:
        raise ValueError('VOLUME_COUPLING_MNA_RESULT: incomplete observable fields')
    if mode == 'ac' and values['frequency_hz'] != [frequency]:
        raise ValueError('VOLUME_COUPLING_MNA_RESULT: changed frequency')

    def finite(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('VOLUME_COUPLING_MNA_RESULT: finite numeric samples required')
        return float(value)

    def close(actual, expected):
        if abs(actual-expected) > 1e-10*max(abs(actual), abs(expected), 1e-12):
            raise ValueError('VOLUME_COUPLING_MNA_RESULT: inconsistent derived electrical observable')

    def sample(value):
        if mode != 'ac':
            return finite(value)
        if not isinstance(value, dict) or set(value) != {'real', 'imaginary', 'magnitude', 'phase_deg'} or any(
                not isinstance(series, list) or len(series) != 1 for series in value.values()):
            raise ValueError('VOLUME_COUPLING_MNA_RESULT: one complex sample required')
        point = complex(finite(value['real'][0]), finite(value['imaginary'][0]))
        close(finite(value['magnitude'][0]), abs(point))
        close(finite(value['phase_deg'][0]), math.degrees(cmath.phase(point)))
        return point

    def table(name, identities):
        raw = values[name]
        if not isinstance(raw, dict) or set(raw) != set(identities):
            raise ValueError('VOLUME_COUPLING_MNA_RESULT: incomplete occurrence/element observable coverage')
        return {key: sample(value) for key, value in raw.items()}

    node_values = table('node_voltage_v', nodes)
    branch_values = table('branch_current_a', branches)
    solution = np.zeros(len(rhs), dtype=complex if mode == 'ac' else float)
    for node, index in nodes.items():
        solution[index] = node_values[node]
    for branch, index in branches.items():
        solution[index] = branch_values[branch]
    residual = float(np.linalg.norm(matrix @ solution-rhs)/max(np.linalg.norm(rhs), np.finfo(float).eps))
    if not math.isfinite(residual) or residual > 1e-8:
        raise ValueError('VOLUME_COUPLING_MNA_RESULT: saved voltages/currents violate circuit equations')
    currents = _element_currents(request, solution, nodes, branches, mode=mode, frequency_hz=frequency)
    saved_currents = table('element_current_a', currents)
    for eid, value in currents.items():
        close(saved_currents[eid], value)
    powers = _element_powers(request, solution, nodes, currents, ac=(mode == 'ac'))
    saved_powers = table('element_complex_power_va' if mode == 'ac' else 'element_power_w', powers)
    for eid, value in powers.items():
        close(saved_powers[eid], value)
    diagnostics = result.get('diagnostics', {})
    if diagnostics.get('points') != 1 or not 0 <= finite(diagnostics.get('relative_residual_max')) <= 1e-8:
        raise ValueError('VOLUME_COUPLING_MNA_RESULT: inconsistent circuit residual evidence')
