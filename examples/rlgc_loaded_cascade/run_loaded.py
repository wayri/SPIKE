# SPDX-License-Identifier: Apache-2.0
"""Physical R/L/C sources and loads around two coupled sections."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from examples.rlgc_coupled_cascade.run_cascade import request as sections_request
from examples.rlgc_reactive_pair.run_pair import request as terminal_request
from python.spike_core.rlgc_loaded_cascade import run_rlgc_loaded_cascade


def request():
    return {"contract":"spike/rlgc-loaded-cascade-request/v1", "sections":sections_request()["sections"],
            **{k:v for k,v in terminal_request().items() if k in ("terminations","sources")}}


if __name__=="__main__":
    print(json.dumps(run_rlgc_loaded_cascade(request()),allow_nan=False))
