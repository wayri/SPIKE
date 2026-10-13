# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original synthetic two-fan/four-passage demonstration, not a vendor model.

Run: python examples/assembly_field/run_fan_system.py
All curve, resistance, and heat inputs are assumed analytical fixtures.
This is not a Wakefield fan curve or a SAS geometry/performance prediction.
Each passage has its own ambient inlet and two streamwise heat loads; heat
does not pass serially from one board occurrence to the next board plane.
"""
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.fan_system_operating_point import (
    REQUEST_CONTRACT, curve_digest, solve_fan_system_operating_point,
)


def _source(description, data):
    return {'reference': 'Original synthetic fixture: ' + description,
            'sha256': curve_digest(data), 'review_status': 'assumed'}


def setup_fan_system(active_count=2):
    """Return explicit data; no dimensions, real fan properties or heat inferred."""
    curve = [{'flow_m3_s': 0, 'pressure_pa': 100},
             {'flow_m3_s': .02, 'pressure_pa': 0}]
    passages = []
    for index, resistance in enumerate((1e6, 4e6, 1e6, 4e6), start=1):
        loads = []
        for site, heat in (('Q129', 2.0), ('Q10', 3.0)):
            load = {'occurrence_id': f'synthetic-Blade-{index}', 'site_id': site, 'heat_w': heat}
            loads.append({**load, 'source': _source('explicit streamwise load', load)})
        passages.append({'id': f'synthetic-passage-{index}', 'resistance_pa_s2_m6': resistance,
                         'min_flow_m3_s': .002, 'source': _source('passage resistance', resistance),
                         'heat_loads': loads})
    return {
        'contract': REQUEST_CONTRACT,
        'fan': {'model_id': 'synthetic-linear-fan-not-vendor-data', 'configuration': 'parallel',
                'installed_count': 2, 'active_count': active_count, 'curve': curve,
                'curve_sha256': curve_digest(curve), 'source': _source('single-fan pressure curve', curve)},
        'system': {'common_resistance_pa_s2_m6': 1e5,
                   'source': _source('common resistance', 1e5), 'passages': passages},
        'air': {'density_kg_m3': 1.2, 'specific_heat_j_kg_k': 1000, 'inlet_temperature_k': 300},
        'air_limits': {'min_total_flow_m3_s': .015, 'max_outlet_temperature_k': 305},
    }


def run_examples():
    summaries = []
    for active in (2, 1, 0):
        result = solve_fan_system_operating_point(setup_fan_system(active))
        point = result['operating_point']
        assert result['not_resolved_CFD'] and not result['board_convection_inferred']
        if active:
            # Independent derivation: gsum=.003; Kparallel=1/.003^2.
            # 100-(5000/active)Q=(1e5+1/.003^2)Q^2.
            k, slope = 1e5 + 1 / .003**2, 5000 / active
            expected_flow = 200 / (slope + math.sqrt(slope**2 + 400 * k))
            assert abs(point['total_flow_m3_s'] - expected_flow) < 1e-12
            assert abs(result['air_summary']['energy_residual_w']) < 1e-8
            assert abs(point['pressure_residual_pa']) <= point['residual_tolerance_pa']
            for passage in result['passages']:
                assert passage['stages'][0]['inlet_temperature_k'] == 300
                assert passage['stages'][1]['inlet_temperature_k'] == passage['stages'][0]['outlet_temperature_k']
        else:
            assert result['status'] == 'zero_flow_heat_failure'
            assert result['air_summary']['mixed_outlet_temperature_k'] is None
            assert not result['limits']['passed']
        summaries.append({
            'case': f'{active}-active-of-2', 'source': 'original_assumed_synthetic_fixture',
            'status': result['status'], 'model_status': result['model_status'],
            'not_resolved_CFD': result['not_resolved_CFD'],
            'board_convection_inferred': result['board_convection_inferred'],
            'request_sha256': result['request_sha256'], 'operating_point': point,
            'passages': result['passages'], 'air_summary': result['air_summary'], 'limits': result['limits'],
        })
    assert summaries[0]['limits']['passed'] and not summaries[1]['limits']['passed']
    return summaries


if __name__ == '__main__':
    print(json.dumps(run_examples(), indent=2, allow_nan=False))
