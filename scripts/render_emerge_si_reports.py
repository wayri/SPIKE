# SPDX-License-Identifier: Apache-2.0
"""Render admitted board-derived EMerge SI and explicitly DC-assumed eye scenarios."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.extension_analysis_results import admit_analysis_result, design_binding
from python.spike_core.solvers.signal_integrity.receivers.si_workflow import REQUEST, run_si_workflow
from python.spike_core.solvers.signal_integrity.networks.sparameters import touchstone_text

DC_CAVEAT = ("ILLUSTRATIVE DC-ASSUMED, BANDLIMITED EYE: FEM has no DC sample. A separate "
             "derived scenario adds an ideal zero-delay disjoint PEC through matrix at DC "
             "(P1↔P2, P3↔P4; all other entries zero). This is an assumption, not an EMerge "
             "DC solve or measured board qualification. Original FEM samples are untouched.")
PORT_MAP = {"P1": "aggressor near", "P2": "aggressor far", "P3": "victim near", "P4": "victim far"}
PAIR_CAVEAT = ("Selected conductors belong to a differential pair. Single-ended conductor-to-conductor "
               "coupling is a diagnostic, not independent-bus crosstalk. Independent quiet/active PRBS "
               "excitation and matched single-ended eyes do not represent normal differential signaling "
               "or a qualified differential-link eye.")
DIFFERENTIAL_CAVEAT = ("Differential scenario uses orthonormal mixed-mode waves, 100 Ω differential "
                      "source/load and matched 25 Ω common-mode ports, derived from physical 50 Ω ports. "
                      "The extracted differential two-port excludes common-mode reconversion through "
                      "external mismatches. 1 V source, PRBS7, 500 Mb/s and 150 ps edges are test "
                      "assumptions, not actual PHY drive, receiver thresholds or termination evidence.")


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def admit_saved(output: Path, prefix: str) -> tuple[dict, dict]:
    design = json.loads((output / f"{prefix}_design.json").read_text(encoding="utf-8"))
    raw = json.loads((output / f"{prefix}_result.json").read_text(encoding="utf-8"))
    result = admit_analysis_result(raw, design_binding(design), extension_id="spike.emerge-suite")
    digest = hashlib.sha256((output / f"{prefix}_simulation.py").read_bytes()).hexdigest()
    if result["provenance"].get("generated_script_sha256") != digest:
        raise ValueError(f"{prefix}: saved script does not match executed source digest")
    return result, {"admission": "passed", "saved_script_matches_execution": True,
                    "generated_script_sha256": digest, "design_binding": design_binding(design)}


def network_arrays(result: dict):
    network = result["networks"]["s_parameters"]
    f = np.asarray(network["frequencies_hz"], dtype=float)
    pairs = np.asarray(network["values"], dtype=float)
    if pairs.shape != (len(f), 4, 4, 2) or not np.isfinite(pairs).all():
        raise ValueError("SI report requires finite four-port samples")
    return f, pairs[..., 0] + 1j * pairs[..., 1], network["reference_impedance_ohm"]


def dc_scenario(f: np.ndarray, s: np.ndarray):
    expected = np.arange(1, 65, dtype=float) * 1e8
    if f.shape != expected.shape or not np.allclose(f, expected, rtol=1e-10, atol=1e-3):
        raise ValueError("Illustrative eye requires 64 uniform FEM samples at 100 MHz through 6.4 GHz")
    dc = np.zeros((4, 4), dtype=complex)
    dc[0, 1] = dc[1, 0] = dc[2, 3] = dc[3, 2] = 1
    return np.r_[0., f], np.concatenate([dc[None], s], axis=0)


def eye_request(text: str, *, active: bool) -> dict:
    source = {"port": 2, "resistance_ohm": 50., "low_v": 0., "high_v": 1.,
              "rise_time_s": 150e-12, "fall_time_s": 150e-12}
    sources = [source]
    if active:
        sources.append({**source, "port": 0, "pattern_shift_bits": 31})
    return {"contract": REQUEST, "channel": {"kind": "touchstone", "name": "derived_dc_assumption.s4p", "text": text},
            "sources": sources, "receivers": [{"port": 3, "resistance_ohm": 50., "capacitance_f": 0.,
                                                 "vil_v": .175, "vih_v": .325}],
            "bit_rate_hz": 500e6, "bit_count": 256, "run_time_domain": True}


def mixed_mode(s: np.ndarray) -> np.ndarray:
    """Equal-reference normalized waves: Dnear,Dfar,Cnear,Cfar."""
    transform = np.array([[1, 0, -1, 0], [0, 1, 0, -1],
                          [1, 0, 1, 0], [0, 1, 0, 1]], dtype=float) / np.sqrt(2)
    return transform @ s @ transform.T


def differential_eye(f, s) -> dict:
    augmented_f, augmented_s = dc_scenario(f, s)
    differential = mixed_mode(augmented_s)[:, :2, :2]
    text = touchstone_text(augmented_f, differential, 100., comments=[DC_CAVEAT, DIFFERENTIAL_CAVEAT])
    request = {"contract": REQUEST, "channel": {"kind": "touchstone", "name": "dc_assumed_differential.s2p", "text": text},
               "sources": [{"port": 0, "resistance_ohm": 100., "low_v": 0., "high_v": 1.,
                            "rise_time_s": 150e-12, "fall_time_s": 150e-12}],
               "receivers": [{"port": 1, "resistance_ohm": 100., "capacitance_f": 0., "vil_v": .175, "vih_v": .325}],
               "bit_rate_hz": 500e6, "bit_count": 256, "run_time_domain": True}
    result = run_si_workflow(request)
    result["external_scenario_assumptions"] = [DC_CAVEAT, DIFFERENTIAL_CAVEAT]
    result["time_domain"].setdefault("limitations", []).extend([DC_CAVEAT, DIFFERENTIAL_CAVEAT])
    return {"status": result["time_domain"]["status"], "request": request, "result": result, "touchstone_text": text}


def illustrative_eyes(f, s, z0) -> dict:
    maximum_gain = float(np.linalg.svd(s, compute_uv=False)[:, 0].max())
    if maximum_gain > 1.001:
        return {"status": "blocked", "reason": f"Material sampled passivity failure: maximum singular value {maximum_gain:.8g} exceeds 1.001; no repair applied"}
    if not np.allclose(z0, 50.):
        return {"status": "blocked", "reason": "Illustrative matched scenario requires 50 ohm reference impedance"}
    try:
        augmented_f, augmented_s = dc_scenario(f, s)
    except ValueError as exc:
        return {"status": "blocked", "reason": str(exc)}
    text = touchstone_text(augmented_f, augmented_s, z0, comments=[DC_CAVEAT])
    scenarios = {}
    for label, active in (("quiet", False), ("active", True)):
        request = eye_request(text, active=active)
        result = run_si_workflow(request)
        result["external_scenario_assumptions"] = [DC_CAVEAT, PAIR_CAVEAT]
        result["time_domain"].setdefault("limitations", []).append(DC_CAVEAT)
        result["time_domain"]["limitations"].append(PAIR_CAVEAT)
        scenarios[label] = {"request": request, "result": result}
    if any(item["result"]["time_domain"]["status"] != "completed" for item in scenarios.values()):
        return {"status": "blocked", "reason": "SI time reconstruction rejected the derived scenario", "scenarios": scenarios}
    quiet = scenarios["quiet"]["result"]["time_domain"]["receivers"][0]["waveform"]
    active = scenarios["active"]["result"]["time_domain"]["receivers"][0]["waveform"]
    if [p["time_s"] for p in quiet] != [p["time_s"] for p in active]:
        raise ValueError("Quiet and active waveform timestamps differ")
    interference = [{"time_s": a["time_s"], "voltage_v": a["voltage_v"] - q["voltage_v"]}
                    for q, a in zip(quiet, active)]
    return {"status": "completed", "assumption": DC_CAVEAT, "touchstone_text": text,
            "differential": differential_eye(f, s),
            "scenarios": scenarios, "interference": interference,
            "peak_abs_interference_v_at_exported_samples": max(abs(p["voltage_v"]) for p in interference)}


def render_nearfield(output, prefix, result, plt) -> str:
    field = result["fields"].get("nearfield")
    if not isinstance(field, dict) or not field.get("planes"):
        return "<p>No captured E/H near-field plane available.</p>"
    plane = min(field["planes"], key=lambda value: abs(value["frequency_hz"] - 3.2e9))
    coordinates = np.asarray(plane["coordinates_mm"])
    ny, nx = plane["grid_shape"]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for axis, key, label in zip(axes, ("e_v_m", "h_a_m"), ("|E| (V/m)", "|H| (A/m)")):
        magnitudes = []
        for valid, vector in zip(plane["valid"], plane[key]):
            magnitudes.append(float(np.sqrt(np.square(np.asarray(vector, dtype=float)).sum())) if valid else np.nan)
        color = axis.pcolormesh(coordinates[:nx, 0], coordinates[::nx, 1], np.array(magnitudes).reshape(ny, nx), shading="nearest")
        figure.colorbar(color, ax=axis, label=label)
        axis.set(xlabel="X (mm)", ylabel="Y (mm)", title=label)
    figure.suptitle(f"{prefix}: {plane['frequency_hz']/1e9:g} GHz, Z={coordinates[0,2]:g} mm\nEMerge port coefficient excitation; no voltage/power calibration")
    figure.savefig(output / f"{prefix}_nearfield.png", dpi=150)
    plt.close(figure)
    return (f'<h3>Spatial field diagnostic</h3><img src="{prefix}_nearfield.png"><p>Excited port: '
            f'{html.escape(str(field.get("excitation_port")))}. {html.escape(str(field.get("excitation_normalization")))}. '
            'Single-port excitation, not simultaneous PRBS interference. Invalid samples are blank.</p>')


def render_board(output: Path, prefix: str, plt) -> tuple[str, dict]:
    result, evidence = admit_saved(output, prefix)
    f, s, z0 = network_arrays(result)
    assumptions = json.loads((output / f"{prefix}_assumptions.json").read_text(encoding="utf-8"))
    parameters = json.loads((output / f"{prefix}_parameters.json").read_text(encoding="utf-8"))
    diagnostic_html = ""
    diagnostic_path = output / f"{prefix}_quality_checks.json"
    if diagnostic_path.exists():
        diagnostics = json.loads(diagnostic_path.read_text(encoding="utf-8"))
        diagnostic_html = ("<h3>Additional numerical diagnostics</h3><p>Two-frequency finer-mesh and larger-air-domain "
                           "checks did not remove the passivity failure. These are diagnostic checks, not convergence evidence.</p>"
                           f"<pre>{html.escape(json.dumps(diagnostics, indent=2))}</pre>")
    sigma = np.linalg.svd(s, compute_uv=False)[:, 0]
    reciprocity = np.max(np.abs(s - np.swapaxes(s, 1, 2)), axis=(1, 2))
    checks = {"maximum_sampled_singular_value": float(sigma.max()),
              "sampled_passivity_with_1e-6_tolerance": bool(sigma.max() <= 1 + 1e-6),
              "maximum_sampled_reciprocity_residual": float(reciprocity.max()),
              "sampled_reciprocity_with_1e-6_tolerance": bool(reciprocity.max() <= 1e-6),
              "caveat": "Finite sampled checks; no passivity repair, interpolation guarantee or convergence claim."}
    check_warning = ""
    if sigma.max() > 1 + 1e-6 or reciprocity.max() > 1e-6:
        check_warning = ('<p class="warning">Sampled network check warning: '
                         f'maximum singular value {sigma.max():.8g}; maximum reciprocity residual {reciprocity.max():.8g}. '
                         'No repair applied. Eyes are blocked if maximum singular value exceeds 1.001.</p>')
    polarity = "Marble: D=N−P" if prefix == "marble" else "White Rabbit: D=P−N"
    (output / f"{prefix}.s4p").write_text(touchstone_text(f, s, z0, comments=["Actual EMerge samples; no invented DC", str(PORT_MAP)]), encoding="utf-8")
    with (output / f"{prefix}_sparameters.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_hz", "observed_port", "excited_port", "real", "imag", "magnitude_db"])
        for k, frequency in enumerate(f):
            for row in range(4):
                for col in range(4):
                    value = s[k, row, col]
                    writer.writerow([frequency, row + 1, col + 1, value.real, value.imag, 20 * np.log10(max(abs(value), 1e-30))])
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    metrics = {}
    for ax, names in zip(axes, (("S11", "S21", "S33", "S43"), ("S31", "S41", "S13", "S14"))):
        for name in names:
            row, col = int(name[1]) - 1, int(name[2]) - 1
            db = 20 * np.log10(np.maximum(np.abs(s[:, row, col]), 1e-30))
            ax.plot(f / 1e9, db, label=name)
            metrics[name] = {"maximum_db": float(db.max()), "minimum_db": float(db.min())}
        ax.set(xlabel="Frequency (GHz)", ylabel="Magnitude (dB)")
        ax.grid(alpha=.25)
        ax.legend()
    axes[0].set_title("Reflection and through transmission")
    axes[1].set_title("NEXT S31 / FEXT S41; reciprocal S13 / S14")
    figure.suptitle(f"{prefix}: single-ended diagnostic within differential pair · unvalidated")
    figure.savefig(output / f"{prefix}_si.png", dpi=150)
    plt.close(figure)
    modal = mixed_mode(s)
    figure, axis = plt.subplots(figsize=(10, 4), constrained_layout=True)
    for row, col, label in ((1, 0, "Sdd21 differential through"), (0, 0, "Sdd11 differential reflection"),
                            (3, 0, "Scd21 differential → common"), (1, 2, "Sdc21 common → differential")):
        db = 20 * np.log10(np.maximum(np.abs(modal[:, row, col]), 1e-30))
        axis.plot(f / 1e9, db, label=label)
        metrics[label] = {"maximum_db": float(db.max()), "minimum_db": float(db.min())}
    axis.set(xlabel="Frequency (GHz)", ylabel="Normalized modal wave magnitude (dB)",
             title=f"{prefix}: differential transmission and mode conversion · actual FEM samples")
    axis.legend()
    axis.grid(alpha=.25)
    figure.savefig(output / f"{prefix}_mixed_mode.png", dpi=150)
    plt.close(figure)
    eyes = illustrative_eyes(f, s, z0)
    eye_html = f"<p>Eye reconstruction: {html.escape(eyes['status'])}. {html.escape(eyes.get('reason', ''))}</p>"
    if eyes["status"] == "completed":
        (output / f"{prefix}_dc_assumption.s4p").write_text(eyes.pop("touchstone_text"), encoding="utf-8")
        differential = eyes["differential"]
        (output / f"{prefix}_dc_assumed_differential.s2p").write_text(differential.pop("touchstone_text"), encoding="utf-8")
        if differential["status"] == "completed":
            rx = differential["result"]["time_domain"]["receivers"][0]
            figure, axis = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
            for trace in rx["traces"]:
                axis.plot(trace["phase_ui"], trace["voltage_v"], color="tab:green", alpha=.12, linewidth=.6)
            axis.set(xlabel="Phase (UI)", ylabel="Differential receiver (V)",
                     title=f"{prefix}: DC-ASSUMED differential eye · height {rx['eye_height_v']:.4g} V\n100 Ω differential / 25 Ω common matched · 500 Mb/s, 150 ps")
            axis.grid(alpha=.25)
            figure.savefig(output / f"{prefix}_differential_eye_dc_assumed.png", dpi=150)
            plt.close(figure)
        figure, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
        for ax, label in zip(axes, ("quiet", "active")):
            rx = eyes["scenarios"][label]["result"]["time_domain"]["receivers"][0]
            for trace in rx["traces"]:
                ax.plot(trace["phase_ui"], trace["voltage_v"], color="tab:blue", alpha=.12, linewidth=.6)
            ax.set(xlabel="Phase (UI)", ylabel="Victim receiver (V)", title=f"{label} aggressor · eye height {rx['eye_height_v']:.4g} V")
            ax.grid(alpha=.25)
        figure.suptitle(f"{prefix}: ILLUSTRATIVE DC-ASSUMED EYES · 500 Mb/s, 150 ps edges, 50 Ω")
        figure.savefig(output / f"{prefix}_eyes_dc_assumed.png", dpi=150)
        plt.close(figure)
        figure, axis = plt.subplots(figsize=(11, 4), constrained_layout=True)
        points = eyes["interference"]
        axis.plot([p["time_s"] * 1e9 for p in points], [p["voltage_v"] * 1e3 for p in points])
        axis.set(xlabel="Time (ns)", ylabel="Active − quiet victim voltage (mV)", title=f"{prefix}: DC-ASSUMED deterministic interference · exported sample timestamps")
        axis.grid(alpha=.25)
        figure.savefig(output / f"{prefix}_interference_dc_assumed.png", dpi=150)
        plt.close(figure)
        with (output / f"{prefix}_interference_dc_assumed.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["time_s", "active_minus_quiet_v"])
            writer.writerows((p["time_s"], p["voltage_v"]) for p in points)
        time_grid = eyes["scenarios"]["quiet"]["result"]["time_domain"]
        grid_caveat = (f"Time step {time_grid['delta_t_s'] * 1e12:.3f} ps; "
                       f"{time_grid['actual_samples_per_ui']:.3f} samples/UI. "
                       "The 150 ps source edges span about two samples. Cursor timing, eye opening and "
                       "finite-bandwidth periodic impulse tails require time-grid and frequency-grid convergence.")
        eye_html = f'<p class="warning">{html.escape(DC_CAVEAT)}<br>{html.escape(PAIR_CAVEAT)}<br>{html.escape(grid_caveat)}</p><img src="{prefix}_eyes_dc_assumed.png"><img src="{prefix}_interference_dc_assumed.png">'
        if differential["status"] == "completed":
            eye_html += f'<p class="warning">{html.escape(DIFFERENTIAL_CAVEAT)}</p><img src="{prefix}_differential_eye_dc_assumed.png">'
    write_json(output / f"{prefix}_eye_analysis.json", eyes)
    field_html = render_nearfield(output, prefix, result, plt)
    derived_links = (f'<p><a href="{prefix}_dc_assumption.s4p">Derived DC-assumed diagnostic network</a> · '
                     f'<a href="{prefix}_dc_assumed_differential.s2p">Derived DC-assumed differential network</a> · '
                     f'<a href="{prefix}_interference_dc_assumed.csv">DC-assumed interference CSV</a></p>') if eyes["status"] == "completed" else ""
    evidence.update({"checks": checks, "sampled_metrics": metrics, "port_mapping": PORT_MAP,
                     "mixed_mode_order": ["Dnear", "Dfar", "Cnear", "Cfar"], "differential_polarity": polarity,
                     "model_status": result["model_status"], "frequency_count": len(f), "eye_status": eyes["status"]})
    write_json(output / f"{prefix}_analysis.json", evidence)
    block = (f'<section><h2>{html.escape(prefix.replace("_", " ").title())}</h2>'
             f'<p class="warning">{html.escape(PAIR_CAVEAT)}</p><p>Mixed-mode polarity: {polarity}; D=A−B, C=A+B (normalized by √2).</p>'
             f'{check_warning}<img src="{prefix}_si.png"><img src="{prefix}_mixed_mode.png">{eye_html}{field_html}'
             f'<h3>Sampled checks and metrics</h3><pre>{html.escape(json.dumps(evidence, indent=2))}</pre>{diagnostic_html}'
             f'<h3>Solver warnings and limitations</h3><pre>{html.escape(json.dumps(result["issues"], indent=2))}</pre>'
             f'<h3>Board selection and assumptions</h3><pre>{html.escape(json.dumps(assumptions, indent=2))}</pre>'
             f'<details><summary>Executed GUI parameters</summary><pre>{html.escape(json.dumps(parameters, indent=2))}</pre></details>'
             f'<p><a href="{prefix}.s4p">Original FEM Touchstone</a> · <a href="{prefix}_sparameters.csv">Complex S-parameter CSV</a> · '
             f'<a href="{prefix}_result.json">Raw result</a> · <a href="{prefix}_simulation.py">Executed Python</a> · '
             f'<a href="{prefix}_eye_analysis.json">Eye assumptions, requests and results</a></p>'
             f'{derived_links}</section>')
    return block, evidence


def render(output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    blocks, records = [], []
    for prefix in ("marble", "white_rabbit"):
        if (output / f"{prefix}_result.json").exists():
            block, record = render_board(output, prefix, plt)
            blocks.append(block)
            records.append(record)
    if not blocks:
        raise ValueError("No completed EMerge board results found")
    write_json(output / "analysis_manifest.json", records)
    (output / "report.html").write_text('<!doctype html><meta charset="utf-8"><title>EMerge board SI analysis</title>'
        '<style>body{font:16px system-ui;max-width:1250px;margin:auto;padding:25px;background:#f4f6f8;color:#172635}'
        'section{background:white;padding:22px;margin:25px 0;border-radius:10px}img{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}'
        '.warning{background:#fff0cc;padding:15px;border-left:5px solid #b56800}</style>'
        '<h1>Marble and White Rabbit: EMerge SI analysis</h1>'
        '<p>Real FEM samples from bounded board-derived four-port slices. Unvalidated: no full-board qualification, measured correlation or mesh-convergence evidence.</p>'
        f'<p>Port mapping: {html.escape(str(PORT_MAP))}. NEXT = S31; FEXT = S41.</p>'
        '<p>Raw FEM has no DC point. Frequency-domain interference curves use original samples. Any eyes and time interference are separately labeled illustrative DC-assumed scenarios, with deterministic PRBS7 and no compliance/BER claim.</p>'
        + ''.join(blocks), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/emerge-si")
    render(parser.parse_args().output)
