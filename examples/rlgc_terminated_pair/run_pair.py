# SPDX-License-Identifier: Apache-2.0
"""Unbalanced physical source/load resistances around a supplied coupled pair."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from examples.rlgc_coupled_pair.run_pair import request as coupled_request
from python.spike_core.rlgc_terminated_pair import run_rlgc_terminated_pair


def request():
    raw = coupled_request()
    return {"contract": "spike/rlgc-terminated-pair-request/v1",
        "pair": {key: raw[key] for key in ("conductor_ids", "modes", "probes")},
        "terminations": [{"id": name, "port": port, "resistance_ohm": resistance}
            for port, name, resistance in ((0, "source_P", 25.), (1, "source_N", 75.), (2, "load_P", 50.), (3, "load_N", 120.))],
        "sources": [{"frequency_hz": drive["frequency_hz"], "voltage_v": [
            {"real": 1., "imag": 0.}, {"real": 0., "imag": .4}, {"real": 0., "imag": 0.}, {"real": .2, "imag": -.1}]}
            for drive in raw["excitations"]]}


if __name__ == "__main__":
    print(json.dumps(run_rlgc_terminated_pair(request()), allow_nan=False))
