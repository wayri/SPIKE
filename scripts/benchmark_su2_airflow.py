# SPDX-License-Identifier: Apache-2.0
"""Run independently generated cavity cases in native SPIKE and installed SU2."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'python'))
from spike_core.native_airflow import run_native_cavity
from spike_core.su2_airflow import run_su2_airflow


def _interpolate(values, point):
    q = point * (len(values)-1)
    index = min(len(values)-2, int(q))
    return values[index] + (q-index)*(values[index+1]-values[index])


def _difference(a, b):
    delta = [x-y for x, y in zip(a, b)]
    return {'max_abs': max(map(abs, delta)), 'rms': math.sqrt(sum(v*v for v in delta)/len(delta))}


def benchmark(cells, output, *, su2_executable=None, native_executable=None, timeout_s=300):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'contract': 'spike/su2-cavity-comparison/v1', 'reynolds': 100,
              'model_status': 'experimental', 'coordinates': [i/20 for i in range(1, 20)],
              'acceptance': {'finest_centerline_max_abs': 0.03, 'require_converged': True,
                             'require_decreasing_cross_solver_error': True}, 'runs': [],
              'limitations': ['Two-dimensional isothermal laminar cavity only.',
                              'Agreement is a cross-code check, not hardware or CHT validation.',
                              'All reported differences are normalized by lid speed.']}
    for n in cells:
        native = run_native_cavity({'n': n, 'reynolds': 100}, executable=native_executable, timeout_s=timeout_s)
        su2 = run_su2_airflow({'cells': n, 'reynolds': 100, 'timeout_s': timeout_s},
                            executable=su2_executable, output_root=output / 'su2-runs')
        (output / f'native-{n}.json').write_text(json.dumps(native, indent=2, allow_nan=False), encoding='utf-8')
        (output / f'su2-{n}.json').write_text(json.dumps(su2, indent=2, allow_nan=False), encoding='utf-8')
        run = {'cells': n, 'native_status': native['status'], 'su2_status': su2['status'],
               'native_diagnostics': native['diagnostics'], 'su2_convergence': su2['convergence'],
               'native_provenance': native['provenance'], 'su2_provenance': su2['provenance']}
        if native['status'] == 'converged' and su2['status'] == 'completed':
            run['profiles'] = {'native': native['centerlines'], 'su2': {
                component+'_over_lid': [_interpolate(su2['centerlines'][component], p) for p in report['coordinates']]
                for component in ('u', 'v')}}
            run['difference'] = {component: _difference(run['profiles']['native'][component+'_over_lid'],
                                                       run['profiles']['su2'][component+'_over_lid'])
                                 for component in ('u', 'v')}
            if report['runs'] and 'profiles' in report['runs'][-1]:
                previous = report['runs'][-1]
                run['refinement_change'] = {engine: {component: _difference(
                    run['profiles'][engine][component+'_over_lid'], previous['profiles'][engine][component+'_over_lid'])
                    for component in ('u', 'v')} for engine in ('native', 'su2')}
        report['runs'].append(run)
        print(json.dumps({key: value for key, value in run.items() if key not in ('profiles', 'native_provenance', 'su2_provenance')}), flush=True)
        (output / 'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    converged = all('difference' in run for run in report['runs'])
    finest = report['runs'][-1]
    report['passed'] = (len(cells) >= 2 and converged and
        all(finest['difference'][c]['max_abs'] <= 0.03 for c in ('u', 'v')) and
        all(report['runs'][i]['difference'][c]['max_abs'] < report['runs'][i-1]['difference'][c]['max_abs']
            for i in range(1, len(cells)) for c in ('u', 'v')))
    (output / 'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cells', nargs='+', type=int, default=[16, 32, 64])
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/su2-benchmark')
    parser.add_argument('--su2-executable')
    parser.add_argument('--native-executable')
    parser.add_argument('--timeout-s', type=int, default=300)
    args = parser.parse_args()
    if args.cells != sorted(set(args.cells)) or any(n < 16 or n > 128 or n % 2 for n in args.cells):
        parser.error('--cells must contain increasing unique even values from 16 to 128')
    report = benchmark(args.cells, args.output, su2_executable=args.su2_executable,
                       native_executable=args.native_executable, timeout_s=args.timeout_s)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
