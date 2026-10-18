# SPDX-License-Identifier: Apache-2.0
"""Original charged capacitor/energized inductor free-decay example."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.rlc_network_transient.run_loaded_rlc import request as zero_request


def request():
    value = zero_request()
    value['contract'] = 'spike/rlc-network-transient-request/v2'
    for point in value['terminations'][0]['voltage_points']:
        point['voltage_v'] = 0.
    digest = hashlib.sha256(json.dumps(value['fit_request'], sort_keys=True, separators=(',', ':'),
                                      ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    value['initial_state'] = {'contract': 'spike/rlc-initial-state/v1', 'fit_request_digest': digest,
                              'fit_state_sqrt_w': [[0.]], 'inductor_current_a_by_port': {'receiver': -.02},
                              'capacitor_voltage_v_by_port': {'receiver': 1.25}}
    return value


if __name__ == '__main__':
    from python.spike_core.sparameter_rlc_initial import run_initialized_rlc_network_transient
    result = run_initialized_rlc_network_transient(request())
    print(json.dumps({key: result[key] for key in ('contract', 'model_status', 'production_qualified',
                                                  'input_digest', 'points', 'restart_state', 'diagnostics')}))
