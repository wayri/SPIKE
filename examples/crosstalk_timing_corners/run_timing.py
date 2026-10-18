# SPDX-License-Identifier: Apache-2.0
"""Original finite nominal/late-clock/early-data timing-corner example."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from examples.multi_aggressor_crosstalk.run_crosstalk import request as crosstalk_request


def request():
    return {'contract': 'spike/crosstalk-timing-corners-request/v1',
            'crosstalk_request': crosstalk_request(),
            'timing_corners': [
                {'id': 'nominal', 'delay_s_by_port': {'clock': 0., 'data': 0.}},
                {'id': 'clock-late', 'delay_s_by_port': {'clock': .1, 'data': 0.}},
                {'id': 'data-early', 'delay_s_by_port': {'clock': 0., 'data': -.2}}]}


if __name__ == '__main__':
    from python.spike_core.service import handle
    response = handle({'method': 'run_crosstalk_timing_corners', 'params': {'request': request()}})
    if not response['ok']:
        raise RuntimeError(response)
    print(json.dumps(response['result'], allow_nan=False))
