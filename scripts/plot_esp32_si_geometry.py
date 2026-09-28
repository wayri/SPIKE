#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Plot saved ESP32 SI channel samples without performing or altering a solve."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


EVIDENCE = Path(__file__).resolve().parents[1] / "examples/esp32/evidence"
result = json.loads((EVIDENCE / "si_geometry_result.json").read_text(encoding="utf-8"))
if result.get("status") != "completed" or result.get("model_status") != "experimental":
    raise ValueError("A completed experimental SI result is required.")
network = result["network"]
eye = result["eye"]
if network.get("status") != "completed" or eye.get("status") != "completed":
    raise ValueError("The saved network and eye traces must both be completed.")

figure, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
for name, color in (("S11", "#bd4d36"), ("S21", "#1268a0")):
    trace = network["traces"][name]
    axes[0].plot([point["frequency_hz"] / 1e9 for point in trace],
                 [point["magnitude_db"] for point in trace], label=name, color=color)
axes[0].set(xlabel="Frequency (GHz)", ylabel="Magnitude (dB)",
            title="Board-derived ERXD0 channel · 50 Ω ports")
axes[0].grid(True, alpha=0.35)
axes[0].legend()

traces = eye["traces"]
samples_per_ui = float(eye["actual_samples_per_ui"])
for trace in traces:
    values = np.asarray(trace["values"], dtype=float)
    axes[1].plot(np.arange(len(values)) / samples_per_ui, values,
                 color="#26648a", linewidth=0.55, alpha=0.23)
axes[1].set(xlabel="Time (UI)", ylabel="Normalized amplitude",
            title=f"Ideal NRZ eye · {eye['bit_rate_hz']/1e6:.0f} Mb/s")
axes[1].grid(True, alpha=0.35)
figure.suptitle("ESP32 SI geometry slice · experimental, unvalidated", fontsize=11)
figure.savefig(EVIDENCE / "si_geometry_plots.png", dpi=170)
plt.close(figure)
print("Rendered saved S11/S21 and normalized eye samples")
