# SPDX-License-Identifier: Apache-2.0
"""Original Heaviside line: uniform attenuation and explicit local losses."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from examples.lossless_line_transient.run_line import request as line_request


def request():
    return {'contract': 'spike/distortionless-line-transient-request/v1',
            'line_request': line_request(), 'attenuation_rate_per_s': 1e7}


if __name__ == '__main__':
    from python.spike_core.service import handle
    response = handle({'method': 'run_distortionless_line_transient', 'params': {'request': request()}})
    if not response['ok']:
        raise RuntimeError(response)
    print(json.dumps(response['result'], allow_nan=False))
