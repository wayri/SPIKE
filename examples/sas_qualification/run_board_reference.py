# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Replay hashed native copper without modifying the source SAS workspace."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.layered_board_thermal import solve_layered_board_thermal


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_fields(result, output, stem):
    with (output / f"{stem}-components.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        columns = ("component_ref", "power_w", "board_temperature_c", "case_temperature_c", "junction_temperature_c")
        writer.writerow([*columns, "temperature_status"])
        for part in [*result["components"], *result.get("board_heat_sources", [])]:
            writer.writerow([*(part[key] for key in columns), part.get("temperature_status", "package_resistance_estimate")])
    nx, ny = result["grid"]["shape"]
    grid = result["grid"]
    if "x_edges_mm" in grid:
        xs, ys = grid["x_edges_mm"], grid["y_edges_mm"]
    else:
        dx, dy = grid["spacing_mm"]
        x0, y0 = grid["origin_mm"]
        xs = [x0 + i * dx for i in range(nx + 1)]
        ys = [y0 + i * dy for i in range(ny + 1)]
    with (output / f"{stem}-fields.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["layer", "x_mm", "y_mm", "temperature_c", "copper_coverage_fraction"])
        for layer in result["layer_grids"]:
            for cell in range(nx * ny):
                ix, iy = cell % nx, cell // nx
                writer.writerow([layer["name"], (xs[ix] + xs[ix + 1]) / 2,
                                 (ys[iy] + ys[iy + 1]) / 2,
                                 layer["temperatures_c"][cell], layer["copper_coverage"][cell]])


def replay(case, output):
    board = case / "blade.kicad_pcb"
    request_path = case / "board_thermal_request.json"
    source_hashes = {str(p): digest(p) for p in (board, request_path)}
    engine_hashes = {str(p.relative_to(ROOT)): digest(p) for p in (
        ROOT / "python/core/board_parser.py",
        ROOT / "python/spike_core/kicad_importer.py",
        ROOT / "python/spike_core/thermal_copper_geometry.py",
        ROOT / "python/spike_core/layered_board_thermal.py", Path(__file__))}
    design = import_kicad_design(str(board))
    native = [z for z in design.zones if z.get("source_kind") == "filled_zone"]
    if not native or any(z.get("source_fill_provenance_complete") is not True for z in native):
        raise ValueError("Native filled copper must retain complete provenance")
    output.mkdir(parents=True, exist_ok=False)
    base = json.loads(request_path.read_text(encoding="utf-8"))
    cases = []
    for step in (5.0, 2.5, 2.0):
        request = json.loads(json.dumps(base))
        request.pop("transient", None)
        request["board"]["include_zones"] = True
        request["board"]["grid_step_mm"] = step
        request["study_scope"] = "Native filled zones included; prescribed square heat contact and convection retained; refinement experiment only."
        result = solve_layered_board_thermal(design, request)
        stem = f"grid-{step:g}mm"
        for suffix, payload in (("request", request), ("result", result)):
            (output / f"{stem}-{suffix}.json").write_text(
                json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        export_fields(result, output, stem)
        cases.append({"step_mm": step, "status": result["status"], "summary": result["summary"],
                      "junction_temperature_c": {v["component_ref"]: v["junction_temperature_c"] for v in result["components"]}})
        print(json.dumps(cases[-1], allow_nan=False), flush=True)
    comparisons = []
    for a, b in zip(cases, cases[1:]):
        differences = {ref: abs(b["junction_temperature_c"][ref] - value)
                       for ref, value in a["junction_temperature_c"].items()}
        comparisons.append({"from_step_mm": a["step_mm"], "to_step_mm": b["step_mm"],
                            "junction_change_k": differences,
                            "maximum_junction_change_k": max(differences.values()),
                            "peak_board_change_k": abs(b["summary"]["maximum_board_temperature_c"] - a["summary"]["maximum_board_temperature_c"])})
    if any(digest(Path(path)) != sha for path, sha in source_hashes.items()):
        raise ValueError("Source changed during replay; no evidence commit")
    if any(digest(ROOT / path) != sha for path, sha in engine_hashes.items()):
        raise ValueError("Engine changed during replay; no evidence commit")
    # Explicit developer comparison criterion, not an installed hardware gate.
    comparison_passed = all(max(c["maximum_junction_change_k"], c["peak_board_change_k"]) < 0.1 for c in comparisons)
    report = {"contract": "spike/native-copper-replay-evidence/v1", "source_hashes": source_hashes,
              "engine_hashes": engine_hashes, "native_filled_fragments": len(native),
              "overrides": ["include_zones=true", "steady only", "grid_step_mm=5/2.5/2"],
              "cases": cases, "comparisons": comparisons, "comparison_threshold_k": 0.1,
              "comparison_gate_passed": comparison_passed,
              "mesh_convergence_status": "undemonstrated", "hardware_qualified": False,
              "limitations": ["Square contact at imported component centroid, not exact drain-pad injection",
                              "Sampled scalar copper coverage, not conforming material interfaces",
                              "Assumed convection and plating; no assembled airflow calculation",
                              "Single Blade only; Base heat and downstream four-board air remain unmapped"]}
    (output / "evidence.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    artifacts = {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output / "COMMITTED.json").write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay(args.case, args.output)
    print(json.dumps({"comparison_gate_passed": report["comparison_gate_passed"],
                      "mesh_convergence_status": report["mesh_convergence_status"], "hardware_qualified": False}))
