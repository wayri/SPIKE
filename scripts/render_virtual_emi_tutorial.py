"""Render a hash-bound, non-compliance EMI/EMerge artifact view.

SPDX-License-Identifier: Apache-2.0
Copyright (c) 2026 SigHarmonic
"""

from __future__ import annotations

import argparse
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "examples/emerge/antenna_example.kicad_pcb"
EXPECTED_BOARD_SHA256 = "f8fd038633c5b49a3867c8f09dc4fb3341b9be5a4a3cd961a088dbde6a77a2f0"


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def render(run_dir: Path, output: Path) -> dict:
    setup_path = ROOT / "examples/emerge/virtual_emi_setup.json"
    config_path = ROOT / "examples/emerge/antenna_run.json"
    preflight_path = run_dir / "emi-preflight.json"
    screening_path = run_dir / "emi-screening.json"
    evidence_path = run_dir / "emerge_emi_evidence.json"
    result_path = run_dir / "emerge_emi_result.json"
    setup, config, preflight, screening, evidence, result = map(
        _read, (setup_path, config_path, preflight_path, screening_path, evidence_path, result_path)
    )
    board_hash = sha256(BOARD.read_bytes()).hexdigest()
    if board_hash != EXPECTED_BOARD_SHA256 or evidence.get("board_sha256") != board_hash:
        raise ValueError("EMerge result does not bind the pinned KiCad board.")
    params = config["parameters"]
    if (setup["selected_nets"] != [params["signal_net"]] or
            setup["return_nets"] != [params["return_net"]] or
            setup["frequency"]["points"] != params["frequency_points"] or
            setup["frequency"]["start_hz"] != params["frequency_start_hz"] or
            setup["frequency"]["stop_hz"] != params["frequency_stop_hz"]):
        raise ValueError("EMI setup and EMerge configuration do not describe the same study.")
    if (preflight.get("contract") != "spike/emi-preflight/v1" or not preflight.get("can_screen") or
            screening.get("status") != "completed_screening_only" or
            screening["provenance"].get("field_solver_executed") is not False or
            screening["provenance"].get("compliance_prediction") is not False):
        raise ValueError("Expected a completed EMI screen with no inferred field solve or compliance result.")
    frequencies = evidence.get("frequencies_hz", [])
    s11 = evidence.get("s11_db", [])
    radiation = result.get("fields", {}).get("radiation", {})
    cuts = radiation.get("cuts", [])
    if (evidence.get("status") != "completed" or evidence.get("model_status") != "unvalidated" or
            result.get("status") != "completed" or result.get("model_status") != "unvalidated" or
            result.get("provenance", {}).get("solver") != evidence.get("solver") or
            result.get("provenance", {}).get("design_digest_sha256") != evidence.get("design_digest_sha256") or
            len(frequencies) < 2 or len(frequencies) != params["frequency_points"] or
            len(s11) != len(frequencies) or
            len(radiation.get("patterns_3d", [])) != len(frequencies) or
            len(cuts) != len(frequencies) or
            "EMERGE_EMI_NOT_COMPLIANCE" not in evidence.get("issue_codes", [])):
        raise ValueError("EMerge radiation result is missing required executed, unvalidated evidence.")
    first_cut = cuts[0]
    angles = first_cut.get("angles_deg", [])
    relative_db = first_cut.get("relative_amplitude_db", [])
    if len(angles) < 2 or len(angles) != len(relative_db) or not all(
        isinstance(value, (int, float)) and math.isfinite(value) for value in [*angles, *relative_db]
    ):
        raise ValueError("EMerge relative far-field cut is incomplete or non-finite.")

    summary = {
        "contract": "spike/virtual-emi-tutorial-review/v1",
        "status": "completed_experimental_review",
        "board_sha256": board_hash,
        "emi_screening": screening["status"],
        "emi_can_run": preflight["can_run"],
        "emerge_solver": evidence["solver"],
        "emerge_model_status": evidence["model_status"],
        "frequency_count": len(frequencies),
        "minimum_sampled_s11_db": min(s11),
        "radiation_data": "relative, independently peak-normalized angular samples",
        "chamber_settings": setup["chamber"],
        "chamber_physics": "visual preview only",
        "compliance_prediction": False,
        "input_sha256": {"emi_setup": sha256(setup_path.read_bytes()).hexdigest(),
                         "emerge_config": sha256(config_path.read_bytes()).hexdigest()},
        "output_sha256": {"emi_screening": sha256(screening_path.read_bytes()).hexdigest(),
                          "emerge_result": sha256(result_path.read_bytes()).hexdigest()},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    (output.parent / "virtual-emi-review.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lo, hi = min(s11) - 0.5, max(s11) + 0.5
    points = " ".join(
        f"{70 + 530 * i / (len(s11) - 1):.1f},{290 - (value - lo) / (hi - lo) * 180:.1f}"
        for i, value in enumerate(s11)
    )
    cut_floor = min(min(relative_db), -1.0)
    cut_points = " ".join(
        f"{65 + 470 * i / (len(relative_db) - 1):.1f},{290 - (value - cut_floor) / -cut_floor * 180:.1f}"
        for i, value in enumerate(relative_db)
    )
    screen = screening["screening"]["recommended_nets"][0]
    input_view = {
        "board_sha256": board_hash,
        "net_and_return": [params["signal_net"], params["return_net"]],
        "frequency_ghz": [3.0, 4.2],
        "sweep_points": len(frequencies),
        "mesh_resolution_mm": params["mesh_resolution_mm"],
        "chamber": setup["chamber"],
        "metric_source": setup["net_metrics"][0]["source"],
    }
    output_view = {
        "emi_preflight": preflight["status"],
        "emi_can_run": preflight["can_run"],
        "screened_net": screen["net"],
        "screening_score": screen["score"],
        "emerge_status": result["status"],
        "emerge_model_status": result["model_status"],
        "minimum_sampled_s11_db": round(min(s11), 6),
        "radiation": "relative angular samples; no absolute emissions",
        "compliance_prediction": False,
    }
    style = """body{margin:0;padding:28px;background:#081322;color:#e9f2ff;font:16px Segoe UI,Arial}h1{margin:0 0 12px}p{color:#aec4df}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.box{background:#15263b;border:1px solid #3a526e;border-radius:10px;padding:18px}pre{font:12px Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;color:#d8e9fc}.charts{display:flex;gap:14px}svg{background:#0d1b2d}footer{margin-top:14px;color:#ffe0a0;background:#514026;padding:12px;border-radius:7px}small{color:#a5c6d8}"""
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Virtual EMI review</title><style>{style}</style>
<h1>Virtual EMI review: SPIKE screen + EMerge relative field</h1>
<p>Executed artifact view, not an EMI-tab screenshot, calibrated emissions result, or compliance certificate.</p>
<section class="grid"><div class="box"><h2>Input and settings</h2><pre>{escape(json.dumps(input_view, indent=2))}</pre></div>
<div class="box"><h2>Returned result</h2><pre>{escape(json.dumps(output_view, indent=2))}</pre></div></section>
<section class="box" style="margin-top:18px"><h2>EMerge solved samples</h2><div class="charts">
<svg width="700" height="350" viewBox="0 0 700 350" role="img" aria-label="S11 samples from 3 to 4.2 GHz">
<path d="M70 50V290H600" fill="none" stroke="#6b819c"/><polyline points="{points}" fill="none" stroke="#63e7dc" stroke-width="3"/>
<text x="70" y="320" fill="#d8e9fc">3.0 GHz</text><text x="540" y="320" fill="#d8e9fc">4.2 GHz</text>
<text x="90" y="45" fill="#d8e9fc">S11, dB (sampled; unvalidated)</text></svg>
<svg width="600" height="350" viewBox="0 0 600 350" role="img" aria-label="Relative far-field angular cut at the first solved frequency">
<path d="M65 50V290H535" fill="none" stroke="#6b819c"/><polyline points="{cut_points}" fill="none" stroke="#ffcb72" stroke-width="3"/>
<text x="65" y="320" fill="#d8e9fc">0°</text><text x="490" y="320" fill="#d8e9fc">180° theta</text>
<text x="75" y="45" fill="#d8e9fc">3.0 GHz relative E, phi=0° (dB)</text></svg></div></section>
<footer>EMI screening uses illustrative manual metrics. A single candidate has no comparative risk rank. EMerge supplies relative peak-normalized radiation shape, not absolute field strength. The chamber table, absorbers, receiver and pose are visual settings; no regulatory limits were evaluated.</footer>
<p><small>Input SHA-256 prefix {summary['input_sha256']['emi_setup'][:16]} · EMerge result SHA-256 prefix {summary['output_sha256']['emerge_result'][:16]} · Original SPIKE-owned artifact view, MIT, SigHarmonic 2026</small></p></html>"""
    output.write_text(html, encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "build/tutorial-virtual-emi")
    parser.add_argument("--output", type=Path, default=ROOT / "build/tutorial-virtual-emi/virtual-emi.html")
    args = parser.parse_args()
    print(json.dumps(render(args.run_dir, args.output), indent=2))
