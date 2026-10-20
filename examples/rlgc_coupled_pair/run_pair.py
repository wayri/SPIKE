# SPDX-License-Identifier: Apache-2.0
"""Supplied lossy symmetric pair with coherent physical-port excitation."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from python.spike_core.rlgc_coupled_pair import run_rlgc_coupled_pair


def request():
    frequencies = [20e6, 300e6, 1e9]
    modes = {}
    for name, inductance, capacitance, resistance, conductance in (
            ("even", 350e-9, 80e-12, 4., .0005), ("odd", 250e-9, 120e-12, 7., .0007)):
        modes[name] = {"contract": "spike/rlgc-line-network-request/v1", "length_m": .08,
            "reference_impedance_ohm": 50., "inductance_h_per_m": inductance, "capacitance_f_per_m": capacitance,
            "samples": [{"frequency_hz": f, "resistance_ohm_per_m": resistance, "conductance_s_per_m": conductance} for f in frequencies]}
    return {"contract": "spike/rlgc-coupled-pair-request/v1", "conductor_ids": ["P", "N"], "modes": modes,
        "excitations": [{"frequency_hz": f, "incident_waves": [{"real": 1., "imag": 0.}, {"real": 0., "imag": .2},
            {"real": -.3, "imag": 0.}, {"real": .1, "imag": .1}]} for f in frequencies],
        "probes": [{"id": "left", "fractional_position": 0.}, {"id": "middle", "fractional_position": .37},
                   {"id": "right", "fractional_position": 1.}]}


if __name__ == "__main__":
    print(json.dumps(run_rlgc_coupled_pair(request()), allow_nan=False))
