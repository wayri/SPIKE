# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Cheap, assertion-bearing Marble mesh/DC/C refinement audit before field solves."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from python.spike_core.contracts import AnalysisSpec
from python.spike_core.hybrid_mesh import build_hybrid_mesh, nearest_mesh_node, TOPOLOGY_ONLY_BRANCH_KINDS
from python.spike_core.peec_plugin import _connected_component
from python.spike_core.peec_network import solve_port
from python.spike_core.peec_volume_resistance import assemble_overlap_resistance
from python.spike_core.peec_volume_support import zone_basis_support_report
from python.spike_core.quasistatic_capacitance import estimate_branch_capacitance
from python.spike_core.service import _design_from_kicad


def _solve_sparse_dc(mesh, nodes, indices, source, sink):
    """Solve the conforming face-resistor network without a dense PEEC matrix."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve

    positions = {node: i for i, node in enumerate(nodes)}
    free = [node for node in nodes if node != sink]
    free_position = {node: i for i, node in enumerate(free)}
    data, rows, cols = [], [], []
    resistance = np.array([mesh.branches[i].resistance_ohm for i in indices])
    if not np.all(np.isfinite(resistance)) or np.any(resistance <= 0):
        raise ValueError("Conforming DC requires finite positive branch resistance")
    for branch_index, r in zip(indices, resistance):
        branch = mesh.branches[branch_index]
        a, b, conductance = branch.node_p, branch.node_n, 1 / r
        for node in (a, b):
            if node in free_position:
                k = free_position[node]
                rows.append(k); cols.append(k); data.append(conductance)
        if a != sink and b != sink:
            ia, ib = free_position[a], free_position[b]
            rows.extend((ia, ib)); cols.extend((ib, ia))
            data.extend((-conductance, -conductance))
    matrix = coo_matrix((data, (rows, cols)), shape=(len(free), len(free))).tocsr()
    excitation = np.zeros(len(free))
    excitation[free_position[source]] = 1
    potentials = spsolve(matrix, excitation)
    if not np.all(np.isfinite(potentials)):
        raise ValueError("Sparse DC factorization returned nonfinite potentials")
    voltages = np.zeros(len(nodes))
    voltages[[positions[node] for node in free]] = potentials
    currents = np.array([(voltages[positions[mesh.branches[i].node_p]]
                          - voltages[positions[mesh.branches[i].node_n]]) / r
                         for i, r in zip(indices, resistance)])
    balance = np.zeros(len(nodes))
    for branch_index, current in zip(indices, currents):
        branch = mesh.branches[branch_index]
        balance[positions[branch.node_p]] += current
        balance[positions[branch.node_n]] -= current
    balance[positions[source]] -= 1
    balance[positions[sink]] += 1
    return float(voltages[positions[source]]), currents, {
        "relative_residual": float(np.linalg.norm(balance) / np.sqrt(2)),
        "maximum_current_balance_a": float(np.max(np.abs(balance))),
    }


def audit(board: Path, sizes: list[float], *, conforming: bool = False, area_surrogate: bool = False) -> dict:
    design = _design_from_kicad(str(board))
    net = "Net-(C383-Pad1)"
    for field in ("tracks", "vias", "pads", "zones"):
        setattr(design, field, [p for p in getattr(design, field)
                               if str(p.get("net_name", p.get("net", ""))) == net])
    pads = {str(p.get("component_pad")): p for p in design.pads}
    def terminal(name):
        pad = pads[name]
        return {"position_mm": pad["at"], "layer": pad.get("layer", "F.Cu"),
                "net": net, "geometry_anchor": {"id": pad["id"], "type": "pad"}}
    rows = []
    for size in sizes:
        spec = AnalysisSpec(mode="dc" if conforming else "ac", net_names=[net], mesh={
            "target_size_mm": size, "zone_cell_mm": size,
            "max_zone_cells": 1000,
            "max_conductors": 100000 if conforming else 2000,
            "max_conforming_cells": 100000 if conforming else 20000,
            "memory_budget_mb": 2048 if conforming else 512},
            options={"peec_volume_extraction": "enabled"} if conforming else {})
        if conforming:
            from python.spike_core.peec_conforming_mesh import build_conforming_mesh
            mesh = build_conforming_mesh(design, spec)
        else:
            mesh = build_hybrid_mesh(design, spec)
        row = {"size_mm": size, "nodes": len(mesh.nodes), "branches": len(mesh.branches),
               "truncated": mesh.truncated, "issues": [i.code for i in mesh.issues],
               "issue_details": [{"code": i.code, "message": i.message} for i in mesh.issues]}
        if mesh.truncated or any(i.severity == "error" for i in mesh.issues):
            row.update(status="blocked", reason="mesh admission failed")
            rows.append(row)
            continue
        source = nearest_mesh_node(mesh, terminal("U37.18"), net)
        sink = nearest_mesh_node(mesh, terminal("R195.1"), net)
        disconnected = nearest_mesh_node(mesh, terminal("C383.1"), net)
        nodes, indices = _connected_component(mesh, net, source)
        row["routed_connected"] = sink in nodes
        row["disconnected_rejected"] = disconnected not in nodes
        if sink not in nodes:
            row.update(status="blocked", reason="routed terminal disconnected")
            rows.append(row)
            continue
        branches = [mesh.branches[i] for i in indices]
        physical = [i for i, b in enumerate(branches) if b.kind not in TOPOLOGY_ONLY_BRANCH_KINDS]
        if conforming:
            partition = mesh.branch_admission.get("conforming_partition", {})
            outside = partition.get("support_outside_area_max_mm2")
            row["zone_support"] = ({"violating_basis_count": int(outside > 1e-8),
                                     "support_outside_area_max_mm2": outside}
                                    if isinstance(outside, (int, float)) else
                                    {"error": "conforming support certificate missing"})
        else:
            try:
                row["zone_support"] = zone_basis_support_report(design, [branches[i] for i in physical])
            except ValueError as error:
                row["zone_support"] = {"error": str(error)}
        if conforming:
            impedance, currents, quality = _solve_sparse_dc(mesh, nodes, indices, source, sink)
            maximum_balance = quality["maximum_current_balance_a"]
        else:
            resistance = np.diag([b.resistance_ohm for b in branches])
            overlap, _ = assemble_overlap_resistance(design, [branches[i] for i in physical])
            resistance[np.ix_(physical, physical)] = overlap
            impedance, currents, quality = solve_port(mesh, nodes, indices, source, sink, resistance)
            balance = {node: 0j for node in nodes}
            for branch, current in zip(branches, currents):
                balance[branch.node_p] += current
                balance[branch.node_n] -= current
            balance[source] -= 1
            balance[sink] += 1
            maximum_balance = max(abs(v) for v in balance.values())
        estimator = estimate_branch_capacitance
        if area_surrogate:
            from python.spike_core.quasistatic_copper_area import estimate_branch_capacitance as estimator
        _, _, capacitance = estimator(design, spec, [branches[i] for i in physical])
        row.update(status="completed", resistance_ohm=float(impedance.real),
                   capacitance_f=capacitance["total_capacitance_f"],
                   capacitance_metadata=capacitance,
                   physical_bases=len(physical), relative_residual=quality["relative_residual"],
                   maximum_current_balance_a=maximum_balance)
        rows.append(row)
    complete = all(row["status"] == "completed" for row in rows)
    changes = {}
    if complete:
        for key in ("resistance_ohm", "capacitance_f"):
            changes[key] = [abs(a[key] - b[key]) / max(abs(b[key]), 1e-30)
                            for a, b in zip(rows, rows[1:])]
    passed = (complete and len(rows) >= 3
              and all(row["disconnected_rejected"] and row["maximum_current_balance_a"] <= 1e-8
                      and row["relative_residual"] <= 1e-7
                      and not row["zone_support"].get("error")
                      and row["zone_support"].get("violating_basis_count") == 0 for row in rows)
              and (not area_surrogate or all(row["capacitance_metadata"].get("complete_source_coverage", False)
                                             for row in rows))
              and all(max(values[-2:]) <= .02 and values[-1] <= values[-2]
                      for values in changes.values()))
    return {"contract": "spike/peec-cheap-refinement-audit/v1", "passed": passed,
            "production_qualified": False, "scope": "DC and capacitance sensitivity; not L or broadband validation",
            "conforming_sparse_dc_only": conforming,
            "board_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
            "conforming_requested": conforming, "area_surrogate_requested": area_surrogate,
            "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in [Path(__file__), ROOT / "python/spike_core/hybrid_mesh.py",
                                           ROOT / "python/spike_core/peec_volume_resistance.py",
                                           ROOT / "python/spike_core/quasistatic_capacitance.py",
                                           ROOT / "python/spike_core/quasistatic_copper_area.py",
                                           ROOT / "python/spike_core/peec_conforming_mesh.py"]},
            "rows": rows, "relative_changes": changes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--sizes", nargs="+", type=float, default=[1, .5, .25])
    parser.add_argument("--conforming", action="store_true")
    parser.add_argument("--area-surrogate", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if len(args.sizes) < 3 or any(not np.isfinite(x) or x <= 0 for x in args.sizes):
        parser.error("At least three finite positive mesh sizes are required")
    if any(a <= b for a, b in zip(args.sizes, args.sizes[1:])):
        parser.error("Mesh sizes must strictly decrease")
    report = audit(args.board, args.sizes, conforming=args.conforming, area_surrogate=args.area_surrogate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "scope": report["scope"],
                      "rows": [{"size_mm": row["size_mm"], "status": row["status"],
                                "nodes": row["nodes"], "branches": row["branches"],
                                "resistance_ohm": row.get("resistance_ohm"),
                                "capacitance_f": row.get("capacitance_f"),
                                "complete_source_coverage": row.get("capacitance_metadata", {}).get("complete_source_coverage")}
                               for row in report["rows"]],
                      "relative_changes": report["relative_changes"]}, allow_nan=False))
    sys.exit(0 if report["passed"] else 1)
