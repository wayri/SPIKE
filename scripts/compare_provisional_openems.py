# SPDX-License-Identifier: Apache-2.0
"""Summarize two-excitation provisional openEMS slices without implying board validation.

The two source-backed cases are intentionally local slices.  Each excitation is
run separately because the openEMS adapter excites one lumped port per job.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _read_two_port(root: Path, stem: str) -> dict:
    one = json.loads((root / f"{stem}-p1-20260928" / "engine-output" / "normalized-result.json").read_text())
    two = json.loads((root / f"{stem}-p2-20260928" / "engine-output" / "normalized-result.json").read_text())
    freq = np.asarray(one["frequency_hz"], dtype=float)
    if not np.array_equal(freq, np.asarray(two["frequency_hz"], dtype=float)):
        raise ValueError(f"{stem}: excitation frequency grids differ")
    if one["status"] != "completed" or two["status"] != "completed":
        raise ValueError(f"{stem}: both excitations must complete")
    if one["model_status"] != "approximate" or two["model_status"] != "approximate":
        raise ValueError(f"{stem}: expected provisional model status")
    s = np.empty((len(freq), 2, 2), dtype=complex)
    for key, result in (("s11", one), ("s21", one), ("s12", two), ("s22", two)):
        value = result["s_parameters"][key]
        i, j = int(key[1]) - 1, int(key[2]) - 1
        s[:, i, j] = np.asarray(value["real"]) + 1j * np.asarray(value["imag"])
    singular = np.linalg.svd(s, compute_uv=False)
    reciprocal_error = np.abs(s[:, 1, 0] - s[:, 0, 1])
    return {
        "frequency_hz": freq,
        "s": s,
        "max_singular_value": singular[:, 0],
        "reciprocity_abs_error": reciprocal_error,
        "runs": [one["run_binding"], two["run_binding"]],
        "mesh": [one["mesh"], two["mesh"]],
    }


def _serializable(case: dict) -> dict:
    s = case["s"]
    return {
        "frequency_hz": case["frequency_hz"].tolist(),
        "s_parameters": {
            f"s{i + 1}{j + 1}": {
                "real": s[:, i, j].real.tolist(),
                "imag": s[:, i, j].imag.tolist(),
                "magnitude": np.abs(s[:, i, j]).tolist(),
            }
            for i in range(2)
            for j in range(2)
        },
        "max_singular_value": case["max_singular_value"].tolist(),
        "reciprocity_abs_error": case["reciprocity_abs_error"].tolist(),
        "peak_reciprocity_abs_error": float(np.max(case["reciprocity_abs_error"])),
        "peak_singular_value": float(np.max(case["max_singular_value"])),
        "runs": case["runs"],
        "mesh": case["mesh"],
        "status": "exploratory_provisional_not_accuracy_validation",
    }


def _plot(cases: dict[str, dict], output: Path) -> None:
    if len(cases) != 1:
        raise ValueError("A separate four-panel figure is needed per source-backed slice")
    label, case = next(iter(cases.items()))
    x = case["frequency_hz"] / 1e9
    s = case["s"]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    ax = axes[0, 0]
    ax.plot(x, np.abs(s[:, 1, 0]), label="|S21|")
    ax.plot(x, np.abs(s[:, 0, 1]), "--", label="|S12|")
    ax.set(title="Transmission", ylabel="S magnitude")
    ax.legend()
    ax = axes[0, 1]
    ax.plot(x, np.abs(s[:, 0, 0]), label="|S11|")
    ax.plot(x, np.abs(s[:, 1, 1]), "--", label="|S22|")
    ax.set(title="Port reflections", ylabel="S magnitude")
    ax.legend()
    ax = axes[1, 0]
    ax.plot(x, case["max_singular_value"], color="tab:purple")
    ax.axhline(1.0, color="black", linewidth=0.8, linestyle=":")
    ax.set(title="Passivity diagnostic", ylabel="Largest singular value", xlabel="Frequency (GHz)")
    ax = axes[1, 1]
    ax.plot(x, case["reciprocity_abs_error"], color="tab:brown")
    ax.set(title="Reciprocity diagnostic", ylabel="|S21 − S12|", xlabel="Frequency (GHz)")
    for ax in axes.flat:
        ax.grid(alpha=0.25)
    fig.suptitle(f"{label}: provisional local openEMS two-port · assumed return, stackup and ports", fontsize=11)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _plot_internal(root: Path, output: Path) -> dict:
    specs = (("HForsten RF_IN", "hforsten-internal.json", "source_to_load_copper_drop_v_at_1a"),
             ("Marble +1V0/GND", "marble-internal.json", "loop_drop_v_at_1a"))
    fig, ax = plt.subplots(figsize=(7.5, 4.5), constrained_layout=True)
    summary = {}
    for name, filename, field in specs:
        record = json.loads((root / filename).read_text())
        rows = sorted(record["dc"], key=lambda row: row["mesh_mm"])
        if any(row["status"] != "completed" or row["model_status"] != "approximate" for row in rows):
            raise ValueError(f"{name}: incomplete native DC sweep")
        mesh = [row["mesh_mm"] for row in rows]
        milliohm = [row[field] * 1000.0 for row in rows]  # V at 1 A -> mΩ
        ax.plot(mesh, milliohm, marker="o", label=name)
        summary[name] = {"mesh_mm": mesh, "effective_dc_milliohm": milliohm,
                         "last_refinement_relative_change": abs(milliohm[1] - milliohm[0]) / abs(milliohm[0]),
                         "quantity": field, "source_sha256": record["source_sha256"]}
    ax.set(xlabel="Mesh spacing (mm)", ylabel="Terminal drop at 1 A (mV = mΩ)",
           title="SPIKE native DC local slices (provisional; mesh sweeps nonmonotonic)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-root", type=Path, default=Path("build/validation"))
    parser.add_argument("--output-dir", type=Path, default=Path("build/validation/openems-internal-comparison-20260928"))
    args = parser.parse_args()
    cases = {"HForsten RF_IN (SI)": _read_two_port(args.validation_root, "hforsten-rf-in-2port")}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "two-port-summary.json").write_text(
        json.dumps({name: _serializable(case) for name, case in cases.items()}, indent=2) + "\n"
    )
    _plot(cases, args.output_dir / "openems-two-port.png")
    internal = _plot_internal(args.validation_root / "internal-comparison", args.output_dir / "internal-dc-mesh.png")
    (args.output_dir / "internal-dc-summary.json").write_text(json.dumps(internal, indent=2) + "\n")
    for name, case in cases.items():
        print(name, "peak singular", float(np.max(case["max_singular_value"])),
              "peak reciprocity error", float(np.max(case["reciprocity_abs_error"])))


if __name__ == "__main__":
    main()
