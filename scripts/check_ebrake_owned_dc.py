# SPDX-License-Identifier: Apache-2.0
"""Retain actual EBrake owned-mode DC runs with unchanged convergence gates.

This is an assumed 24 V/1 A conductivity diagnostic on the original 3Vin
selection. No source geometry, terminal identity or numerical threshold is
modified. Exit zero requires both public CLI execution and convergence.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.contracts import AnalysisSpec
from python.spike_core.convergence import run_mesh_convergence
from python.spike_core.hybrid_dc_solver import solve_hybrid_dc
from python.spike_core.kicad_importer import import_kicad_design

SOURCES = (
    "scripts/check_ebrake_owned_dc.py", "python/spike_core/hybrid_mesh.py",
    "python/spike_core/hybrid_owned_copper.py", "python/spike_core/hybrid_drilled_roundrect.py",
    "python/spike_core/hybrid_dc_solver.py", "python/spike_core/dc_result_utils.py",
    "python/spike_core/convergence.py", "python/spike_core/cli.py",
    "python/spike_core/kicad_importer.py", "python/core/board_parser.py",
)


def snapshot():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-convergence", action="store_true", help="Run only public CLI admission/solve; cannot qualify convergence")
    args = parser.parse_args()
    folder = args.output_dir.resolve()
    if not folder.is_relative_to(ROOT) or folder.exists():
        parser.error("Select a fresh output directory inside this repository")
    folder.mkdir(parents=True)
    before = snapshot()
    board = ROOT / "app/public/demo/ebrake1.kicad_pcb"
    board_digest = hashlib.sha256(board.read_bytes()).hexdigest()
    if board_digest != "d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca":
        parser.error("Pinned EBrake source changed; review the study")
    design = import_kicad_design(str(board))
    spec = AnalysisSpec(mode="dc", net_names=["3Vin"],
        sources=[{"id": "fixture-source", "position_mm": [165.1, 116.3], "layer": "B.Cu", "voltage_v": 24.0}],
        loads=[{"id": "fixture-load", "position_mm": [149.05, 116.3], "layer": "B.Cu", "current_a": 1.0}],
        mesh={"target_size_mm": 1.0, "zone_cell_mm": 1.0, "pad_zone_coupling": "owned_shared_faces"},
        limits={"max_voltage_drop_mv": 50})
    request = {"contract": "spike/analysis-request/v1", "design": design.to_dict(), "spec": asdict(spec)}
    request_path = folder / "request.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    output = folder / "cli-result.json"
    command = [sys.executable, "-m", "python.spike_core.cli", "--quiet", "--output", str(output), "run", str(request_path)]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=240)
    (folder / "cli.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
    result = json.loads(output.read_text(encoding="utf-8")) if output.is_file() else {}
    report = {"contract": "spike/ebrake-owned-dc-audit/v1", "production_qualified": False,
        "board_sha256": board_digest, "sources_before": before, "command": command,
        "cli_exit_code": completed.returncode, "cli_status": result.get("status"),
        "cli_model_status": result.get("model_status"), "cli_issues": result.get("issues", []),
        "scope": "Assumed original diagnostic terminals; explicit opt-in approximate DC only. No full-board SI/PI qualification."}
    if not args.skip_convergence:
        study = run_mesh_convergence(design, spec, solve_hybrid_dc,
            levels=[2, 1, .5, .25], minimum_levels=3)
        (folder / "convergence.json").write_text(json.dumps(study, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        report["convergence_status"] = study.get("status")
        report["can_sign_off"] = study.get("can_sign_off")
        report["comparisons"] = study.get("comparisons", [])
    after = snapshot()
    report["sources_after"] = after
    report["board_sha256_after"] = hashlib.sha256(board.read_bytes()).hexdigest()
    report["sources_unchanged"] = before == after and report["board_sha256_after"] == board_digest
    report["cli_completed"] = completed.returncode == 0 and result.get("status") == "completed"
    report["passed"] = report["cli_completed"] and before == after and report.get("can_sign_off") is True
    (folder / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("cli_status", "cli_model_status", "convergence_status", "can_sign_off", "sources_unchanged", "passed")}))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
