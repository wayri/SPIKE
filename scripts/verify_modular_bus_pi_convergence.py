# SPDX-License-Identifier: MIT
"""Reproduce the pinned MODULAR-BUS-NIB DC mesh-convergence evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from python.spike_core.contracts import AnalysisSpec
from python.spike_core.convergence import run_mesh_convergence
from python.spike_core.service import _design_from_kicad
from python.spike_core.solver_plugins import default_solver_registry


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "app/public/demo/MODULAR-BUS-NIB.kicad_pcb"
REQUEST = ROOT / "docs/validation/modular-bus-nib-12vout-dcir-request.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write compact JSON evidence to this path")
    arguments = parser.parse_args()
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    design = _design_from_kicad(str(BOARD))
    spec = AnalysisSpec(**request["spec"])
    # This run's fourth level exceeds the default 2 GiB sparse-branch admission.
    # This host has 32 GiB physical RAM; a 4 GiB run budget admits that level without
    # changing the board, terminal, material, or numerical tolerances.
    spec = replace(spec, mesh={**spec.mesh, "solver_memory_limit_gb": 4.0})
    report = run_mesh_convergence(
        design, spec, default_solver_registry().run,
        levels=(2.0, 1.0, 0.5, 0.25),
        minimum_levels=3,
        stop_when_converged=False,
    )
    evidence = {
        "contract": "spike/real-board-pi-convergence-evidence/v1",
        "board": str(BOARD.relative_to(ROOT)).replace("\\", "/"),
        "board_sha256": sha256(BOARD),
        "request": str(REQUEST.relative_to(ROOT)).replace("\\", "/"),
        "request_sha256": sha256(REQUEST),
        "analysis_mode": spec.mode,
        "net_names": spec.net_names,
        "solver_memory_limit_gb": spec.mesh["solver_memory_limit_gb"],
        "status": report["status"],
        "can_sign_off": report["can_sign_off"],
        "levels": report["levels"],
        "comparison_history": report["comparison_history"],
        "thresholds": report["thresholds"],
        "limitations": report["limitations"],
    }
    output = json.dumps(evidence, indent=2, allow_nan=False) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if report["can_sign_off"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
