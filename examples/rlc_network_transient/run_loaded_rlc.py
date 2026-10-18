# SPDX-License-Identifier: Apache-2.0
"""Original R/L Thevenin drive into a resistor network with shunt capacitance."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def request():
    reference, load = 50., 75.
    frequencies = [0., 1., 10., 100., 1000.]
    return {'contract': 'spike/rlc-network-transient-request/v1',
            'fit_request': {'contract': 'spike/sparameter-rational-fit-request/v1',
                            'source': {'id': 'original-loaded-rlc', 'port_names': ['receiver'],
                                       'reference_impedance_ohm': reference, 'frequencies_hz': frequencies,
                                       's_parameters': [[[{'real': (load-reference)/(load+reference), 'imag': 0.}]] for _ in frequencies]},
                            'pole_rates_rad_s': [10.], 'max_absolute_error': 1e-12},
            'terminations': [{'port_name': 'receiver', 'resistance_ohm': 20., 'inductance_h': 1.,
                              'capacitance_f': .004, 'voltage_points': [
                                  {'time_s': 0., 'voltage_v': 2.}, {'time_s': 2., 'voltage_v': 2.}]}],
            'output_times_s': [0., .01, .05, .1, .2, .5, 1., 2.]}


if __name__ == '__main__':
    from python.spike_core.sparameter_rlc_terminated import run_rlc_network_transient
    result = run_rlc_network_transient(request())
    print(json.dumps({key: result[key] for key in ('contract', 'model_status', 'production_qualified',
                                                  'input_digest', 'points', 'diagnostics')}))
