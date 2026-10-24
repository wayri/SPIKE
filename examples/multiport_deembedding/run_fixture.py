# SPDX-License-Identifier: Apache-2.0
"""Run an explicit offline fixture-removal request or an original three-port demo."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.sparameter_multiport_deembedding import REQUEST_CONTRACT, deembed_multiport


def pairs(matrix):
    return [[{"real": float(v), "imag": 0.} for v in row] for row in matrix]


def demonstration():
    # Three independent matched attenuator paths, DUT with arbitrary cross-coupling.
    dut = [[.1, .2, -.1], [.05, .15, .3], [.2, -.05, .1]]
    fixture = [[0.] * 6 for _ in range(6)]
    for i in range(3):
        fixture[i][i + 3] = fixture[i + 3][i] = .8
    def source(identity, names, matrix):
        return {"id": identity, "port_names": names, "reference_impedance_ohm": 50.,
                "frequencies_hz": [0., 1e6], "s_parameters": [pairs(matrix), pairs(matrix)]}
    return {"contract": REQUEST_CONTRACT,
            "external_ports": ["E1", "E2", "E3"], "dut_ports": ["D1", "D2", "D3"],
            "fixture": source("supplied-fixture", ["E1", "E2", "E3", "D1", "D2", "D3"], fixture),
            "measured": source("synthetic-measurement", ["E1", "E2", "E3"],
                               [[.64 * v for v in row] for row in dut])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output file; source and previous results are preserved")
    if args.request and args.request.stat().st_size > 8 * 1024 * 1024:
        parser.error("Request exceeds 8 MiB")
    request = json.loads(args.request.read_text(encoding="utf-8")) if args.request else demonstration()
    result = deembed_multiport(request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": "experimental", "ports": result["derived_network"]["port_names"],
                      "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
