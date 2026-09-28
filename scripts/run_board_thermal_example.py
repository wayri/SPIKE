# SPDX-License-Identifier: Apache-2.0
"""Execute and plot a reviewed KiCad board with SPIKE's bounded plate solver."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.kicad_importer import import_kicad_design


def _render(result: dict, target: Path, board_name: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as effects
    from matplotlib.patches import Rectangle
    import numpy as np

    grid = result["grid"]
    nx, ny = grid["shape"]
    xmin, ymin = grid["origin_mm"]
    dx, dy = grid["spacing_mm"]
    field = np.asarray(grid["temperatures_c"]).reshape(ny, nx)
    layered = bool(result.get("layer_grids"))
    columns = 3 if layered else 2
    fig, axes = plt.subplots(1, columns, figsize=(18 if layered else 13.5, 5.2),
                             gridspec_kw={"width_ratios": [1.5, 1.5, 1] if layered else [1.5, 1]},
                             constrained_layout=True)
    ax, table_ax = axes[0], axes[-1]
    image = ax.imshow(field, extent=[xmin, xmin + nx * dx, ymin + ny * dy, ymin],
                      origin="upper", interpolation="bilinear", cmap="coolwarm")
    fig.colorbar(image, ax=ax, label="Board cell temperature (C)")
    for part in result["components"]:
        x, y = part["position_mm"]
        ax.scatter(x, y, s=55, facecolor="white", edgecolor="black", zorder=3)
        ax.annotate(part["component_ref"], (x, y), xytext=(7, -9), textcoords="offset points",
                    color="white", weight="bold", fontsize=10,
                    path_effects=[effects.withStroke(linewidth=2, foreground="black")])
    for sink in result.get("virtual_heatsinks", []):
        x0 = sink["x_mm"] - sink["width_mm"] / 2
        y0 = sink["y_mm"] - sink["height_mm"] / 2
        ax.add_patch(Rectangle((x0, y0), sink["width_mm"], sink["height_mm"],
                               fill=False, edgecolor="black", linestyle="--", linewidth=1.5))
        ax.annotate(f"{sink['id']} ({sink['heat_flow_w']:.2f} W)", (x0, y0),
                    xytext=(3, -5), textcoords="offset points", fontsize=8,
                    path_effects=[effects.withStroke(linewidth=2, foreground="white")])
    ax.set(xlabel="KiCad X (mm)", ylabel="KiCad Y (mm)",
           title="Board temperature (smooth display of solved cells)")
    if layered:
        top = result["layer_grids"][0]
        coverage = np.asarray(top["copper_coverage"]).reshape(ny, nx)
        copper_ax = axes[1]
        copper_image = copper_ax.imshow(coverage, extent=[xmin, xmin + nx * dx, ymin + ny * dy, ymin],
                                        origin="upper", interpolation="bilinear", vmin=0, vmax=1, cmap="Blues")
        fig.colorbar(copper_image, ax=copper_ax, label="Cell copper fraction")
        copper_ax.set(xlabel="KiCad X (mm)", ylabel="KiCad Y (mm)",
                      title=f"{top['name']} copper coverage" +
                            (" (fuzzy)" if result.get("provenance", {}).get("fuzzy_sigma_mm", 0) else ""))
    table_ax.axis("off")
    rows = [[part["component_ref"], f"{part['board_temperature_c']:.2f}",
             f"{part['case_temperature_c']:.2f}", f"{part['junction_temperature_c']:.2f}"]
            for part in result["components"]]
    table = table_ax.table(cellText=rows, colLabels=["Part", "Board C", "Case C", "Junction C"],
                          loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.8)
    table_ax.set_title("Explicit junction/case thermal paths", pad=16)
    fig.suptitle(board_name + " exploratory SPIKE " + ("layered" if layered else "board-plate") +
                 " thermal result | assumed inputs | approximate")
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _render_animation(result: dict, target: Path, board_name: str) -> None:
    """Save actual returned board frames using one fixed color scale."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter
    import numpy as np

    frames = result.get("transient") or []
    if len(frames) < 2:
        raise ValueError("An animation needs at least two solved transient frames.")
    grid = result["grid"]
    nx, ny = grid["shape"]
    xmin, ymin = grid["origin_mm"]
    dx, dy = grid["spacing_mm"]
    lower = min(float(np.min(frame["layer_temperatures_c"][0])) for frame in frames)
    upper = max(float(np.max(frame["layer_temperatures_c"][0])) for frame in frames)
    fig, ax = plt.subplots(figsize=(8.5, 5), constrained_layout=True)
    field = ax.imshow(np.asarray(frames[0]["layer_temperatures_c"][0]).reshape(ny, nx),
                      extent=[xmin, xmin + nx * dx, ymin + ny * dy, ymin],
                      origin="upper", interpolation="bilinear", cmap="coolwarm",
                      vmin=lower, vmax=max(upper, lower + 1e-6))
    fig.colorbar(field, ax=ax, label="Top-layer solved cell temperature (°C)")
    for part in result["components"]:
        x, y = part["position_mm"]
        ax.scatter(x, y, s=40, facecolor="white", edgecolor="black")
        ax.annotate(part["component_ref"], (x, y), xytext=(5, 3), textcoords="offset points")
    ax.set(xlabel="KiCad X (mm)", ylabel="KiCad Y (mm)")
    def update(index: int):
        current = frames[index]
        field.set_data(np.asarray(current["layer_temperatures_c"][0]).reshape(ny, nx))
        ax.set_title(f"{board_name} approximate board transient · {current['time_s']:.0f} s · peak {current['maximum_board_temperature_c']:.1f} °C")
        return (field,)
    animation = FuncAnimation(fig, update, frames=len(frames), blit=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    animation.save(target, writer=PillowWriter(fps=2))
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    parser.add_argument("--animation", type=Path, help="Optional GIF of solved transient board frames")
    parser.add_argument("--grid-step-mm", type=float, help="Override the example grid spacing for refinement checks")
    parser.add_argument("--fuzzy-sigma-mm", type=float, help="Override layerwise copper blur sigma; 0 uses exact occupancy")
    parser.add_argument("--time-step-s", type=float, help="Override transient implicit time step")
    parser.add_argument("--output-stride", type=int, help="Override number of transient steps between saved frames")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    board = ROOT / payload["source"]["board_path"]
    digest = hashlib.sha256(board.read_bytes()).hexdigest()
    if digest != payload["source"]["board_sha256"]:
        parser.error("Board hash differs from the pinned example input.")
    destinations = [args.input, args.result, args.figure, board] + ([args.animation] if args.animation else [])
    if len({path.resolve() for path in destinations}) != len(destinations):
        parser.error("Input, board, result, figure, and animation paths must differ.")
    design = import_kicad_design(str(board))
    if args.grid_step_mm is not None:
        payload["request"]["board"]["grid_step_mm"] = args.grid_step_mm
    if args.fuzzy_sigma_mm is not None:
        payload["request"]["board"]["fuzzy_sigma_mm"] = args.fuzzy_sigma_mm
    if args.time_step_s is not None:
        if "transient" not in payload["request"]:
            parser.error("--time-step-s requires a transient example input.")
        payload["request"]["transient"]["time_step_s"] = args.time_step_s
    if args.output_stride is not None:
        if "transient" not in payload["request"]:
            parser.error("--output-stride requires a transient example input.")
        payload["request"]["transient"]["output_stride"] = args.output_stride
    result = run_board_thermal(design, payload["request"])
    if result["status"] != "completed":
        parser.error(result["issues"][0]["message"])
    result["provenance"].update(board_source_sha256=digest,
                                example_assumptions=payload.get("assumptions", {}))
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    _render(result, args.figure, board.stem)
    if args.animation:
        _render_animation(result, args.animation, board.stem)
    print(json.dumps({"status": result["status"], "model_status": result["model_status"],
                      "grid_shape": result["grid"]["shape"], "summary": result["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
