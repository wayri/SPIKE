# SPDX-License-Identifier: Apache-2.0
"""Run and plot an explicitly assigned board-linked SPIKE object thermal case."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.component_thermal import run_component_thermal
from python.spike_core.kicad_importer import import_kicad_design


def _load_request(path: Path) -> dict:
    request = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(request, dict) or not isinstance(request.get("board"), dict):
        raise ValueError("Request must contain a board object.")
    return request


def _board_context(request: dict) -> tuple[Path, dict, dict]:
    board_info = request["board"]
    board_path = Path(board_info["path"])
    if not board_path.is_absolute():
        board_path = ROOT / board_path
    board_path = board_path.resolve()
    if not board_path.is_file() or board_path.suffix.lower() != ".kicad_pcb":
        raise ValueError("Board path must name an existing KiCad PCB file.")
    digest = hashlib.sha256(board_path.read_bytes()).hexdigest()
    if digest != board_info.get("sha256"):
        raise ValueError("Board SHA-256 does not match the reviewed thermal request.")
    design = import_kicad_design(str(board_path))
    components = {str(item.get("reference", "")): item for item in design.components}
    raw_virtual = board_info.get("virtual_nodes", [])
    if not isinstance(raw_virtual, list) or not all(isinstance(ref, str) and ref for ref in raw_virtual):
        raise ValueError("virtual_nodes must contain reference names.")
    virtual = set(raw_virtual)
    selected = [str(item.get("component_ref", "")) for item in request.get("components", [])]
    unknown = sorted(ref for ref in selected if ref not in components and ref not in virtual)
    if unknown:
        raise ValueError(f"Thermal references absent from the imported board: {unknown}")
    locations = {ref: components[ref]["at"] for ref in selected if ref in components and components[ref].get("at")}
    if any(ref not in locations for ref in selected if ref not in virtual):
        raise ValueError("Every selected physical component needs an imported position.")
    board_data = {
        "source_path": str(board_path), "source_sha256": digest,
        "design_id": design.design_id, "design_name": design.name,
        "board_bounds_mm": design.metadata.get("board_bounds_mm"),
        "component_locations_mm": locations,
        "virtual_nodes": sorted(virtual),
        "import_issues": [{"code": item.code, "severity": item.severity} for item in design.issues],
    }
    return board_path, board_data, components


def _plot(result: dict, board_data: dict, components: dict, target: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.patches import Rectangle

    target.parent.mkdir(parents=True, exist_ok=True)
    nodes = {node["id"]: node for node in result["nodes"]}
    bounds = board_data["board_bounds_mm"]
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise ValueError("Imported board has no drawable bounds.")
    xmin, ymin, xmax, ymax = map(float, bounds)
    refs = list(board_data["component_locations_mm"])
    values = [nodes[ref]["temperature_c"] for ref in refs]
    ambient = float(result["ambient_temperature_c"])
    norm = Normalize(vmin=ambient, vmax=max(values + [ambient + 0.1]))
    figure, (ax_board, ax_trace) = plt.subplots(1, 2, figsize=(14, 5.2), constrained_layout=True)
    ax_board.add_patch(Rectangle((xmin, ymin), xmax - xmin, ymax - ymin,
                                 linewidth=1.5, edgecolor="#40566b", facecolor="#f5f8fb"))
    others = [item.get("at") for item in components.values() if item.get("at")]
    ax_board.scatter([point[0] for point in others], [point[1] for point in others],
                     s=8, color="#b6c2cb", alpha=0.65, label="Other imported footprints")
    positions = [board_data["component_locations_mm"][ref] for ref in refs]
    points = ax_board.scatter([point[0] for point in positions], [point[1] for point in positions],
                              c=values, cmap="inferno", norm=norm, s=190, edgecolors="black", zorder=3)
    for ref, point, value in zip(refs, positions, values):
        ax_board.annotate(f"{ref}  {value:.1f} C", point, xytext=(8, 7),
                          textcoords="offset points", fontsize=9, weight="bold")
    end_time = result["transient"][-1]["time_s"] if result["transient"] else 0
    figure.colorbar(points, ax=ax_board, label=f"Object temperature at {end_time:g} s (C)")
    ax_board.set(xlabel="KiCad X (mm)", ylabel="KiCad Y (mm)",
                 title="Board-bound object temperatures (bounding box, no field)")
    ax_board.set_xlim(xmin - 5, xmax + 5)
    ax_board.set_ylim(ymax + 5, ymin - 5)
    ax_board.set_aspect("equal", adjustable="box")
    for ref in [node["id"] for node in result["nodes"]]:
        times = [frame["time_s"] for frame in result["transient"]]
        temperatures = [frame["temperatures_c"][ref] for frame in result["transient"]]
        ax_trace.plot(times, temperatures, label=f"{ref} ({nodes[ref]['power_w']:.1f} W)")
        ax_trace.axhline(nodes[ref]["steady_temperature_c"], color=ax_trace.lines[-1].get_color(),
                         linestyle=":", alpha=0.5)
    ax_trace.set(xlabel="Time (s)", ylabel="Temperature (C)",
                 title="SPIKE lumped RC transient; dotted = steady solution")
    ax_trace.grid(alpha=0.25)
    ax_trace.legend()
    figure.suptitle(f"{board_data['design_name']} exploratory thermal case | assumed power and paths | approximate", fontsize=12)
    figure.savefig(target, dpi=160)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = _load_request(args.request)
        board_path, board_data, components = _board_context(request)
        protected = {args.request.resolve(), board_path}
        if args.result.resolve() in protected or args.figure.resolve() in protected or args.result.resolve() == args.figure.resolve():
            raise ValueError("Result and figure must be distinct files and cannot replace the input or board.")
        result = run_component_thermal(request)
        if result.get("status") != "completed":
            raise ValueError(result.get("issues", [{}])[0].get("message", "Thermal solve did not complete."))
        result["provenance"]["board_binding"] = board_data
        result["provenance"]["example_assumptions"] = request.get("assumptions", {})
        max_error = float(result["summary"].get("max_transient_energy_balance_error_w", math.nan))
        if not math.isfinite(max_error) or max_error > 1e-7:
            raise ValueError(f"Transient energy balance failed: {max_error} W")
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        _plot(result, board_data, components, args.figure)
        print(json.dumps({"status": result["status"], "model_status": result["model_status"],
                          "max_temperature_c": result["summary"]["max_temperature_c"],
                          "max_transient_balance_error_w": max_error,
                          "result": str(args.result), "figure": str(args.figure)}, indent=2))
        return 0
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"Thermal example blocked: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
