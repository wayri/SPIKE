# SPDX-License-Identifier: Apache-2.0
"""Original synthetic supplied-corner PDN study; no component catalog claim."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.pdn_decap_corners import run_pdn_decap_corners


def make_request():
    provenance = {'kind': 'supplied', 'source_id': 'synthetic-corner-demonstration'}
    return {'contract': 'spike/pdn-decap-corners-request/v1',
            'base_request': {'contract': 'spike/pdn-network-request/v1', 'reference': 'GND',
                             'nodes': ['rail'], 'elements': [
                                 {'id': 'source', 'type': 'source_output_impedance',
                                  'positive': 'rail', 'negative': 'GND', 'resistance_ohm': .1,
                                  'inductance_h': 10e-9, 'provenance': provenance}],
                             'ports': [{'id': 'load', 'mode': 'single', 'positive': 'rail', 'negative': 'GND'}],
                             'frequencies_hz': [10 ** (3 + i / 40) for i in range(161)],
                             'load_transient': None},
            'corners': [{'id': 'nominal', 'bias_voltage_v': 1., 'temperature_k': 298.15},
                        {'id': 'hot-biased', 'bias_voltage_v': 3.3, 'temperature_k': 358.15}],
            'capacitors': [{'id': 'C1', 'positive': 'rail', 'negative': 'GND', 'provenance': provenance,
                            'corners': [{'corner_id': 'nominal', 'capacitance_f': 10e-6,
                                         'esr_ohm': .02, 'esl_h': 1e-9},
                                        {'corner_id': 'hot-biased', 'capacitance_f': 4e-6,
                                         'esr_ohm': .04, 'esl_h': 1.2e-9}]}],
            'target_impedance_ohm_by_port': {'load': .11}}


if __name__ == '__main__':
    request = make_request()
    result = run_pdn_decap_corners(request)
    output = ROOT / 'build/pdn-decap-corners-example'
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (('request', request), ('result', result)):
        (output / f'{name}.json').write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'meets_target': result['meets_target'], 'worst_case': result['worst_case']}, indent=2))
