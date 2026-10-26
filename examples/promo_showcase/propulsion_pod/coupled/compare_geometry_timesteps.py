# SPDX-License-Identifier: Apache-2.0
"""Observe timestep changes between two source-identical completed pod runs.

This is a two-resolution comparison, not an error bound or qualification gate.
Controller sampling remains fixed; only integration dt and wall budget may vary.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def compare(coarse, fine):
    for run in (coarse, fine):
        if run.get('contract') != 'spike/geometry-propulsion-loop-result/v1' or run.get('status') != 'completed':
            raise ValueError('Two completed geometry loop results required')
        if run.get('physical_load_qualified') is not False or run.get('production_qualified') is not False:
            raise ValueError('Comparison does not admit physical qualification claims')
    identities = ('field_table_sha256', 'fluid_port_sha256', 'controller_source_sha256', 'orchestrator_sha256')
    for key in identities:
        value = coarse.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value) or value != fine.get(key):
            raise ValueError('Different or missing constitutive/controller identity: '+key)
    requests = [json.loads(json.dumps(run['request'], allow_nan=False)) for run in (coarse, fine)]
    dt = [request['transient'].pop('time_step_s') for request in requests]
    for request in requests:
        request['transient'].pop('wall_budget_s', None)
    if requests[0] != requests[1]:
        raise ValueError('Initial conditions, drive, shaft, thermal and controller setup must match')
    if not all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in dt):
        raise ValueError('Positive finite timesteps required')
    ratio = round(dt[0]/dt[1])
    if ratio < 2 or abs(ratio*dt[1]-dt[0]) > 32*np.finfo(float).eps*dt[0]:
        raise ValueError('Fine timestep must integrally subdivide the coarse timestep')
    histories = [run['history'] for run in (coarse, fine)]
    duration = requests[0]['transient']['duration_s']
    for run, rows, step in zip((coarse, fine), histories, dt):
        count = run['accepted_steps']
        if type(count) is not int or not 1 <= count <= 20000 or len(rows) != count+1:
            raise ValueError('Completed bounded histories required')
        if abs(count*step-duration) > 32*np.finfo(float).eps*max(duration, step):
            raise ValueError('History does not cover the requested duration')
        for index, row in enumerate(rows):
            if not math.isfinite(row['time_s']) or abs(row['time_s']-index*step) > 32*np.finfo(float).eps*max(duration, step):
                raise ValueError('Uniform accepted endpoint grid required')
    if len(histories[1]) != ratio*(len(histories[0])-1)+1:
        raise ValueError('Aligned time histories required')
    aligned = histories[1][::ratio]
    units = {'currents_a': ('A', 3), 'speed_rad_s': ('rad/s', 1),
             'angle_rad': ('rad', 1), 'temperature_k': ('K', 11),
             'field_torque_n_m': ('N m', 1), 'flux_coordinates_wb_turn': ('Wb turn', 2)}
    differences = {}
    for key, (unit, width) in units.items():
        values = [np.asarray([row[key] for row in rows], dtype=float).reshape(len(histories[0]), -1)
                  for rows in (histories[0], aligned)]
        if any(value.shape[1] != width or not np.isfinite(value).all() for value in values):
            raise ValueError('Invalid endpoint observable: '+key)
        delta = values[0]-values[1]
        differences[key] = {'unit': unit, 'maximum_absolute_change': float(np.max(np.abs(delta))),
                            'rms_change': float(np.sqrt(np.mean(delta*delta))),
                            'endpoint_change': delta[-1].tolist()}
    energy = {}
    if set(coarse['energy']) != set(fine['energy']):
        raise ValueError('Different energy ledger fields')
    for key in coarse['energy']:
        a, b = coarse['energy'][key], fine['energy'][key]
        if not all(type(value) in (int, float) and math.isfinite(value) for value in (a, b)):
            raise ValueError('Finite energy totals required')
        energy[key] = {'unit': 'J', 'coarse_minus_fine': a-b}
    return {'contract': 'spike/geometry-pod-timestep-comparison/v1',
            'physical_qualified': False, 'production_qualified': False,
            'source_identities': {key: coarse[key] for key in identities},
            'time_steps_s': dt, 'subdivision_ratio': ratio, 'common_endpoint_count': len(aligned),
            'controller_period_s': requests[0]['transient']['controller_period_s'],
            'endpoint_observables': differences, 'cumulative_energy': energy,
            'scope': 'Observed two-grid changes at common accepted endpoints; no true-error bound, convergence order or hardware qualification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('coarse', 'fine', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Existing evidence is not overwritten')
    blobs = [path.read_bytes() for path in (args.coarse, args.fine)]
    result = compare(*[json.loads(blob) for blob in blobs])
    result['input_file_sha256'] = dict(zip(('coarse', 'fine'), [hashlib.sha256(blob).hexdigest() for blob in blobs]))
    result['comparison_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'output': str(args.output.resolve()), 'common_endpoint_count': result['common_endpoint_count']}))


if __name__ == '__main__':
    main()
