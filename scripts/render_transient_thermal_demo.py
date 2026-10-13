# SPDX-License-Identifier: Apache-2.0
"""Render admitted thermal output frames; never interpolate or fabricate samples."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def render(source: Path, output: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.ticker import MaxNLocator
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import numpy as np
    from PIL import Image
    from python.spike_core.assembly_field_thermal import verify_assembly_field_result
    from python.spike_core.assembly_field_handoff import prepare_assembly_field_handoff

    geometry = json.loads((source / "geometry.json").read_text(encoding="utf-8"))
    problem = json.loads((source / "problem.json").read_text(encoding="utf-8"))
    result = json.loads((source / "spike.json").read_text(encoding="utf-8"))
    verify_assembly_field_result(geometry, problem, result)
    handoff = prepare_assembly_field_handoff(geometry)
    vertices = np.asarray(handoff["mesh"]["vertices"]) * 1000  # assembled SI -> mm
    faces = np.asarray([face["vertices"] for face in handoff["boundary_faces"]])
    frames = result["field_result"]["frames"]
    if not 2 <= len(frames) <= 180:
        raise ValueError("Demo requires 2..180 returned frames")
    times = [frame["time_s"] for frame in frames]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Returned frame timestamps must increase")
    normalization = Normalize(min(frame["minimum_k"] for frame in frames),
                              max(frame["maximum_k"] for frame in frames))
    fig = plt.figure(figsize=(10, 6), dpi=100, facecolor="#f5f7fa")
    ax = fig.add_subplot(111, projection="3d")
    surface = Poly3DCollection(vertices[faces], linewidths=.15, edgecolors="#344054")
    ax.add_collection3d(surface)
    ax.auto_scale_xyz(vertices[:, 0], vertices[:, 1], vertices[:, 2])
    span = np.maximum(np.ptp(vertices, axis=0), .5)
    ax.set_box_aspect(span)
    ax.view_init(elev=25, azim=-65)
    ax.set(xlabel="X (mm)", ylabel="Y (mm)", zlabel="Z (mm)")
    ax.yaxis.set_major_locator(MaxNLocator(3))
    ax.zaxis.set_major_locator(MaxNLocator(4))
    fig.colorbar(plt.cm.ScalarMappable(norm=normalization, cmap="inferno"), ax=ax,
                 shrink=.6, pad=.1, label="Boundary triangle mean temperature (K)")
    title = fig.suptitle("")
    fig.text(.05, .04, "Original two-board + STEP benchmark · experimental · declared synthetic conditions\n"
             "Exact returned samples; surface colors average the triangle's three nodal temperatures.", fontsize=9)
    output.mkdir(parents=True, exist_ok=True)
    images = []
    for index, frame in enumerate(frames):
        temperature = np.asarray(frame["node_temperatures_k"])
        if len(temperature) != len(vertices):
            raise ValueError("Frame node count differs from retained mesh")
        surface.set_facecolors(plt.cm.inferno(normalization(temperature[faces].mean(axis=1))))
        title.set_text(f"Transient thermal demonstration · t = {frame['time_s']:.3f} s\n"
                       f"Sample {index + 1}/{len(frames)} · nodal peak {frame['maximum_k']:.3f} K")
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", facecolor=fig.get_facecolor())
        buffer.seek(0)
        images.append(Image.open(buffer).convert("RGB"))
    plt.close(fig)
    images[-1].save(output / "transient-thermal-final.png")
    # Playback at one tenth real time; GIF durations are rounded to 10 ms.
    durations = [max(10, round((b-a)*10000/10)*10) for a, b in zip(times, times[1:])]
    durations.append(1500)
    gif = output / "transient-thermal.gif"
    images[0].save(gif, save_all=True, append_images=images[1:], duration=durations, loop=0)
    with Image.open(gif) as check:
        assert check.n_frames == len(frames) and check.size == (1000, 600)
    evidence = {"source_result_sha256": hashlib.sha256((source / "spike.json").read_bytes()).hexdigest(),
                "result_digest": result["result_digest"], "handoff_digest": handoff["handoff_digest"],
                "sample_times_s": times, "playback_speed": .1, "final_hold_ms": 1500,
                "gif_sha256": hashlib.sha256(gif.read_bytes()).hexdigest(),
                "frames": len(frames), "size": [1000, 600], "interpolation": "none"}
    (output / "transient-thermal-demo.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(render(args.source, args.output)))
