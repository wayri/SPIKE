# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original reduced pressure-network and sensible-air calculation, not CFD.

For identical fans, series adds pressure and parallel adds flow. Each passive
passage obeys dp=Kj*Qj**2. Equal passage pressure gives conductance gj=1/sqrt(Kj),
Qj=Q*gj/sum(g), and Kparallel=1/sum(g)**2. Common resistance adds in series.
The continuous piecewise-linear supplied fan curve intersects this quadratic
system curve. A bounded bisection retains a sign bracket and checks both flow
resolution and the final pressure residual. No curve extrapolation is used.

Within each passage only, explicit heat increments air temperature by
heat/(rho*Qj*cp). All heat is assumed transferred to that stream: this is not
a board temperature, heat-transfer coefficient, resolved velocity, or CHT
prediction. Failed fans are removed from the ideal bank without added blockage.
Caller source digests are provenance declarations, not authenticated evidence.
"""
import copy
import hashlib
import json
import math
import re

REQUEST_CONTRACT = 'spike/fan-system-operating-point-request/v1'
RESULT_CONTRACT = 'spike/fan-system-operating-point-result/v1'
MAX_CURVE_POINTS = 4096
MAX_PASSAGES = 128
MAX_HEAT_LOADS = 1024


class FanSystemOperatingPointError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f'{code}: {message}')


def _require(condition, code, message):
    if not condition:
        raise FanSystemOperatingPointError(code, message)


def _keys(value, names, label):
    _require(isinstance(value, dict) and set(value) == set(names.split()),
             'invalid_fields', f'{label} requires exactly: {names}.')


def _text(value, label, maximum=256):
    _require(isinstance(value, str) and 0 < len(value) <= maximum and value.strip(),
             'invalid_text', f'{label} must be nonblank bounded text.')


def _number(value, label, minimum=0, maximum=1e12, positive_floor=1e-12):
    _require(type(value) in (int, float), 'invalid_number', f'{label} must be a JSON number.')
    _require(minimum <= value <= maximum and math.isfinite(value),
             'numeric_range', f'{label} is outside [{minimum}, {maximum}].')
    _require(value == 0 or value >= positive_floor, 'numeric_range',
             f'{label} nonzero values must be at least {positive_floor}.')
    return float(value)


def _source(source):
    _keys(source, 'reference sha256 review_status', 'source')
    _text(source['reference'], 'source reference', 2048)
    _require(isinstance(source['sha256'], str) and
             re.fullmatch('[0-9a-f]{64}', source['sha256']) is not None,
             'source_digest', 'Source sha256 must be 64 lowercase hexadecimal characters.')
    _require(source['review_status'] in ('reviewed', 'assumed'),
             'source_review', 'Source review_status must be reviewed or assumed.')


def curve_digest(curve):
    """Digest the exact supplied JSON numbers; 1 and 1.0 serialize differently."""
    return hashlib.sha256(json.dumps(curve, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()


def _validate(request):
    _keys(request, 'contract fan system air air_limits', 'request')
    _require(request['contract'] == REQUEST_CONTRACT, 'contract', 'Unsupported request contract.')
    fan, system, air, limits = (request[name] for name in ('fan', 'system', 'air', 'air_limits'))
    _keys(fan, 'model_id configuration installed_count active_count curve curve_sha256 source', 'fan')
    _text(fan['model_id'], 'fan model_id')
    _require(fan['configuration'] in ('series', 'parallel'), 'configuration', 'Require series or parallel.')
    _require(type(fan['installed_count']) is int and 1 <= fan['installed_count'] <= 1024,
             'fan_count', 'installed_count must be an integer in 1..1024.')
    _require(type(fan['active_count']) is int and 0 <= fan['active_count'] <= fan['installed_count'],
             'fan_count', 'active_count must be an integer in 0..installed_count.')
    _source(fan['source'])
    curve = fan['curve']
    _require(isinstance(curve, list) and 2 <= len(curve) <= MAX_CURVE_POINTS,
             'curve_budget', 'Supply 2..4096 fan curve samples; no curve is inferred.')
    previous_q, previous_p = -1.0, math.inf
    for point in curve:
        _keys(point, 'flow_m3_s pressure_pa', 'fan curve point')
        q = _number(point['flow_m3_s'], 'flow_m3_s', maximum=1e6)
        p = _number(point['pressure_pa'], 'pressure_pa')
        _require(q > previous_q and p <= previous_p, 'curve_order',
                 'Fan flow must strictly increase and pressure must not increase.')
        previous_q, previous_p = q, p
    _require(fan['curve_sha256'] == curve_digest(curve), 'curve_digest', 'Fan curve digest mismatch.')
    _keys(system, 'common_resistance_pa_s2_m6 source passages', 'system')
    _number(system['common_resistance_pa_s2_m6'], 'common resistance', maximum=1e24)
    _source(system['source'])
    passages = system['passages']
    _require(isinstance(passages, list) and 1 <= len(passages) <= MAX_PASSAGES,
             'passage_budget', 'Supply 1..128 parallel passages.')
    passage_ids, sites, load_count = set(), set(), 0
    for passage in passages:
        _keys(passage, 'id resistance_pa_s2_m6 min_flow_m3_s source heat_loads', 'passage')
        _text(passage['id'], 'passage id')
        _require(passage['id'] not in passage_ids, 'duplicate_passage', 'Passage ids must be unique.')
        passage_ids.add(passage['id'])
        _number(passage['resistance_pa_s2_m6'], 'passage resistance', 1e-12, 1e24)
        _number(passage['min_flow_m3_s'], 'passage minimum flow', maximum=1e9)
        _source(passage['source'])
        loads = passage['heat_loads']
        _require(isinstance(loads, list), 'heat_budget', 'heat_loads must be a list.')
        load_count += len(loads)
        _require(load_count <= MAX_HEAT_LOADS, 'heat_budget', 'At most 1024 heat loads are admitted.')
        for load in loads:
            _keys(load, 'occurrence_id site_id heat_w source', 'heat load')
            _text(load['occurrence_id'], 'occurrence_id')
            _text(load['site_id'], 'site_id')
            identity = (load['occurrence_id'], load['site_id'])
            _require(identity not in sites, 'duplicate_heat_site', 'An occurrence/site may contribute heat only once.')
            sites.add(identity)
            _number(load['heat_w'], 'heat_w')
            _source(load['source'])
    _keys(air, 'density_kg_m3 specific_heat_j_kg_k inlet_temperature_k', 'air')
    _number(air['density_kg_m3'], 'air density', 1e-9, 1e6)
    _number(air['specific_heat_j_kg_k'], 'air specific heat', 1e-6, 1e9)
    _number(air['inlet_temperature_k'], 'air inlet temperature', 1e-6, 1e6)
    _keys(limits, 'min_total_flow_m3_s max_outlet_temperature_k', 'air_limits')
    _number(limits['min_total_flow_m3_s'], 'minimum total flow', maximum=1e9)
    _number(limits['max_outlet_temperature_k'], 'maximum outlet temperature', 1e-6, 1e6)


def _operating_point(fan, resistance):
    active = fan['active_count']
    if active == 0:
        return 0.0, 0.0, 0.0, 0, 1e-21
    pressure_scale = active if fan['configuration'] == 'series' else 1
    flow_scale = active if fan['configuration'] == 'parallel' else 1
    samples = [(float(p['flow_m3_s']) * flow_scale,
                float(p['pressure_pa']) * pressure_scale) for p in fan['curve']]
    # A sampled endpoint remains covered when network reduction differs by a
    # handful of ulps; retain its measured residual, never extrapolate flow.
    for q, p in (samples[0], samples[-1]):
        load = resistance * q**2
        if abs(p - load) <= 8 * math.ulp(max(p, load)):
            return q, p, p - load, 0, 1e-9 * max(1e-12, p, load)
    _require(samples[0][1] - resistance * samples[0][0]**2 >= 0 and
             samples[-1][1] - resistance * samples[-1][0]**2 <= 0,
             'intersection_not_covered', 'Fan/system intersection is outside the supplied curve; no extrapolation.')
    for (q0, p0), (q1, p1) in zip(samples, samples[1:]):
        if p1 - resistance * q1**2 > 0:
            continue
        low, high = q0, q1
        for q, p in ((q0, p0), (q1, p1)):
            load = resistance * q**2
            if abs(p - load) <= 8 * math.ulp(max(p, load)):
                return q, p, p - load, 0, 1e-9 * max(1e-12, p, load)
        # Endpoint interpolation avoids intercept cancellation for steep curves.
        def pressure(q):
            fraction = (q - q0) / (q1 - q0)
            return (1 - fraction) * p0 + fraction * p1
        for iteration in range(161):
            q = low + (high - low) / 2
            p = pressure(q)
            residual = p - resistance * q**2
            tolerance = 1e-9 * max(1e-12, p, resistance * q**2)
            if residual == 0 or (abs(residual) <= tolerance and
                                  high - low <= 1e-12 * max(q, 1e-12)):
                return q, p, residual, iteration, tolerance
            if residual > 0:
                low = q
            else:
                high = q
        raise FanSystemOperatingPointError('pressure_convergence', 'Pressure residual or flow bracket did not converge.')
    raise FanSystemOperatingPointError('intersection_not_covered', 'No covered pressure intersection.')


def _passage_air(passage, flow, air, max_temperature):
    capacity = air['density_kg_m3'] * flow * air['specific_heat_j_kg_k']
    temperature = float(air['inlet_temperature_k'])
    stages = []
    for load in passage['heat_loads']:
        incoming = temperature
        if temperature is not None:
            temperature = (temperature + load['heat_w'] / capacity if capacity > 0 else
                           (temperature if load['heat_w'] == 0 else None))
        stages.append({'occurrence_id': load['occurrence_id'], 'site_id': load['site_id'],
                       'heat_w': load['heat_w'], 'inlet_temperature_k': incoming,
                       'outlet_temperature_k': temperature})
    heat = math.fsum(load['heat_w'] for load in passage['heat_loads'])
    energy_residual = None if temperature is None else capacity * (temperature - air['inlet_temperature_k']) - heat
    _require(energy_residual is None or abs(energy_residual) <= 1e-8 * max(1e-12, heat),
             'energy_resolution', 'Passage temperature resolution cannot represent its supplied heat balance.')
    return {'id': passage['id'], 'flow_m3_s': flow,
            'mass_flow_kg_s': air['density_kg_m3'] * flow,
            'inlet_temperature_k': air['inlet_temperature_k'], 'outlet_temperature_k': temperature,
            'heat_w': heat, 'energy_residual_w': energy_residual,
            'stages': stages, 'minimum_flow_passed': flow >= passage['min_flow_m3_s'],
            'maximum_outlet_temperature_passed': temperature is not None and temperature <= max_temperature}


def solve_fan_system_operating_point(request):
    """Validate a strict SI request and compute its bounded, ideal reduced model."""
    _validate(request)
    fan, system, air, limits = (request[name] for name in ('fan', 'system', 'air', 'air_limits'))
    conductance = [1 / math.sqrt(p['resistance_pa_s2_m6']) for p in system['passages']]
    conductance_sum = math.fsum(conductance)
    parallel_resistance = (system['passages'][0]['resistance_pa_s2_m6'] if len(conductance) == 1
                           else 1 / conductance_sum**2)
    resistance = parallel_resistance + system['common_resistance_pa_s2_m6']
    flow, pressure, residual, iterations, tolerance = _operating_point(fan, resistance)
    passage_results = [_passage_air(passage, flow * g / conductance_sum, air,
                                    limits['max_outlet_temperature_k'])
                       for passage, g in zip(system['passages'], conductance)]
    total_heat = math.fsum(p['heat_w'] for p in passage_results)
    capacity = air['density_kg_m3'] * flow * air['specific_heat_j_kg_k']
    mixed_outlet = (air['inlet_temperature_k'] + total_heat / capacity if flow > 0 else
                    (air['inlet_temperature_k'] if total_heat == 0 else None))
    recovered_heat = (None if mixed_outlet is None else math.fsum(
        p['mass_flow_kg_s'] * air['specific_heat_j_kg_k'] *
        (p['outlet_temperature_k'] - air['inlet_temperature_k']) for p in passage_results))
    _require(recovered_heat is None or abs(recovered_heat - total_heat) <= 1e-8 * max(1e-12, total_heat),
             'energy_resolution', 'Temperature resolution cannot represent the supplied sensible heat balance.')
    sources = [fan['source'], system['source']]
    for passage in system['passages']:
        sources.append(passage['source'])
        sources.extend(load['source'] for load in passage['heat_loads'])
    minimum_passed = flow >= limits['min_total_flow_m3_s']
    maximum_passed = all(p['maximum_outlet_temperature_passed'] for p in passage_results)
    return {
        'contract': RESULT_CONTRACT, 'status': 'zero_flow_heat_failure' if mixed_outlet is None else 'completed',
        'model_status': 'approximate', 'model_kind': 'reduced_fan_system_sensible_air',
        'flow_topology': 'parallel_passages_with_streamwise_heat_loads',
        'not_resolved_CFD': True, 'board_convection_inferred': False,
        'fan_failure_assumption': 'failed_fans_removed_without_added_blockage',
        'source_digest_authentication': 'caller_declared_not_authenticated',
        'source_review_status': 'reviewed' if all(s['review_status'] == 'reviewed' for s in sources) else 'assumed',
        'request_sha256': curve_digest(request), 'fan_model_id': fan['model_id'],
        'fan_curve_sha256': fan['curve_sha256'], 'input_snapshot': copy.deepcopy(request),
        'operating_point': {
            'total_flow_m3_s': flow, 'fan_pressure_pa': pressure,
            'system_pressure_pa': resistance * flow**2, 'pressure_residual_pa': residual,
            'residual_tolerance_pa': tolerance, 'iterations': iterations,
            'active_count': fan['active_count'], 'installed_count': fan['installed_count'],
            'configuration': fan['configuration'],
            'effective_parallel_resistance_pa_s2_m6': parallel_resistance,
            'total_resistance_pa_s2_m6': resistance,
            'passage_pressure_pa': parallel_resistance * flow**2,
            'common_pressure_pa': system['common_resistance_pa_s2_m6'] * flow**2},
        'passages': passage_results,
        'air_summary': {'total_heat_w': total_heat, 'mixed_outlet_temperature_k': mixed_outlet,
                        'energy_residual_w': None if recovered_heat is None else recovered_heat - total_heat},
        'limits': {'minimum_total_flow_passed': minimum_passed,
                   'maximum_outlet_temperature_passed': maximum_passed,
                   'passed': minimum_passed and maximum_passed and
                             all(p['minimum_flow_passed'] for p in passage_results)},
    }
