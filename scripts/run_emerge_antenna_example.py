# SPDX-License-Identifier: Apache-2.0
"""Run the checked-in KiCad antenna through SPIKE's EMerge extension.

The output is evidence of execution, not an antenna performance qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.extension_analysis_results import design_binding  # noqa: E402
from python.spike_core.extensions import ExtensionRegistry  # noqa: E402
from python.spike_core.kicad_importer import import_kicad_design  # noqa: E402


def run(config_path: Path, python_executable: Path | None = None,
        *, output_dir: Path | None = None, output_prefix: str = "antenna") -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    parameters = dict(config["parameters"])
    if python_executable is not None:
        parameters["python_executable"] = str(python_executable.resolve())
    board_path = (ROOT / config["board"]).resolve()
    if not board_path.is_file() or board_path.suffix.lower() != ".kicad_pcb":
        raise ValueError("Example must reference an existing KiCad board.")
    # The desktop bridge transmits JSON arrays; the Python importer uses a few
    # tuples for coordinates, so mirror that exact transport normalization.
    design = json.loads(json.dumps(import_kicad_design(str(board_path)).to_dict(),
                                   allow_nan=False))
    binding = design_binding(design)
    registry = ExtensionRegistry()
    diagnostics = registry.discover([ROOT / "extensions"], trusted_roots=[ROOT / "extensions"])
    if not any(row["id"] == "spike.emerge-suite" and row["status"] == "loaded"
               for row in diagnostics):
        raise RuntimeError("The bundled EMerge extension was not admitted by SPIKE.")
    envelope = registry.invoke("spike.emerge-suite", "emerge-radiation",
                               {"design": design, "parameters": parameters})
    result = envelope["data"]["analysis_result"]
    network = result["networks"]["s_parameters"]
    radiation = result["fields"]["radiation"]
    frequencies = network["frequencies_hz"]
    s11 = [20 * math.log10(max(math.hypot(*matrix[0][0]), 1e-30))
           for matrix in network["values"]]
    pattern = radiation["patterns_3d"][0]
    peak = max(range(len(pattern["relative_amplitude_db"])),
               key=lambda index: pattern["relative_amplitude_db"][index])
    phi_count = len(pattern["phi_deg"])
    theta_index, phi_index = divmod(peak, phi_count)
    probe = {
        "frequency_hz": pattern["frequency_hz"],
        "theta_deg": pattern["theta_deg"][theta_index],
        "phi_deg": pattern["phi_deg"][phi_index],
        "relative_amplitude_db": pattern["relative_amplitude_db"][peak],
        "e_theta_v_m": pattern["e_theta_v_m"][peak],
        "e_phi_v_m": pattern["e_phi_v_m"][peak],
        "sample_kind": "solver_angular_grid_point",
    }
    evidence = {
        "board": config["board"],
        "board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
        "design_id": design["design_id"],
        "design_digest_sha256": binding["digest_sha256"],
        "parameters": config["parameters"],
        "runtime_executable": parameters.get("python_executable", "auto"),
        "solver": result["provenance"]["solver"],
        "status": result["status"],
        "model_status": result["model_status"],
        "frequencies_hz": frequencies,
        "s11_db": s11,
        "ports": network["ports"],
        "radiation_peak_sample": probe,
        "radiation_cut_peak_angles_deg": [cut["peak_angle_deg"] for cut in radiation["cuts"]],
        "issue_codes": [issue["code"] for issue in result["issues"]],
        "qualification": "execution evidence only; no mesh or measurement correlation",
    }
    if not output_prefix.isidentifier():
        raise ValueError("Output prefix must be a simple identifier.")
    output = output_dir or ROOT / "examples" / "emerge"
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{output_prefix}_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output / f"{output_prefix}_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    try:
        import matplotlib
    except ModuleNotFoundError:
        # The solver result and hash-bound evidence have already been written.
        # Plotting is optional in the minimal worker environment; a missing
        # visualization package must not turn a completed solve into a failure.
        evidence["plot_status"] = "not_generated_matplotlib_unavailable"
        (output / f"{output_prefix}_evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
        return evidence
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(10, 3.6), constrained_layout=True)
    axes[0].plot([frequency / 1e9 for frequency in frequencies], s11, marker="o")
    axes[0].set(xlabel="Frequency (GHz)", ylabel="S11 (dB)", title="Port reflection, 50 Ω")
    axes[0].grid(True)
    cut = radiation["cuts"][0]
    axes[1].plot(cut["angles_deg"], cut["relative_amplitude_db"])
    axes[1].set(xlabel="Theta (degrees), phi = 0", ylabel="Relative amplitude (dB)",
                title=f"Far-field cut, {cut['frequency_hz'] / 1e9:g} GHz")
    axes[1].grid(True)
    figure.savefig(output / f"{output_prefix}_plots.png", dpi=160)
    plt.close(figure)

    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=ROOT / "examples" / "emerge" / "antenna_run.json")
    parser.add_argument("--python-executable", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output-prefix", default="antenna")
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.python_executable,
                         output_dir=args.output_dir, output_prefix=args.output_prefix), indent=2))
