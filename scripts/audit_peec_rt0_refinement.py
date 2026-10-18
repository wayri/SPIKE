# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Pinned Marble RT0 DC refinement gate; intentionally not AC/L/C qualification."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.contracts import AnalysisSpec
from python.spike_core.peec_conforming_mesh import build_conforming_mesh
from python.spike_core.peec_conforming_dc import solve_hybridized_conforming_dc
from python.spike_core.peec_plugin import _connected_component
from python.spike_core.service import _design_from_kicad


MARBLE_SHA256 = "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512"


def _sexpr_block(text: str, start: int) -> str:
    """Select one native source expression, ignoring parentheses in strings."""
    depth = 0
    for match in re.finditer(r'"(?:\\.|[^"\\])*"|[()]', text[start:]):
        if match.group() == "(":
            depth += 1
        elif match.group() == ")":
            depth -= 1
            if depth == 0:
                return text[start:start + match.end()]
    raise ValueError("Unterminated native source expression")


def verify_marble_source_topology(board: Path) -> dict:
    """Independent native-coordinate oracle for the corrected backside pad map.

    This pinned source has C383 pad 1 at footprint + (-0.45, 0), with no
    rotation. U37 pad 18 at (0, 2.35) rotates 180 degrees. Both points lie
    in the same stored, simple net-656 B.Cu filled polygon. No importer,
    mesh connectivity, pad-outline helper, or invented copper is used here.
    """
    from shapely.geometry import Point, Polygon, box
    if hashlib.sha256(board.read_bytes()).hexdigest() != MARBLE_SHA256:
        raise ValueError("Native topology oracle requires the pinned Marble board")
    text = board.read_text(encoding="utf-8")
    footprints = {}
    for name in ("C383", "U37"):
        marker = text.index(f'(fp_text reference "{name}"')
        footprints[name] = _sexpr_block(text, text.rfind("(footprint ", 0, marker))
    for name, footprint_at, pad_at in (
            ("C383", "234.9284 157.988", '"1" smd rect locked (at -0.45 0) (size 0.62 0.62)'),
            ("U37", "232.9726 161.8234 180", '"18" smd roundrect locked (at 0 2.35 90) (size 1.05 0.35)')):
        block = footprints[name]
        if f"(at {footprint_at})" not in block or f"(pad {pad_at}" not in block:
            raise ValueError(f"Pinned {name} native transform changed")
    zone_start = text.index('(zone (net 656) (net_name "Net-(C383-Pad1)") (layer "B.Cu")')
    zone = _sexpr_block(text, zone_start)
    filled = _sexpr_block(zone, zone.index("(filled_polygon"))
    points = [(float(x), float(y)) for x, y in re.findall(
        r'\(xy\s+([-+\d.eE]+)\s+([-+\d.eE]+)\)', filled)]
    polygon = Polygon(points)
    c383 = (234.9284 - .45, 157.988)
    u37 = (232.9726, 161.8234 - 2.35)
    pad = box(c383[0] - .31, c383[1] - .31, c383[0] + .31, c383[1] + .31)
    if not polygon.is_valid or not polygon.covers(pad) or not polygon.covers(Point(u37)):
        raise ValueError("Native stored copper does not prove the expected connected pads")
    return {"method": "native KiCad coordinates and same simple filled-polygon containment",
        "board_sha256": MARBLE_SHA256, "filled_polygon_sha256": hashlib.sha256(filled.encode()).hexdigest(),
        "c383_center_mm": c383, "u37_center_mm": u37,
        "c383_pad_area_mm2": pad.area, "c383_copper_overlap_mm2": polygon.intersection(pad).area,
        "c383_fully_covered": True, "u37_center_in_same_filled_polygon": True,
        "supersedes": "Historical C383 isolation expectation used incorrect backside placement."}


def evaluate_rows(rows: list[dict]) -> tuple[bool, list[float]]:
    """Apply the pinned three-level DC gate without treating algebraic fit as physics."""
    complete = len(rows) >= 3 and all(row["status"] == "completed" for row in rows)
    if not complete:
        return False, []
    changes = [abs(a["resistance_ohm"] - b["resistance_ohm"])
               / abs(b["resistance_ohm"]) for a, b in zip(rows, rows[1:])]
    passed = (all(row["routed_connected"] and row.get("c383_connected") is True
        and row["relative_residual"] <= 1e-7
        and row["maximum_cell_kcl_error_a"] <= 1e-8
        and row["maximum_face_kcl_error_a"] <= 1e-8
        and row["relative_energy_error"] <= 1e-7 for row in rows)
        and max(changes[-2:]) <= .02 and changes[-1] <= changes[-2])
    return bool(passed), changes


def audit(board: Path, sizes: list[float], *, max_unknowns: int = 150000,
          max_triangles: int = 150000,
          interior_edge_factor: float | None = None) -> dict:
    if (not board.is_file() or not 10 <= max_unknowns <= 250000
            or not 4 <= max_triangles <= 250000):
        raise ValueError("An existing board and admitted unknown/triangle budgets are required")
    if interior_edge_factor is not None and not 0 < interior_edge_factor <= 1:
        raise ValueError("Interior edge factor must be in (0, 1]")
    source_topology = verify_marble_source_topology(board)
    design = _design_from_kicad(str(board))
    net = "Net-(C383-Pad1)"
    for field in ("tracks", "vias", "pads", "zones"):
        setattr(design, field, [item for item in getattr(design, field)
                               if str(item.get("net_name", item.get("net", ""))) == net])
    pads = {str(item.get("component_pad")): item for item in design.pads}
    for name in ("U37.18", "R195.1", "C383.1"):
        if name not in pads:
            raise ValueError(f"Pinned Marble pad missing: {name}")
    rows = []
    for size in sizes:
        mesh_options = {
            "target_size_mm": size, "zone_cell_mm": size,
            "max_zone_cells": 1000, "max_conductors": 100000,
            "max_conforming_cells": 100000, "memory_budget_mb": 2048}
        if interior_edge_factor is not None:
            mesh_options["conforming_interior_max_edge_mm"] = size * interior_edge_factor
        spec = AnalysisSpec(mode="dc", net_names=[net], mesh=mesh_options,
            options={"peec_volume_extraction": "enabled"})
        mesh = build_conforming_mesh(design, spec)
        row = {"size_mm": size, "interior_max_edge_mm": mesh_options.get("conforming_interior_max_edge_mm"),
               "nodes": len(mesh.nodes), "branches": len(mesh.branches),
               "truncated": mesh.truncated,
               "issues": [{"code": issue.code, "message": issue.message} for issue in mesh.issues]}
        if mesh.truncated or any(issue.severity == "error" for issue in mesh.issues):
            row.update(status="blocked", reason="conforming mesh admission failed")
            rows.append(row)
            continue
        contacts = {}
        for contact in mesh.branch_admission["conforming_partition"]["terminal_contacts"]:
            if contact.get("kind") == "pad":
                contacts.setdefault(str(contact["source_id"]), set()).add(int(contact["node"]))
        mapped = {}
        for name in ("U37.18", "R195.1", "C383.1"):
            candidates = contacts.get(str(pads[name]["id"]), set())
            if len(candidates) != 1:
                row.update(status="blocked", reason=f"{name} has {len(candidates)} fixed contact anchors")
                break
            mapped[name] = next(iter(candidates))
        if row.get("status") == "blocked":
            rows.append(row)
            continue
        nodes, _ = _connected_component(mesh, net, mapped["U37.18"])
        row["routed_connected"] = mapped["R195.1"] in nodes
        row["c383_connected"] = mapped["C383.1"] in nodes
        if not row["routed_connected"] or not row["c383_connected"]:
            row.update(status="blocked", reason="pinned terminal connectivity changed")
            rows.append(row)
            continue
        try:
            result = solve_hybridized_conforming_dc(mesh, mapped["U37.18"],
                mapped["R195.1"], max_unknowns=max_unknowns,
                max_triangles=max_triangles)
        except ValueError as error:
            row.update(status="blocked", reason=str(error))
        else:
            row.update(status="completed", **result)
        rows.append(row)
    passed, changes = evaluate_rows(rows)
    return {"contract":"spike/peec-hybrid-rt0-dc-refinement-audit/v2",
        "source_topology": source_topology,
        "disconnected_control": "Separate manufactured disconnected-kernel tests; C383.1 is physically connected in this board.",
        "passed_dc_refinement_gate":bool(passed), "full_peec_qualified":False,
        "scope":"experimental sparse DC only; no L/C/AC/thermal or release qualification",
        "board_sha256":hashlib.sha256(board.read_bytes()).hexdigest(),
        "source_sha256":{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), ROOT/"python/spike_core/peec_conforming_mesh.py",
                         ROOT/"python/spike_core/peec_conforming_dc.py",
                         ROOT/"python/spike_core/conforming_local_refinement.py")},
        "max_unknowns":max_unknowns, "max_triangles":max_triangles,
        "interior_edge_factor":interior_edge_factor,
        "sizes_mm":sizes, "rows":rows,
        "relative_resistance_changes":changes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--sizes", nargs="+", type=float, default=[1,.5,.25])
    parser.add_argument("--max-unknowns", type=int, default=150000)
    parser.add_argument("--max-triangles", type=int, default=150000)
    parser.add_argument("--interior-edge-factor", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.sizes) < 3 or any(not (0 < x < float("inf")) for x in args.sizes):
        parser.error("At least three finite positive mesh sizes are required")
    if any(a <= b for a,b in zip(args.sizes,args.sizes[1:])):
        parser.error("Mesh sizes must strictly decrease")
    report = audit(args.board,args.sizes,max_unknowns=args.max_unknowns,
        max_triangles=args.max_triangles,
        interior_edge_factor=args.interior_edge_factor)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"passed_dc_refinement_gate":report["passed_dc_refinement_gate"],
        "rows":[{"size_mm":row["size_mm"],"status":row["status"],
                 "resistance_ohm":row.get("resistance_ohm"),"reason":row.get("reason")}
                for row in report["rows"]],
        "relative_resistance_changes":report["relative_resistance_changes"]}))
    sys.exit(0 if report["passed_dc_refinement_gate"] else 1)
