# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Three-level refinement evidence for the fan thermal fixture.

This evaluates supplied metrics, not files or CFD. Hash identities bind the
comparison metadata but their authenticity must be verified by the caller.
Richardson estimates assume a single leading error power, not proven asymptotia.
"""
from __future__ import annotations

import math
import re

from scipy.optimize import brentq


class RefinementStudyError(ValueError):
    """Invalid or incomparable supplied refinement evidence."""


def _require(condition, code):
    if not condition:
        raise RefinementStudyError(code)


def _number(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    _require(valid, 'REFINEMENT_NONFINITE_OR_UNTYPED')
    return float(value)


def evaluate_refinement_study(request):
    """Compare exactly three independently identified coarse-to-fine runs.

Mesh studies hold timestep fixed; time studies hold mesh size fixed. All runs
must report the same observable at the same physical time, reference temperature,
geometry, materials and heat sources. Near-identical values do not prove order.
"""
    _require(isinstance(request, dict) and set(request) == {'contract', 'axis', 'levels'},
             'REFINEMENT_CONTRACT_FIELDS')
    _require(request['contract'] == 'spike/openfoam-refinement-study/v1' and
             request['axis'] in ('mesh', 'time'), 'REFINEMENT_UNSUPPORTED')
    levels = request['levels']
    _require(isinstance(levels, list) and len(levels) == 3, 'REFINEMENT_THREE_LEVELS_REQUIRED')
    hashes = ('case_sha256', 'result_sha256', 'geometry_sha256', 'material_sha256', 'source_sha256')
    numeric = ('physical_time_s', 'h_m', 'time_step_s', 'reference_temperature_k', 'temperature_k')
    for level in levels:
        _require(isinstance(level, dict) and set(level) == set(hashes+numeric), 'REFINEMENT_LEVEL_FIELDS')
        for key in hashes:
            _require(isinstance(level[key], str) and re.fullmatch('[0-9a-f]{64}', level[key]) is not None,
                     'REFINEMENT_INVALID_HASH')
        for key in numeric:
            _require(_number(level[key]) > 0, 'REFINEMENT_NONPOSITIVE')
    for key in ('case_sha256', 'result_sha256'):
        _require(len({level[key] for level in levels}) == 3, 'REFINEMENT_STALE_EVIDENCE')
    fixed_axis = 'time_step_s' if request['axis'] == 'mesh' else 'h_m'
    for key in ('geometry_sha256', 'material_sha256', 'source_sha256', 'physical_time_s',
                'reference_temperature_k', fixed_axis):
        _require(all(level[key] == levels[0][key] for level in levels), 'REFINEMENT_INCOMPARABLE_'+key.upper())
    axis_key = 'h_m' if request['axis'] == 'mesh' else 'time_step_s'
    steps = [float(level[axis_key]) for level in levels]
    _require(steps[0] > steps[1] > steps[2], 'REFINEMENT_NOT_COARSE_TO_FINE')
    ratios = [steps[0]/steps[1], steps[1]/steps[2]]
    _require(all(math.isfinite(r) and 1.01 <= r <= 100 for r in ratios), 'REFINEMENT_INVALID_RATIO')
    rises = [level['temperature_k']-level['reference_temperature_k'] for level in levels]
    differences = [rises[0]-rises[1], rises[1]-rises[2]]
    _require(all(math.isfinite(x) for x in rises+differences), 'REFINEMENT_NONFINITE_DIFFERENCE')
    roundoff = 32*max(math.ulp(float(level['temperature_k'])) for level in levels)
    result = {'contract': 'spike/openfoam-refinement-study-result/v1', 'axis': request['axis'],
              'temperature_rises_k': rises, 'refinement_ratios': ratios,
              'successive_differences_k': differences,
              'fine_relative_change': abs(differences[1])/abs(rises[2]) if abs(rises[2]) > roundoff else None,
              'observed_order': None, 'richardson_temperature_rise_k': None,
              'estimated_fine_error_k': None, 'production_qualified': False,
              'provenance_authenticated': False,
              'physical_time_s': levels[0]['physical_time_s'],
              'reference_temperature_k': levels[0]['reference_temperature_k'],
              'geometry_sha256': levels[0]['geometry_sha256'],
              'material_sha256': levels[0]['material_sha256'],
              'source_sha256': levels[0]['source_sha256'],
              'axis_steps': steps,
              'case_sha256': [level['case_sha256'] for level in levels],
              'result_sha256': [level['result_sha256'] for level in levels]}
    if any(abs(delta) <= roundoff for delta in differences):
        result['status'] = 'indeterminate_roundoff_or_identical'
        return result
    if (differences[0] > 0) != (differences[1] > 0):
        result['status'] = 'nonmonotonic'
        return result
    measured_ratio = differences[0]/differences[1]
    # Normalize by the fine step to avoid powers of dimensional tiny lengths.
    log_r1, log_r2 = math.log(ratios[0]), math.log(ratios[1])
    def mismatch(order):
        predicted = math.exp(order*log_r2)*math.expm1(order*log_r1)/math.expm1(order*log_r2)
        return predicted-measured_ratio
    lower, upper = 0.01, 12.0
    if mismatch(lower)*mismatch(upper) > 0:
        result['status'] = 'no_supported_positive_order'
        return result
    order = brentq(mismatch, lower, upper, xtol=1e-12)
    correction = (rises[2]-rises[1])/math.expm1(order*log_r2)
    extrapolated = rises[2]+correction
    _require(math.isfinite(correction) and math.isfinite(extrapolated), 'REFINEMENT_NONFINITE_ESTIMATE')
    result.update(status='monotonic_estimate', observed_order=order,
                  richardson_temperature_rise_k=extrapolated,
                  estimated_fine_error_k=abs(correction))
    return result
