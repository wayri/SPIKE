# SPDX-License-Identifier: Apache-2.0
"""Supplied coupled pair with series R/L and node-shunt C source/load models."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from examples.rlgc_terminated_pair.run_pair import request as resistive_request
from python.spike_core.rlgc_reactive_pair import run_rlgc_reactive_pair


def request():
    raw = resistive_request(); raw["contract"] = "spike/rlgc-reactive-pair-request/v1"
    for term, inductance, capacitance in zip(raw["terminations"], (2e-9, 3e-9, 1e-9, 5e-9), (1e-12, .5e-12, 2e-12, 4e-12)):
        term.update(inductance_h=inductance, capacitance_f=capacitance)
    return raw


if __name__ == "__main__":
    print(json.dumps(run_rlgc_reactive_pair(request()), allow_nan=False))
