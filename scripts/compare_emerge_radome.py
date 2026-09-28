# SPDX-License-Identifier: Apache-2.0
"""Compare paired EMerge antenna runs; figures are unvalidated display evidence."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1] / "examples" / "emerge" / "radome"


def load_case(name: str) -> tuple[dict, dict]:
    return (json.loads((ROOT / f"{name}_result.json").read_text(encoding="utf-8")),
            json.loads((ROOT / f"{name}_evidence.json").read_text(encoding="utf-8")))


def main() -> None:
    bare, bare_evidence = load_case("bare")
    covered, covered_evidence = load_case("covered")
    for key in ("board_sha256", "design_digest_sha256", "frequencies_hz", "ports"):
        if bare_evidence[key] != covered_evidence[key]:
            raise ValueError(f"Paired runs differ in {key}.")
    for key in ("signal_net", "return_net", "signal_pad_id", "return_pad_id",
                "frequency_start_hz", "frequency_stop_hz", "frequency_points", "mesh_resolution_mm"):
        if bare_evidence["parameters"][key] != covered_evidence["parameters"][key]:
            raise ValueError(f"Paired runs differ in {key}.")
    bpattern = bare["fields"]["radiation"]["patterns_3d"][0]
    cpattern = covered["fields"]["radiation"]["patterns_3d"][0]
    if bpattern["theta_deg"] != cpattern["theta_deg"] or bpattern["phi_deg"] != cpattern["phi_deg"]:
        raise ValueError("Pattern angular grids differ.")
    theta = np.asarray(cpattern["theta_deg"], dtype=float)
    phi = np.asarray(cpattern["phi_deg"], dtype=float)
    bare_db = np.asarray(bpattern["relative_amplitude_db"], dtype=float).reshape(len(theta), len(phi))
    cover_db = np.asarray(cpattern["relative_amplitude_db"], dtype=float).reshape(len(theta), len(phi))
    direct_index = (int(np.argmin(abs(theta - 90))), int(np.argmin(abs(phi))))
    back_index = (int(np.argmin(abs(theta - 180))), int(np.argmin(abs(phi))))
    direct_delta = float(cover_db[direct_index] - bare_db[direct_index])
    evidence = {
        "board_sha256": bare_evidence["board_sha256"], "solver": covered_evidence["solver"],
        "frequencies_hz": bare_evidence["frequencies_hz"],
        "s11_db_bare": bare_evidence["s11_db"], "s11_db_covered": covered_evidence["s11_db"],
        "first_frequency_hz": float(cpattern["frequency_hz"]),
        "theta_90_phi_0_relative_db_bare": float(bare_db[direct_index]),
        "theta_90_phi_0_relative_db_covered": float(cover_db[direct_index]),
        "theta_90_phi_0_normalized_shape_delta_db": direct_delta,
        "theta_180_phi_0_relative_db_bare": float(bare_db[back_index]),
        "theta_180_phi_0_relative_db_covered": float(cover_db[back_index]),
        "theta_180_phi_0_normalized_shape_delta_db": float(cover_db[back_index] - bare_db[back_index]),
        "radome": covered_evidence["parameters"]["surrounding_geometry"],
        "interpretation": "Pattern difference compares independently peak-normalized display fields; it is not insertion loss, gain, or compliance margin.",
        "qualification": "Unvalidated coarse mesh; no convergence, measured reference, or numerical human review.",
    }
    (ROOT / "comparison_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    figure, axes = plt.subplots(1, 2, figsize=(10, 3.6), constrained_layout=True)
    frequency = np.asarray(evidence["frequencies_hz"]) / 1e9
    axes[0].plot(frequency, evidence["s11_db_bare"], "o-", label="Bare")
    axes[0].plot(frequency, evidence["s11_db_covered"], "s-", label="With dielectric cover")
    axes[0].set(xlabel="Frequency (GHz)", ylabel="S11 (dB)", title="Same board and port")
    axes[0].grid(True); axes[0].legend()
    axes[1].plot(theta, bare_db[:, 0], "o-", label="Bare")
    axes[1].plot(theta, cover_db[:, 0], "s-", label="With dielectric cover")
    axes[1].set(xlabel="Theta (degrees), phi = 0°", ylabel="Relative amplitude (dB)",
                title=f"Normalized cut · {frequency[0]:g} GHz", ylim=(-40, 1))
    axes[1].grid(True); axes[1].legend()
    figure.savefig(ROOT / "radome_comparison.png", dpi=160)
    plt.close(figure)

    # Bilinear interpolation is performed in linear relative amplitude; it is
    # a display surface and does not create additional solved angular samples.
    dense_theta = np.arange(0, 181, 5, dtype=float)
    dense_phi = np.arange(0, 361, 5, dtype=float)
    dense = np.empty((len(dense_theta), len(dense_phi)))
    solved_amplitude = 10 ** (cover_db / 20)
    for row, t in enumerate(dense_theta):
        along_phi = np.asarray([np.interp(t, theta, solved_amplitude[:, col]) for col in range(len(phi))])
        dense[row] = np.interp(dense_phi, phi, along_phi)
    tt, pp = np.meshgrid(np.deg2rad(dense_theta), np.deg2rad(dense_phi), indexing="ij")
    radius = dense
    xx, yy, zz = radius * np.sin(tt) * np.cos(pp), radius * np.sin(tt) * np.sin(pp), radius * np.cos(tt)
    color_db = 20 * np.log10(np.maximum(dense, 1e-15))
    colors = plt.cm.viridis(np.clip((color_db + 40) / 40, 0, 1))
    figure = plt.figure(figsize=(8, 7))
    axis = figure.add_subplot(111, projection="3d")
    axis.plot_surface(xx, yy, zz, facecolors=colors, linewidth=0, antialiased=True,
                      rstride=1, cstride=1, shade=False)
    axis.set(xlabel="X", ylabel="Y", zlabel="Z", title="Dielectric cover · interpolated 5° display · 3 GHz")
    axis.set_box_aspect((1, 1, 1))
    figure.colorbar(plt.cm.ScalarMappable(norm=plt.Normalize(-40, 0), cmap="viridis"),
                   ax=axis, shrink=.65, label="Relative amplitude (dB)")
    figure.savefig(ROOT / "covered_pattern_interpolated.png", dpi=150)
    plt.close(figure)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
