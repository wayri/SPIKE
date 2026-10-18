# SPDX-License-Identifier: Apache-2.0
"""Original 5-m lossless TEM line with finite ramp and mismatched terminations."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def request():
    return {'contract': 'spike/lossless-line-transient-request/v1', 'length_m': 5.,
            'inductance_h_per_m': 250e-9, 'capacitance_f_per_m': 100e-12,
            'left_boundary': {'resistance_ohm': 25., 'voltage_points': [
                {'time_s': 0., 'voltage_v': 0.}, {'time_s': 10e-9, 'voltage_v': 1.},
                {'time_s': 200e-9, 'voltage_v': 1.}]},
            'right_boundary': {'resistance_ohm': 100., 'voltage_points': [
                {'time_s': 0., 'voltage_v': 0.}, {'time_s': 200e-9, 'voltage_v': 0.}]},
            'probes': [{'id': 'left', 'fractional_position': 0.},
                       {'id': 'midpoint', 'fractional_position': .5},
                       {'id': 'right', 'fractional_position': 1.}],
            'output_times_s': [0., 5e-9, 10e-9, 12.5e-9, 25e-9, 30e-9, 35e-9, 50e-9, 75e-9, 100e-9, 150e-9, 200e-9]}


if __name__ == '__main__':
    from python.spike_core.service import handle
    response = handle({'method': 'run_lossless_line_transient', 'params': {'request': request()}})
    if not response['ok']:
        raise RuntimeError(response)
    print(json.dumps(response['result'], allow_nan=False))
