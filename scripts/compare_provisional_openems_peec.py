# SPDX-License-Identifier: Apache-2.0
"""Cross-check unlike provisional port models without fitting PEEC coefficients."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    validation = ROOT / "build/validation"
    fdtd = json.loads((validation / "openems-internal-comparison-20260928/two-port-summary.json").read_text())[
        "HForsten RF_IN (SI)"
    ]
    peec_record = json.loads((validation / "internal-comparison/hforsten-volume-peec.json").read_text())
    peec_result = peec_record["result"]
    if peec_result["status"] != "completed" or peec_result["model_status"] != "approximate":
        raise RuntimeError("Volume PEEC result is not completed/approximate")
    frequency = np.asarray(fdtd["frequency_hz"], dtype=float)
    s = np.empty((len(frequency), 2, 2), dtype=complex)
    for i in range(2):
        for j in range(2):
            value = fdtd["s_parameters"][f"s{i+1}{j+1}"]
            s[:, i, j] = np.asarray(value["real"]) + 1j * np.asarray(value["imag"])
    cond = np.asarray([np.linalg.cond(np.eye(2) - value) for value in s])
    if np.max(cond) > 1e6:
        raise RuntimeError("S-to-Z conversion is ill-conditioned")
    z = np.asarray([50.0 * (np.eye(2) + value) @ np.linalg.inv(np.eye(2) - value) for value in s])
    fdtd_diff = z[:, 0, 0] + z[:, 1, 1] - z[:, 0, 1] - z[:, 1, 0]
    rows = peec_result["networks"]["parasitics"][0]["impedance"]
    peec_f = np.asarray([row["frequency_hz"] for row in rows])
    peec_z = np.asarray([complex(row["resistance_ohm"], row["reactance_ohm"]) for row in rows])
    peec_on_fdtd = np.interp(frequency, peec_f, peec_z.real) + 1j * np.interp(frequency, peec_f, peec_z.imag)
    output = validation / "openems-internal-comparison-20260928"
    summary = {
        "status": "exploratory_crosscheck_not_calibration",
        "reason": "openEMS differential two-port terminal current and SPIKE single signal-path PEEC current/return approximation are not physically matched; geometry, materials, and ports are provisional",
        "openems_quantity": "Z11+Z22-Z12-Z21 from a 50-ohm two-port S matrix",
        "internal_quantity": "one signal-net source-to-load PEEC driving-point Z",
        "frequency_hz": frequency.tolist(),
        "openems_differential_z_ohm": [{"real": float(v.real), "imag": float(v.imag)} for v in fdtd_diff],
        "peec_interpolated_z_ohm": [{"real": float(v.real), "imag": float(v.imag)} for v in peec_on_fdtd],
        "max_s_to_z_condition_number": float(np.max(cond)),
        "native_module_sha256": peec_record["native_module_sha256"],
    }
    (output / "hforsten-crosscheck.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    x = frequency / 1e9
    for ax, part, label in ((axes[0], "real", "Re(Z) (Ω)"), (axes[1], "imag", "Im(Z) (Ω)")):
        component = (lambda value: value.real) if part == "real" else (lambda value: value.imag)
        ax.plot(x, [component(value) for value in fdtd_diff], label="openEMS two-port differential")
        ax.plot(x, [component(value) for value in peec_on_fdtd], "--", label="SPIKE signal-path PEEC")
        ax.set(xlabel="Frequency (GHz)", ylabel=label)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("HForsten provisional cross-check · different terminal/current models · no calibration", fontsize=11)
    fig.savefig(output / "hforsten-openems-peec-crosscheck.png", dpi=170)
    plt.close(fig)
    print(json.dumps({"output": str(output / "hforsten-crosscheck.json"),
                      "imag_1ghz": [float(fdtd_diff[0].imag), float(peec_on_fdtd[0].imag)],
                      "imag_3ghz": [float(fdtd_diff[-1].imag), float(peec_on_fdtd[-1].imag)]}))


if __name__ == "__main__":
    main()
