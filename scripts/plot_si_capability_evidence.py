# SPDX-License-Identifier: Apache-2.0
"""Save exploratory SI reference-workflow and native PEEC plots."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.si_workflow import REQUEST, run_si_workflow


def plot_reference(output: Path) -> dict:
    result = run_si_workflow({"contract": REQUEST})
    if result["status"] != "completed" or result["time_domain"]["status"] != "completed":
        raise RuntimeError("Reference coupled-line time-domain workflow did not complete")
    network = result["network"]
    if network["port_count"] != 4 or len(network["reflection_vswr"]["ports"]) != 4:
        raise RuntimeError("Reference coupled-line port mapping changed")
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    ax = axes[0, 0]
    for key, label in (("S31", "through"), ("S21", "NEXT"), ("S41", "FEXT")):
        rows = network["traces"][key]
        ax.plot([row["frequency_hz"] / 1e9 for row in rows],
                [max(row["magnitude_db"], -120.0) for row in rows], label=f"{label} ({key})")
    ax.set(title="Matched four-port channel", xlabel="Frequency (GHz)", ylabel="Magnitude (dB)", ylim=(-120, 5))
    ax.legend()
    ax = axes[0, 1]
    rows = network["reflection_vswr"]["ports"][0]["trace"]
    ax.plot([row["frequency_hz"] / 1e9 for row in rows],
            [row["vswr"] if row["vswr_status"] == "finite" else np.nan for row in rows])
    ax.set(title="Port 1 matched-reference VSWR", xlabel="Frequency (GHz)", ylabel="VSWR")
    ax = axes[1, 0]
    receiver = result["time_domain"]["receivers"][0]
    for trace in receiver["traces"]:
        ax.plot(trace["phase_ui"], trace["voltage_v"], color="tab:blue", alpha=0.08, linewidth=0.7)
    ax.set(title=f"Reference receiver eye · height {receiver['eye_height_v']:.3f} V",
           xlabel="Phase (UI)", ylabel="Voltage (V)")
    ax = axes[1, 1]
    tdr = result["tdr"]["tdr"]
    ax.plot([row["time_s"] * 1e9 for row in tdr], [row["impedance_ohm"] for row in tdr])
    ax.set(title="Returned TDR impedance", xlabel="Time (ns)", ylabel="Ω", xlim=(0, 8))
    for ax in axes.flat:
        ax.grid(alpha=0.25)
    fig.suptitle("SPIKE analytical coupled-RLGC reference workflow · experimental, not a PCB extraction", fontsize=11)
    fig.savefig(output, dpi=170)
    plt.close(fig)
    return {"contract": result["contract"], "status": result["status"],
            "model_status": result["model_status"], "port_count": network["port_count"],
            "time_domain_status": result["time_domain"]["status"],
            "tdr_status": result["tdr"]["status"],
            "eye_height_v": receiver["eye_height_v"],
            "field_maps_status": result["field_maps"]["status"],
            "production_qualified": result["production_qualified"]}


def plot_peec(output: Path) -> dict:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    summary = {}
    for ax, board in zip(axes, ("hforsten", "marble")):
        path = ROOT / "build/validation/internal-comparison" / f"{board}-volume-peec.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        result = record["result"]
        if result["status"] != "completed" or result["model_status"] != "approximate":
            raise RuntimeError(f"{board} volume PEEC not completed/approximate")
        network = result["networks"]["parasitics"][0]
        rows = network["impedance"]
        x = [row["frequency_hz"] / 1e9 for row in rows]
        ax.plot(x, [row["reactance_ohm"] for row in rows], color="tab:orange", label="Im(Z)")
        right = ax.twinx()
        right.plot(x, [row["resistance_ohm"] for row in rows], color="tab:blue", linestyle="--", label="Re(Z)")
        ax.set(title=f"{board.title()} signal path · approximate PEEC", xlabel="Frequency (GHz)", ylabel="Im(Z) (Ω)")
        right.set_ylabel("Re(Z) (Ω)")
        ax.grid(alpha=0.25)
        lines = ax.lines + right.lines
        ax.legend(lines, [line.get_label() for line in lines], loc="upper left")
        summary[board] = {"status": result["status"], "model_status": result["model_status"],
                          "source_sha256": record["source_sha256"],
                          "native_module_sha256": record["native_module_sha256"],
                          "frequency_hz": [row["frequency_hz"] for row in rows],
                          "resistance_ohm": [row["resistance_ohm"] for row in rows],
                          "reactance_ohm": [row["reactance_ohm"] for row in rows],
                          "inductance_negative_modes": network["quality"]["inductance_passivity"]["negative_eigenmode_count"],
                          "blocked_uses": network["blocked_uses"]}
    fig.suptitle("Native finite-volume PEEC driving-point results · provisional local slices · no S-parameter calibration", fontsize=11)
    fig.savefig(output, dpi=170)
    plt.close(fig)
    return summary


def main() -> None:
    output = ROOT / "build/validation/si-capability-evidence-20260928"
    output.mkdir(parents=True, exist_ok=True)
    reference = plot_reference(output / "analytical-si-workflow.png")
    peec = plot_peec(output / "native-volume-peec-impedance.png")
    (output / "summary.json").write_text(json.dumps({"analytical_reference": reference,
                                                       "provisional_volume_peec": peec}, indent=2,
                                                      allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "reference": reference,
                      "volume_peec_status": {name: item["status"] for name, item in peec.items()}}))


if __name__ == "__main__":
    main()
