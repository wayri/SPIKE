#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render admitted ESP32 EMerge samples; never fabricate a field or solve."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1] / "examples/esp32/evidence"
result = json.loads((ROOT / "rf_surrogate_result.json").read_text(encoding="utf-8"))
if result.get("status") != "completed" or result.get("model_status") != "unvalidated":
    raise ValueError("A completed, explicitly unvalidated SPIKE result is required.")
network = result["networks"]["s_parameters"]
radiation = result["fields"]["radiation"]
frequencies = network["frequencies_hz"]
s11 = [20 * math.log10(max(math.hypot(*matrix[0][0]), 1e-30)) for matrix in network["values"]]
selected = min(range(len(frequencies)), key=lambda index: abs(frequencies[index] - 2.45e9))
cut = radiation["cuts"][selected]
pattern = radiation["patterns_3d"][selected]

figure, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
axes[0].plot(np.asarray(frequencies) / 1e9, s11, "o-", color="#1268a0")
axes[0].set(xlabel="Frequency (GHz)", ylabel="S11 (dB)", title="One-port reflection, 50 Ω")
axes[0].grid(True, alpha=0.35)
axes[1].plot(cut["angles_deg"], cut["relative_amplitude_db"], "o-", markersize=2, color="#a34c21")
axes[1].set(xlabel="Theta (degrees), phi = 0°", ylabel="Relative field (dB)",
            title=f"Far-field cut, {cut['frequency_hz']/1e9:.2f} GHz")
axes[1].grid(True, alpha=0.35)
figure.suptitle("ESP32 two-conductor surrogate · EMerge · unvalidated", fontsize=11)
figure.savefig(ROOT / "rf_surrogate_2d_plots.png", dpi=170)
plt.close(figure)

theta = np.radians(np.asarray(pattern["theta_deg"], dtype=float))
phi = np.radians(np.asarray(pattern["phi_deg"], dtype=float))
db = np.asarray(pattern["relative_amplitude_db"], dtype=float).reshape(len(theta), len(phi))
radius = 10 ** (np.maximum(db, -40) / 20)
th, ph = np.meshgrid(theta, phi, indexing="ij")
x = radius * np.sin(th) * np.cos(ph)
y = radius * np.sin(th) * np.sin(ph)
z = radius * np.cos(th)
figure = plt.figure(figsize=(7, 6))
axis = figure.add_subplot(111, projection="3d")
colors = plt.get_cmap("viridis")((np.clip(db, -40, 0) + 40) / 40)
axis.plot_surface(x, y, z, facecolors=colors, rstride=1, cstride=1,
                  linewidth=0.25, edgecolor="#324251", shade=False, antialiased=True)
axis.set(xlabel="X", ylabel="Y", zlabel="Z", title=f"ESP32 relative field · {pattern['frequency_hz']/1e9:.2f} GHz")
axis.set_box_aspect((1, 1, 1))
scale = plt.cm.ScalarMappable(norm=plt.Normalize(-40, 0), cmap="viridis")
figure.colorbar(scale, ax=axis, shrink=0.65, label="Relative field (dB)")
figure.text(0.5, 0.04, "Solver angular samples joined for display · two-conductor surrogate · unvalidated",
            ha="center", fontsize=9)
figure.savefig(ROOT / "rf_surrogate_pattern_3d.png", dpi=170)
plt.close(figure)
print("Rendered admitted S11, theta cut and 3D angular samples")
