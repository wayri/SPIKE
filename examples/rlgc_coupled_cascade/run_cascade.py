# SPDX-License-Identifier: Apache-2.0
"""Two supplied coupled sections with different impedance and loss."""
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from examples.rlgc_coupled_pair.run_pair import request as uniform_request
from python.spike_core.rlgc_coupled_cascade import run_rlgc_coupled_cascade


def request():
    original = uniform_request()
    model = {key: original[key] for key in ("conductor_ids", "modes", "probes")}
    second = deepcopy(model)
    for mode in second["modes"].values():
        mode["length_m"] = .055
        mode["inductance_h_per_m"] *= 1.4
        mode["capacitance_f_per_m"] *= .8
        for sample in mode["samples"]:
            sample["resistance_ohm_per_m"] *= 1.5
            sample["conductance_s_per_m"] *= 2
    return {"contract": "spike/rlgc-coupled-cascade-request/v1",
            "sections": [{"id": "first", "pair": model}, {"id": "second", "pair": second}],
            "excitations": original["excitations"]}


if __name__ == "__main__":
    print(json.dumps(run_rlgc_coupled_cascade(request()), allow_nan=False))
