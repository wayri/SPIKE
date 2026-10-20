# SPDX-License-Identifier: Apache-2.0
"""Read pinned native terminal geometry without importing a solver or inventing contacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from math import cos, dist, hypot, radians, sin
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BOARDS = {
    "ebrake": ("app/public/demo/ebrake1.kicad_pcb",
        "d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca"),
    "marble": ("build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb",
        "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expression(text):
    """Minimal independent native-expression reader; quoted parentheses are data."""
    stack, result = [], None
    for match in re.finditer(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text):
        value = match.group()
        if value == "(":
            node = []
            if stack:
                stack[-1].append(node)
            elif result is not None:
                raise ValueError("Multiple root expressions")
            else:
                result = node
            stack.append(node)
        elif value == ")":
            if not stack:
                raise ValueError("Unbalanced expression")
            stack.pop()
        elif not stack:
            raise ValueError("Native atom outside root")
        else:
            stack[-1].append(json.loads(value) if value.startswith('"') else value)
    if stack or not result or result[0] != "kicad_pcb":
        raise ValueError("Incomplete native board expression")
    return result


def children(node, key):
    return [item for item in node if isinstance(item, list) and item and item[0] == key]


def child(node, key, default=()):
    items = children(node, key)
    return items[0][1:] if items else default


def native_geometry(text):
    board = expression(text)
    nets = {item[1]: item[2] for item in children(board, "net")}
    tracks = []
    for item in children(board, "segment"):
        tracks.append({"uuid": child(item, "uuid", child(item, "tstamp", [""]))[0],
            "start_mm": list(map(float, child(item, "start"))),
            "end_mm": list(map(float, child(item, "end"))),
            "width_mm": float(child(item, "width")[0]),
            "layer": child(item, "layer")[0], "net": nets[child(item, "net")[0]]})
    pads = []
    for footprint in children(board, "footprint") + children(board, "module"):
        refs = [row for row in children(footprint, "property") if row[1] == "Reference"]
        refs += [row for row in children(footprint, "fp_text") if row[1] == "reference"]
        if not refs:
            continue
        ref = refs[0][2]
        at = list(map(float, child(footprint, "at")))
        angle = radians(-(at[2] if len(at) > 2 else 0))
        for item in children(footprint, "pad"):
            local = list(map(float, child(item, "at", [0, 0])))
            center = [at[0]+cos(angle)*local[0]-sin(angle)*local[1],
                      at[1]+sin(angle)*local[0]+cos(angle)*local[1]]
            drill = child(item, "drill", [])
            oval = bool(drill and drill[0] == "oval")
            dimensions = [float(v) for v in drill[(1 if oval else 0):] if not isinstance(v, list)]
            offset = [v for v in drill if isinstance(v, list) and v and v[0] == "offset"]
            padnet = child(item, "net", [""])
            pads.append({"component_pad": ref+"."+item[1], "type": item[2], "shape": item[3],
                "center_mm": center, "size_mm": list(map(float, child(item, "size"))),
                "native_pad_angle_deg": local[2] if len(local) > 2 else 0,
                "layers": list(child(item, "layers")),
                "net": nets.get(padnet[0], padnet[1] if len(padnet) > 1 else ""),
                "drill_shape": "oval" if oval else "circle" if dimensions else "none",
                "drill_dimensions_mm": dimensions, "has_drill_offset": bool(offset),
                "uuid": child(item, "uuid", child(item, "tstamp", [""]))[0]})
    return tracks, pads


def segment_distance(point, a, b):
    length2 = sum((b[i]-a[i])**2 for i in (0, 1))
    fraction = max(0, min(1, sum((point[i]-a[i])*(b[i]-a[i]) for i in (0, 1))/length2)) if length2 else 0
    return dist(point, [a[i]+fraction*(b[i]-a[i]) for i in (0, 1)])


def terminal_fact(point, tracks, pads):
    covering = []
    for track in tracks:
        if track["net"] != "3Vin" or track["layer"] != "B.Cu":
            continue
        distance = segment_distance(point, track["start_mm"], track["end_mm"])
        if distance <= track["width_mm"]/2:
            covering.append(dict(track, centerline_distance_mm=distance))
    voids = []
    for pad in pads:
        if (pad["drill_shape"] == "circle" and not pad["has_drill_offset"]
                and pad["drill_dimensions_mm"] and "*.Cu" in pad["layers"]):
            radius = pad["drill_dimensions_mm"][0]/2
            distance = hypot(*(point[i]-pad["center_mm"][i] for i in (0, 1)))
            if distance < radius:
                voids.append(dict(pad, center_distance_mm=distance, drill_radius_mm=radius))
    return {"position_mm": list(point), "layer": "B.Cu", "net": "3Vin",
        "finite_electrode_footprint_specified": False,
        "track_primitive_envelopes_covering_point": covering,
        "centered_circular_through_drill_voids_covering_point": voids,
        "interpretation": "Track-envelope overlap does not override a physical drill void or specify an electrode footprint."}


def audit(root=ROOT):
    before = {name: digest(root / spec[0]) for name, spec in BOARDS.items()}
    if before != {name: spec[1] for name, spec in BOARDS.items()}:
        raise ValueError("Pinned board changed; contact facts require a new review")
    e_tracks, e_pads = native_geometry((root / BOARDS["ebrake"][0]).read_text(encoding="utf-8"))
    _, m_pads = native_geometry((root / BOARDS["marble"][0]).read_text(encoding="utf-8"))
    selected = [pad for pad in m_pads if pad["component_pad"] in {"U37.18", "R195.1", "C383.1"}]
    if len(selected) != 3:
        raise ValueError("Pinned Marble pads are not unique")
    after = {name: digest(root / spec[0]) for name, spec in BOARDS.items()}
    return {"contract": "spike/board-terminal-contact-audit/v1", "audit_execution_completed": True,
        "production_qualified": False, "full_board_pisi_ready": False,
        "board_sha256_before": before, "board_sha256_after": after, "sources_unchanged": before == after,
        "ebrake_original_dc": {"source": dict(terminal_fact((165.1, 116.3), e_tracks, e_pads), voltage_v=24),
            "load": dict(terminal_fact((149.05, 116.3), e_tracks, e_pads), current_a=1)},
        "ebrake_original_ac": "Net /AOUT1, 1 kHz to 100 kHz, three points; fixture supplies no explicit source/load electrodes.",
        "marble_native_pads": selected,
        "marble_contact_scope": "Finite pad geometry exists. Existing RT0 probe assumes uniform finite-area injection and conjugate averaged voltage; this is not measured hardware contact validation.",
        "decision": "Keep original EBrake positions and unspecified contact areas unchanged. No finite footprint, new pad terminal, or sensitivity model is authorized by this audit."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = args.output.resolve()
    if not path.is_relative_to(ROOT) or path.exists():
        parser.error("Select a fresh repository output path")
    result = audit()
    result["audit_script_sha256"] = digest(Path(__file__))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"sources_unchanged": result["sources_unchanged"],
        "ebrake_contact_footprints_specified": False, "full_board_pisi_ready": False}))
    return 0 if result["sources_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
