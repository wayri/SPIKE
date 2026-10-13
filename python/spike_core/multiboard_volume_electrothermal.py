# SPDX-License-Identifier: Apache-2.0
"""Conservative steady native MNA PI/SI to retained tetra thermal feedback.

Original derivation: R(T)=Rref*(1+alpha*(T-Tref)); Pdc=VI and
Pac=|Iphasor|**2*R for RMS phasors (half for peak). Cell power is
sum(weight*P), density is power/volume. No transient switching is solved.
"""
import copy
import math
import numpy as np

from .assembly_field_handoff import bounded_json
from .assembly_field_thermal import run_assembly_field_thermal, verify_assembly_field_result
from .multiboard_identity import assembly_physics_digest, canonical_json_digest
from .multiboard_volume_electrothermal_setup import _prepare_multiboard_volume_electrothermal
from .native_mna import run_native_mna

RESULT_CONTRACT = 'spike/multiboard-volume-electrothermal-result/v1'


def prepare_multiboard_volume_electrothermal(request):
    """JSON-safe admitted topology/volume preview without executing a solver."""
    data = _prepare_multiboard_volume_electrothermal(request)
    result = {'contract': 'spike/multiboard-volume-electrothermal-case/v1', 'status': 'ready_to_run',
              'model_status': 'experimental', 'production_qualified': False,
              'request_digest': canonical_json_digest(request),
              'assembly_digest': assembly_physics_digest(request['geometry']['assembly']),
              'geometry': data['geometry'], 'handoff': data['handoff'],
              'circuit_maps': {k: v for k, v in data['compiled'].items() if k != 'native_request'},
              'resistors': [e for e in data['compiled']['native_request']['elements'] if e['type'] == 'resistor'],
              'loss_bindings': copy.deepcopy(request['loss_bindings']), 'thermal_engine': data['thermal_engine']}
    bounded_json(result)
    return result


def _evaluate(data, temperature, native_result=None):
    native_request = copy.deepcopy(data['compiled']['native_request'])
    means = {cid: float(np.mean(temperature[c['vertices']])) for cid, c in data['cells'].items()}
    samples, resistance = {}, {}
    for eid, binding in data['bindings'].items():
        sample = math.fsum(w*means[cid] for cid, w in binding['distribution'].items())
        alpha, reference, low, high = binding['law']
        # Every receiving cell stays inside the declared law, not only its mean.
        if any(not low <= means[cid] <= high for cid in binding['distribution']):
            raise ValueError('VOLUME_COUPLING_ENVELOPE: cell temperature outside declared resistance law')
        samples[eid] = sample
        resistance[eid] = binding['reference_resistance_ohm']*(1 + alpha*(sample-reference))
        if not math.isfinite(resistance[eid]) or resistance[eid] <= 0:
            raise ValueError('VOLUME_COUPLING_LAW: nonpositive or unrepresentable resistance')
    for element in native_request['elements']:
        if element['id'] in resistance:
            element['resistance_ohm'] = resistance[element['id']]
    native = run_native_mna(native_request) if native_result is None else native_result
    if native.get('contract') != 'spike/native-mna-result/v1' or native.get('status') != 'completed':
        raise ValueError('VOLUME_COUPLING_CIRCUIT: native MNA failed: ' + str(native.get('issues', native.get('diagnostics', {}))))
    if native_result is not None:
        from .multiboard_volume_electrical_admission import verify_volume_mna_result
        verify_volume_mna_result(native_request, native)
    values = native['data']
    powers = {cid: 0. for cid in data['cells']}
    losses = []
    dc = native_request['analysis']['mode'] == 'operating_point'
    for eid, binding in data['bindings'].items():
        if dc:
            power = float(values['element_power_w'][eid])
            expected = float(values['element_current_a'][eid])**2*resistance[eid]
            if not math.isclose(power, expected, rel_tol=1e-8, abs_tol=1e-12):
                raise ValueError('VOLUME_COUPLING_LOSS: DC power disagrees with resistor current')
        else:
            if values.get('frequency_hz') != [native_request['analysis']['start_hz']]:
                raise ValueError('VOLUME_COUPLING_AC: returned frequency differs from heating frequency')
            current = values['element_current_a'][eid]
            if len(current['real']) != 1 or len(current['imaginary']) != 1:
                raise ValueError('VOLUME_COUPLING_AC: single-frequency current coverage required')
            power = data['ac_factor']*(current['real'][0]**2 + current['imaginary'][0]**2)*resistance[eid]
        if not math.isfinite(power) or power < 0:
            raise ValueError('VOLUME_COUPLING_LOSS: nonfinite or negative resistor loss')
        for cid, weight in binding['distribution'].items():
            powers[cid] += weight*power
        losses.append({'element_id': eid, 'average_power_w': power,
                       'temperature_k': samples[eid], 'resistance_ohm': resistance[eid]})
    if not all(math.isfinite(p) for p in powers.values()):
        raise ValueError('VOLUME_COUPLING_LOSS: cell heat overflow')
    return {'native_request': native_request, 'native_result': native, 'losses': losses}, powers


def _problem(request, data, powers):
    problem = copy.deepcopy(request['thermal_problem'])
    problem['heat_sources'] = [{'occurrence_id': oid, 'cell_id': local,
                                'heat_source_w_m3': powers[cid]/data['volumes'][cid]}
                               for (oid, local), cid in data['local_cells'].items()]
    return problem


def run_multiboard_volume_electrothermal(request, *, cancel_check=None):
    """Fail on unresolved topology, incomplete loss accounting or nonconvergence."""
    data = _prepare_multiboard_volume_electrothermal(request)
    options = request['iteration']
    temperature = np.full(len(data['handoff']['mesh']['vertices']), options['initial_temperature_k'], dtype=float)
    history = []

    def cancel():
        if cancel_check is not None and cancel_check():
            raise ValueError('VOLUME_COUPLING_CANCELLED: cancelled')

    for iteration in range(options['max_iterations']):
        cancel()
        _, powers = _evaluate(data, temperature)
        problem = _problem(request, data, powers)
        if data['thermal_engine'] == 'calculix':
            from .calculix_thermal import run_calculix_thermal
            thermal = run_calculix_thermal(data['geometry'], problem, data['thermal_engine_options'], cancel_check=cancel_check)
        else:
            thermal = run_assembly_field_thermal(data['geometry'], problem)
        cancel()
        target = np.asarray(thermal['field_result']['node_temperatures_k'])
        electrical, final_powers = _evaluate(data, target)
        defect = float(np.max(np.abs(target-temperature)))
        power_defect = math.fsum(abs(final_powers[cid]-powers[cid]) for cid in powers)
        relative = power_defect/max(math.fsum(powers.values()), math.fsum(final_powers.values()), 1e-30)
        history.append({'iteration': iteration+1, 'unrelaxed_temperature_defect_k': defect,
                        'power_relative_defect': relative, 'power_defect_w': power_defect,
                        'deposited_heat_w': math.fsum(powers.values())})
        if defect <= options['temperature_tolerance_k'] and relative <= options['power_relative_tolerance']:
            loss_total = math.fsum(row['average_power_w'] for row in electrical['losses'])
            deposited = math.fsum(final_powers.values())
            balance = thermal['field_result'].get('heat_balance')
            result = {'contract': RESULT_CONTRACT, 'status': 'completed', 'model_status': 'experimental',
                      'production_qualified': False, 'domain': request['circuit']['domain'],
                      'thermal_engine': data['thermal_engine'], 'request_digest': canonical_json_digest(request),
                      'assembly_digest': assembly_physics_digest(request['geometry']['assembly']),
                      'circuit_request_digest': canonical_json_digest(request['circuit']),
                      'circuit_maps': {k: v for k, v in data['compiled'].items() if k != 'native_request'},
                      'electrical': electrical, 'thermal': thermal,
                      'thermal_geometry': data['geometry'], 'thermal_problem': problem,
                      'cell_deposited_power_w': final_powers, 'thermal_applied_cell_power_w': powers,
                      'history': history, 'loss_balance': {'electrical_resistor_loss_w': loss_total,
                          'deposited_power_w': deposited, 'mapping_residual_w': deposited-loss_total,
                          'coupled_power_defect_w': power_defect,
                          'thermal_imbalance_w': balance['imbalance_w'] if balance else None,
                          'thermal_balance_status': 'reported' if balance else 'not_reported'},
                      'limitations': [
                          'Experimental native linear reduced circuit coupled to supplied steady tetra thermal volumes.',
                          'No PCB impedance extraction, full-wave fields, switching transient or nonlinear device losses.',
                          'SI uses one explicit sinusoidal frequency and RMS or peak convention; DC offsets unsupported.',
                          'Every resistor, combined link/contact resistor and electrical bond loss is explicitly mapped once.',
                          'Independent sources are ideal excitation; source-device and reactive-element losses are not modelled.',
                          'Weights also define the resistance-law temperature sample; no automatic component-to-volume mapping.',
                          'Fixed-point tolerances are iteration defects, not spatial discretization or physical accuracy bounds.',
                          'CalculiX balance is not reported; finite-precision NT temperatures can limit convergence.']}
            result['result_digest'] = canonical_json_digest(result)
            bounded_json(result)
            return result
        temperature += options['relaxation']*(target-temperature)
    raise ValueError('VOLUME_COUPLING_NONCONVERGENCE: unrelaxed temperature/power defects exceed iteration budget')


def verify_multiboard_volume_electrothermal_result(request, result):
    """Offline identity, loss coverage and thermal admission; no solver execution."""
    bounded_json(result)
    if not isinstance(result, dict) or result.get('contract') != RESULT_CONTRACT:
        raise ValueError('VOLUME_COUPLING_RESULT: unsupported result')
    if result.get('result_digest') != canonical_json_digest({k: v for k, v in result.items() if k != 'result_digest'}):
        raise ValueError('VOLUME_COUPLING_RESULT: changed result digest')
    data = _prepare_multiboard_volume_electrothermal(request)
    expected = {'request_digest': canonical_json_digest(request),
                'assembly_digest': assembly_physics_digest(request['geometry']['assembly']),
                'circuit_request_digest': canonical_json_digest(request['circuit']),
                'domain': request['circuit']['domain'], 'thermal_engine': data['thermal_engine'],
                'status': 'completed', 'model_status': 'experimental', 'production_qualified': False}
    if any(result.get(key) != value for key, value in expected.items()):
        raise ValueError('VOLUME_COUPLING_STALE: request identity or supported result status changed')
    if result.get('thermal_geometry') != data['geometry'] or result.get('circuit_maps') != {
            k: v for k, v in data['compiled'].items() if k != 'native_request'}:
        raise ValueError('VOLUME_COUPLING_RESULT: changed geometry or electrical coverage')
    applied = result.get('thermal_applied_cell_power_w')
    if not isinstance(applied, dict) or set(applied) != set(data['cells']) or any(
            type(p) not in (int, float) or not math.isfinite(p) or p < 0 for p in applied.values()):
        raise ValueError('VOLUME_COUPLING_RESULT: incomplete or invalid applied cell power')
    problem = _problem(request, data, applied)
    if result.get('thermal_problem') != problem:
        raise ValueError('VOLUME_COUPLING_RESULT: changed thermal loads')
    thermal = verify_assembly_field_result(data['geometry'], problem, result['thermal'])
    expected_thermal_contract = ('spike/calculix-thermal-result/v1' if data['thermal_engine'] == 'calculix'
                                 else 'spike/assembly-field-thermal-result/v1')
    if thermal['contract'] != expected_thermal_contract:
        raise ValueError('VOLUME_COUPLING_RESULT: thermal engine result does not match selected engine')
    target = np.asarray(thermal['field_result']['node_temperatures_k'])
    electrical, powers = _evaluate(data, target, result['electrical']['native_result'])
    if electrical != result['electrical'] or powers != result.get('cell_deposited_power_w'):
        raise ValueError('VOLUME_COUPLING_RESULT: loss binding, temperature feedback or deposited power mismatch')
    history = result.get('history')
    if not isinstance(history, list) or not 1 <= len(history) <= request['iteration']['max_iterations']:
        raise ValueError('VOLUME_COUPLING_RESULT: missing bounded convergence history')
    for index, row in enumerate(history):
        if not isinstance(row, dict) or row.get('iteration') != index+1 or any(
                type(row.get(k)) not in (int, float) or not math.isfinite(row[k]) or row[k] < 0
                for k in ('unrelaxed_temperature_defect_k', 'power_relative_defect', 'power_defect_w', 'deposited_heat_w')):
            raise ValueError('VOLUME_COUPLING_RESULT: invalid convergence history')
    last = history[-1]
    power_defect = math.fsum(abs(powers[cid]-applied[cid]) for cid in powers)
    relative = power_defect/max(math.fsum(powers.values()), math.fsum(applied.values()), 1e-30)
    if last['power_defect_w'] != power_defect or last['deposited_heat_w'] != math.fsum(applied.values()):
        raise ValueError('VOLUME_COUPLING_RESULT: last iteration load accounting changed')
    if not 0 <= last['unrelaxed_temperature_defect_k'] <= request['iteration']['temperature_tolerance_k'] or (
            relative > request['iteration']['power_relative_tolerance'] or last['power_relative_defect'] != relative):
        raise ValueError('VOLUME_COUPLING_RESULT: convergence defects inconsistent')
    loss_total = math.fsum(row['average_power_w'] for row in electrical['losses'])
    balance = thermal['field_result'].get('heat_balance')
    expected_balance = {'electrical_resistor_loss_w': loss_total, 'deposited_power_w': math.fsum(powers.values()),
                        'mapping_residual_w': math.fsum(powers.values())-loss_total,
                        'coupled_power_defect_w': power_defect,
                        'thermal_imbalance_w': balance['imbalance_w'] if balance else None,
                        'thermal_balance_status': 'reported' if balance else 'not_reported'}
    if result.get('loss_balance') != expected_balance:
        raise ValueError('VOLUME_COUPLING_RESULT: inconsistent loss balance')
    return copy.deepcopy(result)
