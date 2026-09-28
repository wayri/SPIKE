# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Diagnostic Marble finite-contact RT0 DC probe; never release qualification.

This exercises the experimental conforming builder and RT0 solver together.
It does not construct a compatible PEEC inductance matrix or validate AC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.contracts import AnalysisSpec  # noqa: E402
from python.spike_core.peec_conforming_dc import (  # noqa: E402
    assemble_conforming_dc, solve_conforming_dc,
)
from python.spike_core.peec_conforming_mesh import build_conforming_mesh  # noqa: E402
from python.spike_core.peec_rt0_iterative import solve_iterative_conforming_dc  # noqa: E402
from python.spike_core.service import _design_from_kicad  # noqa: E402


NET = "Net-(C383-Pad1)"
SOURCE = "U37.18"
LOAD = "R195.1"
BOARD_SHA256 = "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512"


def _partition_summary(partition: dict) -> dict:
    """Keep diagnostic output bounded; contact records are not result data."""
    return {key: partition[key] for key in (
        "method", "outside_area_tolerance_mm2", "support_outside_area_max_mm2",
        "maximum_omitted_area_fraction", "boundary_depth",
        "visited_box_count", "raw_interior_rectangle_count",
        "coalesced_interior_rectangle_count", "contact_max_edge_mm",
        "contact_subdivision_added_cells", "groups",
    ) if key in partition}


def probe(board: Path, size_mm: float, max_cells: int = 20000,
          max_unknowns: int = 150000, assemble_only: bool = False,
          boundary_depth: int = 7, area_limit: float = 0.01,
          solver: str = "direct", max_iterations: int = 2000,
          timeout_s: float = 60.0) -> dict:
    if not board.is_file() or not math.isfinite(size_mm) or size_mm < 0.05:
        raise ValueError("board and mesh size >= 0.05 mm are required; smaller requests are clamped by the builder")
    if (not 4 <= max_cells <= 100000 or not 10 <= max_unknowns <= 250000
            or not 1 <= boundary_depth <= 12 or not math.isfinite(area_limit)
            or not 0 < area_limit <= 0.02 or solver not in ("direct", "iterative")
            or not 1 <= max_iterations <= 100000
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= 86400):
        raise ValueError("finite mesh, unknown, boundary and area budgets are required")
    with board.open("rb") as stream:
        identity = hashlib.file_digest(stream, "sha256").hexdigest()
    if identity != BOARD_SHA256:
        raise ValueError("reviewed Marble board SHA-256 mismatch")
    design = _design_from_kicad(str(board))
    for field in ("tracks", "vias", "pads", "zones"):
        setattr(design, field, [item for item in getattr(design, field)
            if str(item.get("net_name", item.get("net", ""))) == NET])
    terminal_ids = {str(pad.get("component_pad")): str(pad.get("id"))
                    for pad in design.pads if pad.get("component_pad") in (SOURCE, LOAD)}
    if set(terminal_ids) != {SOURCE, LOAD}:
        raise ValueError("reviewed Marble source/load pad identities were not found")
    spec = AnalysisSpec(mode="dc", net_names=[NET], mesh={
        "target_size_mm": size_mm, "zone_cell_mm": size_mm,
        "max_zone_cells": 1000, "max_conforming_cells": max_cells,
        "max_conductors": max_unknowns, "memory_budget_mb": 2048,
        "conforming_boundary_depth": boundary_depth,
        "conforming_max_omitted_area_fraction": area_limit,
    })
    start = perf_counter()
    mesh = build_conforming_mesh(design, spec)
    elapsed_mesh = perf_counter() - start
    partition = mesh.branch_admission.get("conforming_partition", {})
    result = {"contract": "spike/marble-rt0-dc-diagnostic/v1",
              "qualification": "diagnostic_only", "board_sha256": identity,
              "mesh_size_mm": size_mm, "status": "blocked", "nodes": len(mesh.nodes),
              "solver": solver,
              "boundary_depth": boundary_depth, "area_limit": area_limit,
              "resource_enforcement": "solver work counters only; no OS memory limit",
              "branches": len(mesh.branches), "cells": len(mesh.cells),
              "mesh_seconds": elapsed_mesh,
              "issues": [{"code": issue.code, "message": issue.message}
                         for issue in mesh.issues],
              "partition": _partition_summary(partition)}
    if mesh.truncated or any(issue.severity == "error" for issue in mesh.issues):
        return result
    contacts = partition.get("terminal_contacts", [])
    nodes = {}
    for name in (SOURCE, LOAD):
        matches = {int(contact["node"]) for contact in contacts
                   if contact.get("source_id") == terminal_ids[name]
                   and contact.get("kind") == "pad"}
        if len(matches) != 1:
            result["issues"].append({"code": "PEEC_RT0_TERMINAL_UNRESOLVED",
                "message": f"{name}: expected one finite pad contact, found {len(matches)}"})
            return result
        nodes[name] = matches.pop()
    try:
        if assemble_only:
            system = assemble_conforming_dc(mesh, max_unknowns=max_unknowns)
            result.update(status="assembled_only", terminals=nodes,
                rt0_triangles=system.incidence.shape[0],
                rt0_currents=system.incidence.shape[1],
                rt0_resistance_nonzeros=int(system.resistance.nnz),
                assemble_seconds=perf_counter() - start - elapsed_mesh)
            return result
        if solver == "iterative":
            solved = solve_iterative_conforming_dc(mesh, nodes[SOURCE], nodes[LOAD],
                max_unknowns=max_unknowns, max_triangles=max_unknowns,
                max_iterations=max_iterations, timeout_s=timeout_s)
        else:
            solved = solve_conforming_dc(mesh, nodes[SOURCE], nodes[LOAD],
                                        max_unknowns=max_unknowns)
    except ValueError as error:
        result["issues"].append({"code": "PEEC_RT0_DC_NOT_ADMITTED", "message": str(error)})
        return result
    result.update(status="experimental", terminals=nodes, dc=solved,
                  solve_seconds=perf_counter() - start - elapsed_mesh)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--mesh-size-mm", type=float, required=True)
    parser.add_argument("--max-cells", type=int, default=20000)
    parser.add_argument("--max-unknowns", type=int, default=150000)
    parser.add_argument("--assemble-only", action="store_true")
    parser.add_argument("--boundary-depth", type=int, default=7)
    parser.add_argument("--area-limit", type=float, default=0.01)
    parser.add_argument("--solver", choices=("direct", "iterative"), default="direct")
    parser.add_argument("--max-iterations", type=int, default=2000)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    args = parser.parse_args()
    print(json.dumps(probe(args.board, args.mesh_size_mm,
                           args.max_cells, args.max_unknowns, args.assemble_only,
                           args.boundary_depth, args.area_limit,
                           args.solver, args.max_iterations, args.timeout_s), allow_nan=False))
