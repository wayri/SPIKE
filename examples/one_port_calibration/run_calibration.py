# SPDX-License-Identifier: Apache-2.0
"""Run an explicitly synthetic known-standard one-port calibration example."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.solvers.signal_integrity.networks.one_port_calibration import calibrate_one_port, input_basis


def demonstration():
    frequencies = [1e8, 1e9]
    standard_values = [[], [], []]
    dut = [.2+.3j, -.4+.1j]
    measured = [[], [], []]
    d, t, s = .02+.01j, .85-.12j, .08+.03j

    def pair(z):
        return {"real": float(z.real), "imag": float(z.imag)}

    def instrument(g):
        return d+t*g/(1-s*g)

    for frequency in frequencies:
        w = 2*np.pi*frequency
        # Independently specified lumped standards at the same 50-ohm plane.
        impedances = [1/(1j*w*35e-15), 1j*w*25e-12, 50.3]
        for j, z in enumerate(impedances):
            g = (z-50)/(z+50)
            standard_values[j].append(pair(g))
            measured[j].append(pair(instrument(g)))
    factor = np.diag([5e-5 if i % 14 < 6 else 1e-5 for i in range(28)])
    common = np.linspace(-1e-5, 1e-5, 28)
    covariance = factor@factor.T + np.outer(common, common)
    return {"contract": "spike/one-port-calibration-request/v1", "id": "synthetic-sol-study-v1",
            "port_name": "reviewed-one-port-plane", "reference_impedance_ohm": 50.,
            "frequencies_hz": frequencies,
            "standards": [{"id": label, "provenance": "SPIKE synthetic lumped standard v1; not a calibration certificate",
                           "reflection": standard_values[i], "measured": measured[i]}
                          for i, label in enumerate(("open-35fF", "short-25pH", "load-50p3ohm"))],
            "dut": {"id": "synthetic-independent-dut", "provenance": "SPIKE explicitly synthetic reflection pair v1",
                    "measured": [pair(instrument(g)) for g in dut]},
            "covariance": {"basis": input_basis(2), "matrix": covariance.tolist(),
                           "provenance": "SPIKE synthetic joint covariance v1: diagonal noise plus shared frequency-correlated mode"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, help="Explicit known-standard request; default is synthetic example")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8")) if args.request else demonstration()
    capture = {"source": request, "result": calibrate_one_port(request)}
    # Exclusive creation preserves existing captures. No instrument/board data
    # are modified; source is retained alongside its separate derived network.
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(capture, allow_nan=False, indent=2)+"\n")
    print("Experimental one-port capture retained; physical/linearization qualification remains open.")


if __name__ == "__main__":
    main()
