# SPDX-License-Identifier: Apache-2.0
"""Original charged/energized free decay with a per-port energy ledger."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.rlc_network_initial.run_free_decay import request as transient_request


def request():
    return {'contract': 'spike/rlc-energy-ledger-request/v1',
            'transient_request': transient_request(),
            'relative_tolerance': 1e-9, 'absolute_tolerance_j': 1e-10}


if __name__ == '__main__':
    from python.spike_core.sparameter_rlc_energy import run_rlc_energy_ledger
    result = run_rlc_energy_ledger(request())
    print(json.dumps({key: result[key] for key in ('contract', 'model_status', 'production_qualified',
                                                  'input_digest', 'totals', 'diagnostics')}))
