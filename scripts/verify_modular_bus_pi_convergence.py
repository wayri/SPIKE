# SPDX-License-Identifier: MIT
"""Reproduce the pinned MODULAR-BUS-NIB DC mesh-convergence evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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
    parser.add_argument("--exact-terminals", action="store_true", help="Bind source and loads to their named board pads")
    arguments = parser.parse_args()
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    solver_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    solver_source_sha256 = {
        name: sha256(ROOT / "python/spike_core" / name)
        for name in (
            "convergence.py", "dc_terminal_validation.py",
            "hybrid_dc_solver.py", "hybrid_mesh.py",
        )
    }
    design = _design_from_kicad(str(BOARD))
    spec = AnalysisSpec(**request["spec"])
    # This run's fourth level exceeds the default 2 GiB sparse-branch admission.
    # This host has 32 GiB physical RAM; a 4 GiB run budget admits that level without
    # changing the board, terminal, material, or numerical tolerances.
    spec = replace(spec, mesh={**spec.mesh, "solver_memory_limit_gb": 4.0})
    terminal_pad_ids: dict[str, str] = {}
    if arguments.exact_terminals:
        terminal_names = ("R19.3", "J14.2", "J20.2", "J15.2")
        sources = [dict(item) for item in spec.sources]
        loads = [dict(item) for item in spec.loads]
        if len(sources) + len(loads) != len(terminal_names):
            raise ValueError("The pinned DC request no longer has the expected source and three loads")
        for terminal, name in zip(sources + loads, terminal_names):
            matches = [pad for pad in design.pads if pad.get("component_pad") == name]
            if len(matches) != 1:
                raise ValueError(f"Pinned board requires exactly one terminal pad {name}; found {len(matches)}")
            pad = matches[0]
            if pad.get("net_name") != "/12Vout" or any(
                abs(float(a) - float(b)) > 1e-6
                for a, b in zip(terminal["position_mm"], pad["at"])
            ):
                raise ValueError(f"Terminal {name} no longer matches the pinned pad geometry")
            terminal["geometry_anchor"] = {"type": "pad", "id": str(pad["id"])}
            terminal_pad_ids[name] = str(pad["id"])
        spec = replace(
            spec, sources=sources, loads=loads,
            options={**spec.options, "require_exact_terminal_geometry": True},
        )
    level_diagnostics: list[dict] = []
    registry = default_solver_registry()
    progress_path = (
        arguments.output.with_name(arguments.output.stem + ".progress.json")
        if arguments.output else None
    )

    def runner(run_design, run_spec):
        result = registry.run(run_design, run_spec)
        level_diagnostics.append({
            "analysis_id": run_spec.analysis_id,
            "status": result.status,
            "source_to_load": result.networks.get("source_to_load"),
            "max_scaled_linear_residual": result.summary.get("max_scaled_linear_residual"),
            "mesh_build_time_s": result.summary.get("mesh_build_time_s"),
            "linear_solve_time_s": result.summary.get("linear_solve_time_s"),
            "geometry_counts": result.summary.get("geometry_counts"),
            "required_metrics": {
                key: result.summary.get(key)
                for key in (
                    "max_load_voltage_drop_v", "total_copper_loss_w",
                    "total_load_current_a", "p95_current_density_a_mm2",
                    "node_count", "edge_count",
                )
            },
            "errors": [issue.__dict__ for issue in result.issues if issue.severity == "error"],
        })
        if progress_path:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint = {
                "contract": "spike/real-board-pi-convergence-progress/v1",
                "board_sha256": sha256(BOARD),
                "request_sha256": sha256(REQUEST),
                "terminal_mode": "exact_pad_anchors" if arguments.exact_terminals else "coordinate_snap",
                "solver_memory_limit_gb": spec.mesh["solver_memory_limit_gb"],
                "solver_revision": solver_revision,
                "solver_source_sha256": solver_source_sha256,
                "completed_levels": level_diagnostics,
            }
            temporary = progress_path.with_name(progress_path.name + ".tmp")
            temporary.write_text(json.dumps(checkpoint, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            temporary.replace(progress_path)
        return result

    report = run_mesh_convergence(
        design, spec, runner,
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
        "terminal_mode": "exact_pad_anchors" if arguments.exact_terminals else "coordinate_snap",
        "terminal_pad_ids": terminal_pad_ids,
        "solver_memory_limit_gb": spec.mesh["solver_memory_limit_gb"],
        "solver_revision": solver_revision,
        "solver_source_sha256": solver_source_sha256,
        "status": report["status"],
        "can_sign_off": report["can_sign_off"],
        "levels": report["levels"],
        "level_diagnostics": level_diagnostics,
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
