# SPDX-License-Identifier: Apache-2.0
"""Physical RLC terminations for three supplied coupled branches."""
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from examples.rlgc_coupled_star.run_star import request as branch_request
from examples.rlgc_reactive_pair.run_pair import request as endpoint_request
from python.spike_core.rlgc_loaded_star import run_rlgc_loaded_star


def request():
    branches, ends = branch_request(), endpoint_request()
    terms=deepcopy(ends["terminations"])
    terms += [{**deepcopy(terms[k]),"id":"branch-"+str(k),"port":k+4} for k in range(2)]
    return {"contract":"spike/rlgc-loaded-star-request/v1","legs":branches["legs"],"terminations":terms,
        "sources":[{"frequency_hz":s["frequency_hz"],"voltage_v":s["voltage_v"]+[{"real":.2,"imag":.1},{"real":0.,"imag":-.1}]} for s in ends["sources"]]}


if __name__=="__main__":
    print(json.dumps(run_rlgc_loaded_star(request()),allow_nan=False))
