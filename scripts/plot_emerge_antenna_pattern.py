# SPDX-License-Identifier: Apache-2.0
"""Render the saved EMerge antenna angular samples without rerunning the solver."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1] / "examples" / "emerge"
result = json.loads((ROOT / "antenna_result.json").read_text(encoding="utf-8"))
pattern = result["fields"]["radiation"]["patterns_3d"][0]
theta = pattern["theta_deg"]
phi = pattern["phi_deg"]
points = []
for row, theta_deg in enumerate(theta):
    for column, phi_deg in enumerate(phi):
        db = pattern["relative_amplitude_db"][row * len(phi) + column]
        radius = 10 ** (max(db, -60.0) / 20)
        t, p = math.radians(theta_deg), math.radians(phi_deg)
        points.append((radius * math.sin(t) * math.cos(p),
                       radius * math.sin(t) * math.sin(p),
                       radius * math.cos(t), db))

figure = plt.figure(figsize=(6, 5))
axis = figure.add_subplot(111, projection="3d")
scatter = axis.scatter([point[0] for point in points],
                       [point[1] for point in points],
                       [point[2] for point in points],
                       c=[point[3] for point in points], cmap="viridis",
                       vmin=-40, vmax=0, s=10)
axis.set(xlabel="X", ylabel="Y", zlabel="Z",
         title=f"Solved angular samples · {pattern['frequency_hz'] / 1e9:g} GHz")
axis.set_box_aspect((1, 1, 1))
figure.colorbar(scatter, ax=axis, shrink=0.7, label="Relative amplitude (dB)")
figure.tight_layout()
figure.savefig(ROOT / "antenna_pattern_3d.png", dpi=160)
plt.close(figure)
