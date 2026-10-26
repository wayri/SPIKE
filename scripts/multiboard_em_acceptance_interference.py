# SPDX-License-Identifier: Apache-2.0
"""Load actual four-excitation field evidence and calculate terminated coupling.

Refuses failed or changed field outputs. Numerical screening remains separate
from the ability to calculate frequency-domain loaded response. No DC spectrum
or complete imported PCB geometry is invented.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.solvers.signal_integrity.receivers.si_crosstalk import analyze_crosstalk
from python.spike_core.solvers.signal_integrity.networks.sparameters import NetworkData, touchstone_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    args = parser.parse_args()
    case = args.case.resolve(strict=True)
    execution = json.loads((case / "execution.json").read_text(encoding="utf-8"))
    field_path = case / "field-result.json"
    sha = hashlib.sha256(field_path.read_bytes()).hexdigest()
    if execution["status"] != "executed" or execution["artifact_sha256"]["field-result.json"] != sha:
        raise ValueError("Unsuccessful or changed field execution cannot produce loaded evidence")
    field = json.loads(field_path.read_text(encoding="utf-8"))
    matrix = np.asarray(field["s_real"]) + 1j * np.asarray(field["s_imag"])
    network = NetworkData(np.asarray(field["frequency_hz"]), matrix, np.full(4, 50.), source="actual-two-substrate-FDTD")
    loaded = analyze_crosstalk(network, port_map={"aggressor_near": 0, "aggressor_far": 1, "victim_near": 2, "victim_far": 3},
                              termination_ohm=[50.] * 4)
    loaded["source_field_sha256"] = sha
    loaded["source_scope"] = "Actual two-substrate box FDTD; not complete imported boards. Ports preserve +z polarity."
    (case / "loaded-field-crosstalk.json").write_text(json.dumps(loaded, indent=2, allow_nan=False), encoding="utf-8")
    (case / "field-network.s4p").write_text(touchstone_text(network.frequencies_hz, matrix, 50.), encoding="ascii")
    print(json.dumps({"status": loaded["status"], "peak_transfer_v_per_v": {
        name: max(row["magnitude"] for row in response["trace"]) for name, response in loaded["frequency_response"].items()},
        "source_field_sha256": sha, "production_qualified": False}, indent=2))


if __name__ == "__main__":
    main()
