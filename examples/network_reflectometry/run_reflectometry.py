# SPDX-License-Identifier: Apache-2.0
"""Original loaded-RLC experiment probing a 75-ohm fitted-network port."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from examples.rlc_network_transient.run_loaded_rlc import request as transient_request


def request():
    source = transient_request()
    source['contract'] = 'spike/rlc-network-transient-request/v2'
    fit_digest = hashlib.sha256(json.dumps(source['fit_request'], sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    source['initial_state'] = {'contract': 'spike/rlc-initial-state/v1', 'fit_request_digest': fit_digest,
                               'fit_state_sqrt_w': [[0.]], 'inductor_current_a_by_port': {'receiver': 0.},
                               'capacitor_voltage_v_by_port': {'receiver': 0.}}
    return {'contract': 'spike/network-reflectometry-request/v1', 'transient_request': source,
            'probe_port': 'receiver', 'minimum_incident_voltage_v': 1e-9, 'minimum_current_a': 1e-12}


if __name__ == '__main__':
    from python.spike_core.service import handle
    response = handle({'method': 'run_network_reflectometry', 'params': {'request': request()}})
    if not response['ok']:
        raise RuntimeError(response)
    print(json.dumps(response['result'], allow_nan=False))
