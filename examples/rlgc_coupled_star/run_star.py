# SPDX-License-Identifier: Apache-2.0
"""Three supplied coupled branches meeting at two ideal conductor nodes."""
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from examples.rlgc_coupled_cascade.run_cascade import request as chain_request
from python.spike_core.rlgc_coupled_star import run_rlgc_coupled_star


def request():
    source=chain_request();legs=source["sections"]
    third=deepcopy(legs[0]);third["id"]="branch"
    for mode in third["pair"]["modes"].values():mode["length_m"]*=.5
    legs.append(third)
    return {"contract":"spike/rlgc-coupled-star-request/v1","legs":legs,
        "excitations":[{"frequency_hz":e["frequency_hz"],"incident_waves":e["incident_waves"]+[{"real":.2,"imag":.1},{"real":0.,"imag":-.1}]} for e in source["excitations"]]}


if __name__=="__main__":
    print(json.dumps(run_rlgc_coupled_star(request()),allow_nan=False))
