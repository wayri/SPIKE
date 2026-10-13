# SPDX-License-Identifier: Apache-2.0
"""Independent finite-box electrostatic reference and retained EM refinement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.constants import epsilon_0
from scipy.sparse import diags
from scipy.sparse.linalg import cg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def laplace_solve(fixed, prescribed):
    """Solve the original seven-neighbour energy equations on a cubic grid."""
    n = fixed.shape[0]
    size = n ** 3
    # Every outer node must be prescribed, so row wrapping never enters the
    # unknown block. Unit edge weights cancel from the harmonic equations.
    assert all(np.all(np.take(fixed, i, axis=a)) for a in range(3) for i in (0, -1))
    operator = diags([np.full(size - abs(k), -1.) for k in (-n*n, -n, -1)]
                     + [np.full(size, 6.)]
                     + [np.full(size - k, -1.) for k in (1, n, n*n)],
                     [-n*n, -n, -1, 0, 1, n, n*n], format='csr')
    free = np.flatnonzero(~fixed.ravel())
    potential = prescribed.copy().ravel()
    rhs = -(operator @ potential)[free]
    reduced = operator[free][:, free]
    solution, status = cg(reduced, rhs, rtol=1e-10, atol=0., maxiter=3000)
    if status:
        raise RuntimeError(f'Electrostatic CG failed: {status}')
    potential[free] = solution
    residual = float(np.linalg.norm(reduced @ solution-rhs) / np.linalg.norm(rhs))
    return potential.reshape(fixed.shape), residual


def conductor_charge(potential, electrode, spacing):
    """Outward displacement flux; each vacuum grid edge has epsilon_0*h F."""
    charge = 0.
    for axis in range(3):
        first = [slice(None)] * 3
        second = [slice(None)] * 3
        first[axis] = slice(None, -1)
        second[axis] = slice(1, None)
        first, second = tuple(first), tuple(second)
        jump = potential[first] - potential[second]
        charge += np.sum(jump * (electrode[first].astype(int)-electrode[second].astype(int)))
    return float(epsilon_0 * spacing * charge)


def static_reference(subdivisions_per_mm, return_potential=False):
    """Finite 14 mm cavity with two original 10x10x1 mm electrodes."""
    m = subdivisions_per_mm
    n = 14 * m + 1
    x, y, z = np.indices((n, n, n))
    wall = (x == 0) | (x == n-1) | (y == 0) | (y == n-1) | (z == 0) | (z == n-1)
    footprint = (x >= 2*m) & (x <= 12*m) & (y >= 2*m) & (y <= 12*m)
    electrodes = [footprint & (z >= lo*m) & (z <= hi*m) for lo, hi in ((2, 3), (6, 7))]
    fixed = wall | electrodes[0] | electrodes[1]
    matrix = np.zeros((2, 2))
    residuals = []
    potentials = []
    for column in range(2):
        potential, residual = laplace_solve(fixed, electrodes[column].astype(float))
        residuals.append(residual)
        potentials.append(potential)
        for row in range(2):
            matrix[row, column] = conductor_charge(potential, electrodes[row], .001/m)
    # Cage is the zero-potential gauge. The source transfers charge between
    # electrodes; net electrode charge is zero. V_signal - V_return = 1 V.
    common = -np.sum(matrix[:, 1]) / np.sum(matrix)
    voltages = np.array([common, common+1.])
    charges = matrix @ voltages
    report = {'spacing_m': .001/m, 'nodes': n**3,
            'max_relative_linear_residual': max(residuals),
            'maxwell_matrix_f': matrix.tolist(), 'electrode_voltages_v': voltages.tolist(),
            'net_electrode_charge_c': float(np.sum(charges)),
            'capacitance_f': float(charges[1]),
            'reciprocity_relative_error': float(abs(matrix[0, 1]-matrix[1, 0])/abs(matrix[0, 1]))}
    if return_potential:
        return report, voltages[0]*potentials[0] + voltages[1]*potentials[1]
    return report


def response(result):
    column = result['s_parameter_column'][0]
    s = np.array(column['real']) + 1j*np.array(column['imag'])
    frequencies = np.array(result['frequency_hz'])
    impedance = 50. * (1+s)/(1-s)
    admittance = 1/impedance
    return {'frequency_hz': frequencies.tolist(),
            'effective_capacitance_f': (admittance.imag/(2*np.pi*frequencies)).tolist(),
            'impedance_real_ohm': impedance.real.tolist(),
            's11_real': s.real.tolist(), 's11_imag': s.imag.tolist(),
            'stopping': result.get('stopping', {
                'execution_status': 'unknown', 'did_reach_requested_decay': None,
                'stopping_reason': 'historical_result_without_stopping_evidence'}),
            'observable_sensitivity': result.get('observable_sensitivity', {
                'status': 'not_assessed',
                'reason': 'A single execution cannot establish observable sensitivity.'})}


def assess(directory):
    """Apply declared bounded-fixture gates; never qualify unrelated geometry."""
    static = json.loads((directory/'static-reference.json').read_text())
    runs = json.loads((directory/'responses.json').read_text())
    reference = static[-1]['capacitance_f']
    def delta(left, right):
        a, b = runs[left], runs[right]
        return float(np.max(np.abs(np.array(a['s11_real'])+1j*np.array(a['s11_imag'])
                       -np.array(b['s11_real'])-1j*np.array(b['s11_imag']))))
    metrics = {
        'static_last_relative_change': abs(reference-static[-2]['capacitance_f'])/reference,
        'duration_max_complex_s11_change': delta('base', 'duration'),
        'pml_max_complex_s11_change': delta('base', 'pml-distance'),
        'fine_low_frequency_capacitance_relative_error':
            abs(runs['spatial']['effective_capacitance_f'][0]-reference)/reference,
        'spatial_low_frequency_capacitance_relative_change':
            abs(runs['spatial']['effective_capacitance_f'][0]-runs['duration']['effective_capacitance_f'][0])
            /runs['spatial']['effective_capacitance_f'][0]}
    limits = {'static_last_relative_change': .01, 'duration_max_complex_s11_change': 1e-4,
        'pml_max_complex_s11_change': 1e-4, 'fine_low_frequency_capacitance_relative_error': .05,
        'spatial_low_frequency_capacitance_relative_change': .075}
    observable_sensitivity = {
        'duration': {'status': 'accepted' if metrics['duration_max_complex_s11_change'] <= limits['duration_max_complex_s11_change'] else 'rejected',
            'metric': 'duration_max_complex_s11_change',
            'value': metrics['duration_max_complex_s11_change'],
            'limit': limits['duration_max_complex_s11_change']},
        'pml-distance': {'status': 'accepted' if metrics['pml_max_complex_s11_change'] <= limits['pml_max_complex_s11_change'] else 'rejected',
            'metric': 'pml_max_complex_s11_change',
            'value': metrics['pml_max_complex_s11_change'],
            'limit': limits['pml_max_complex_s11_change']},
        'spatial': {'status': 'accepted' if metrics['spatial_low_frequency_capacitance_relative_change'] <= limits['spatial_low_frequency_capacitance_relative_change'] else 'rejected',
            'metric': 'spatial_low_frequency_capacitance_relative_change',
            'value': metrics['spatial_low_frequency_capacitance_relative_change'],
            'limit': limits['spatial_low_frequency_capacitance_relative_change']}}
    metric_aliases = {}
    if 'spatial-duration' in runs:
        metrics['fine_duration_max_complex_s11_change'] = delta('spatial', 'spatial-duration')
        limits['fine_duration_max_complex_s11_change'] = .001
        metrics['duration_refined_capacitance_relative_error'] = abs(
            runs['spatial-duration']['effective_capacitance_f'][0]-reference)/reference
        limits['duration_refined_capacitance_relative_error'] = .05
        observable_sensitivity['spatial-duration'] = {
            'status': 'accepted' if metrics['fine_duration_max_complex_s11_change'] <= limits['fine_duration_max_complex_s11_change'] else 'rejected',
            'metric': 'fine_duration_max_complex_s11_change',
            'value': metrics['fine_duration_max_complex_s11_change'],
            'limit': limits['fine_duration_max_complex_s11_change']}
        metric_aliases['time_refined_capacitance_relative_error'] = {
            'canonical_metric': 'duration_refined_capacitance_relative_error',
            'value': metrics['duration_refined_capacitance_relative_error'],
            'historical_semantics': 'Duration-only comparison at fixed spatial resolution; not a timestep-refinement claim.'}
    report = {'model': 'Original finite enclosed plates; quasistatic air model only',
        'production_qualified': False, 'metrics': metrics, 'limits': limits,
        'checks': {key: value<=limits[key] for key, value in metrics.items()},
        'metric_aliases': metric_aliases,
        'stopping': {name: item.get('stopping', {
            'execution_status': 'unknown', 'did_reach_requested_decay': None,
            'stopping_reason': 'historical_result_without_stopping_evidence'})
            for name, item in runs.items()},
        'observable_sensitivity': observable_sensitivity,
        'limitations': ['Electrostatic reference neglects dynamic inductance and conductor loss.',
            'Finite-difference convergence is evidence, not a rigorous continuum error bound.',
            'No Arduino, radiation, EMC, skin-effect or general field accuracy qualification.',
            'Knowledgeable numerical human review is required before release.']}
    (directory/'validation-summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not all(report['checks'].values()):
        raise AssertionError(report['checks'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--static-only', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Preserve completed cases and retry incomplete runs')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=args.resume)
    if not (args.resume and (args.output/'static-reference.json').exists()):
        static = []
        for refinement in (2, 4, 6):
            item = static_reference(refinement)
            static.append(item)
            print(json.dumps(item), flush=True)
            (args.output/'static-reference.json').write_text(json.dumps(static, indent=2), encoding='utf-8')
    if args.static_only:
        return
    from tests.python.test_assembly_em import fixture
    from python.spike_core.assembly_em import run_assembly_em
    cases = [('base', .001, .006, 40000, 1e-6),
             ('duration', .001, .006, 80000, 1e-9),
             ('pml-distance', .001, .012, 40000, 1e-6),
             ('spatial', .0005, .006, 80000, 1e-6),
             ('spatial-duration', .0005, .006, 40000, 1e-8)]
    responses_path = args.output/'responses.json'
    responses = json.loads(responses_path.read_text()) if args.resume and responses_path.exists() else {}
    for name, edge, margin, steps, decay in cases:
        if name in responses:
            continue
        request = fixture()
        request['settings'].update(frequency_hz=[2.5e8, 3.75e8, 5e8], mesh_resolution_m=edge,
            air_margin_m=margin, max_timesteps=steps, end_criteria=decay, timeout_s=600)
        directory = args.output/name
        if directory.exists():
            directory = args.output/(name+'-retry')
        result = run_assembly_em(request, directory)
        (directory/'bound-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        (directory/'study.json').write_text(json.dumps({'contract':'spike/assembly-em-study/v1',
            'request':request,'result':result}, indent=2), encoding='utf-8')
        responses[name] = response(result)
        responses[name]['directory'] = str(directory)
        print(name, json.dumps(responses[name]), flush=True)
        (args.output/'responses.json').write_text(json.dumps(responses, indent=2), encoding='utf-8')
    assess(args.output)


if __name__ == '__main__':
    main()
