# SPDX-License-Identifier: Apache-2.0
"""Original biased two-aggressor coupled conductance/RLC example (SI units)."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def request():
    import numpy as np
    ports = ['victim', 'clock', 'data']
    conductance = np.array([[.020, -.004, -.003], [-.004, .030, -.002], [-.003, -.002, .025]])
    matrix = np.linalg.solve(np.eye(3)+50*conductance, np.eye(3)-50*conductance)
    frequencies = [0., 1., 10., 100., 1000.]
    fit = {'contract': 'spike/sparameter-rational-fit-request/v1',
           'source': {'id': 'original-biased-crosstalk', 'port_names': ports,
                      'reference_impedance_ohm': 50., 'frequencies_hz': frequencies,
                      's_parameters': [[[{'real': float(x), 'imag': 0.} for x in row] for row in matrix] for _ in frequencies]},
           'pole_rates_rad_s': [10.], 'max_absolute_error': 1e-12}
    waveforms = [[(0., 0.), (1., 0.)],
                 [(0., 0.), (.1, 2.), (.4, 2.), (.7, 0.), (1., 0.)],
                 [(0., 1.), (.2, 1.), (.5, 0.), (.8, 1.), (1., 1.)]]
    terms = [{'port_name': port, 'resistance_ohm': r, 'inductance_h': l,
              'capacitance_f': c, 'voltage_points': [{'time_s': t, 'voltage_v': v} for t, v in wave]}
             for port, r, l, c, wave in zip(ports, [50., 20., 30.], [.2, .3, .4], [.002, .003, .004], waveforms)]
    digest = hashlib.sha256(json.dumps(fit, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    source = {'contract': 'spike/rlc-network-transient-request/v2', 'fit_request': fit,
              'terminations': terms, 'output_times_s': [0., .05, .1, .2, .35, .5, .7, .8, 1.],
              'initial_state': {'contract': 'spike/rlc-initial-state/v1', 'fit_request_digest': digest,
                                'fit_state_sqrt_w': [[0., 0., 0.]],
                                'inductor_current_a_by_port': dict.fromkeys(ports, 0.),
                                'capacitor_voltage_v_by_port': dict.fromkeys(ports, 0.)}}
    return {'contract': 'spike/multi-aggressor-crosstalk-request/v1', 'transient_request': source,
            'victim_port': 'victim', 'aggressors': [{'port_name': 'data', 'reference_voltage_v': .5},
                                                 {'port_name': 'clock', 'reference_voltage_v': 1.}],
            'lower_limit_v': -.02, 'upper_limit_v': .3}


if __name__ == '__main__':
    from python.spike_core.service import handle
    response = handle({'method': 'run_multi_aggressor_crosstalk', 'params': {'request': request()}})
    if not response['ok']:
        raise RuntimeError(response)
    print(json.dumps(response['result'], allow_nan=False))
