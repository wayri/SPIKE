# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Diagnose PEEC basis support and contact loss without native L extraction.

Requires NumPy and Shapely in the diagnostic interpreter. This deliberately
inspects the unqualified mesh, bypassing volume-adapter admission; its R solve
is evidence about the defect, never an admitted physical extraction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.contracts import AnalysisSpec, DesignIR  # noqa: E402
from python.spike_core.hybrid_mesh import (  # noqa: E402
    TOPOLOGY_ONLY_BRANCH_KINDS, _normalize_filled_zone_polygon,
    build_hybrid_mesh, nearest_mesh_node,
)
from python.spike_core.peec_network import solve_port  # noqa: E402
from python.spike_core.peec_plugin import _connected_component  # noqa: E402
from python.spike_core.peec_volume_resistance import (  # noqa: E402
    _basis, assemble_overlap_resistance,
)
from python.spike_core.service import _design_from_kicad  # noqa: E402

PINNED_SHA256 = "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512"
NET = "Net-(C383-Pad1)"


def triangular_face_oracle() -> dict:
    """Independent polynomial integration for the proposed two-prism basis.

    A square of side a is split on x+y=a. Opposite vertices are (0,0)
    and (a,a). Current flows from the lower triangle through the common face.
    These are reference values, not a supported native basis implementation.
    """
    side, thickness, conductivity = 1e-3, 35e-6, 5.8e7
    area = side * side / 2
    normal = np.array([1.0, 1.0]) / np.sqrt(2.0)
    face_area = side * np.sqrt(2.0) * thickness
    face_points = [side * np.array([u, 1 - u]) for u in (0.1, 0.5, 0.9)]
    fluxes = [[float(np.dot(point / (2 * area * thickness), normal) * face_area),
               float(np.dot((side - point) / (2 * area * thickness), normal) * face_area)]
              for point in face_points]
    # Equal weights at barycentric permutations of (2/3, 1/6, 1/6)
    # integrate degree-two polynomials exactly; b dot b has degree two.
    points = side * np.array([[1/6, 1/6], [2/3, 1/6], [1/6, 2/3]])
    lower = points / (2 * area * thickness)
    upper_points = side - points
    upper = (side - upper_points) / (2 * area * thickness)
    resistance = float(area * thickness / conductivity *
                       (np.mean(np.sum(lower**2, axis=1)) +
                        np.mean(np.sum(upper**2, axis=1))))
    expected = 1 / (3 * conductivity * thickness)
    if not np.allclose(fluxes, 1.0, rtol=0, atol=1e-14):
        raise AssertionError("manufactured face flux is not one ampere")
    if not np.isclose(resistance, expected, rtol=1e-14, atol=0):
        raise AssertionError("manufactured affine-basis loss differs from analytical oracle")
    return {"implemented_native_basis": False, "side_m": side, "thickness_m": thickness,
            "common_face_flux_per_ampere": fluxes,
            "two_triangle_resistance_ohm": resistance,
            "analytical_resistance_ohm": expected}


def audit(design: DesignIR, size_mm: float) -> dict:
    spec = AnalysisSpec(mode="ac", net_names=[NET], mesh={
        "target_size_mm": size_mm, "zone_cell_mm": size_mm,
        "max_zone_cells": 1000, "max_conductors": 2000, "memory_budget_mb": 512,
    })
    mesh = build_hybrid_mesh(design, spec)
    zones = {str(zone["id"]): Polygon(_normalize_filled_zone_polygon(
        [tuple(point) for point in zone["points"]]
    )).buffer(0) for zone in design.zones}
    outside = []
    for branch in mesh.branches:
        if branch.kind != "zone":
            continue
        support = Polygon(_basis(design, branch).polygon)
        area = support.difference(zones[branch.source_id]).area
        if area > 1e-8:
            outside.append({"branch_id": branch.id, "source_id": branch.source_id,
                            "outside_area_mm2": area, "support_area_mm2": support.area})
    pads = {str(pad.get("component_pad")): pad for pad in design.pads}
    terminals = {}
    for name in ("U37.18", "R195.1", "C383.1"):
        pad = pads[name]
        node = nearest_mesh_node(mesh, {
            "position_mm": pad["at"], "layer": pad.get("layer", "F.Cu"),
            "net": NET, "geometry_anchor": {"id": pad["id"], "type": "pad"},
        }, NET)
        if node is None:
            raise ValueError(f"unresolved pinned terminal {name}")
        terminals[name] = {"source_id": pad["id"], "pad_at_mm": pad["at"],
                           "pad_size_mm": pad["size"], "node": node,
                           "node_at_mm": [mesh.nodes[node].x_mm, mesh.nodes[node].y_mm]}
    source, sink = terminals["U37.18"]["node"], terminals["R195.1"]["node"]
    nodes, indices = _connected_component(mesh, NET, source)
    if sink not in nodes:
        raise ValueError("routed pinned load disconnected")
    branches = [mesh.branches[index] for index in indices]
    physical_positions = [i for i, branch in enumerate(branches)
                          if branch.kind not in TOPOLOGY_ONLY_BRANCH_KINDS]
    resistance = np.diag([branch.resistance_ohm for branch in branches])
    physical, resistance_quality = assemble_overlap_resistance(
        design, [branches[i] for i in physical_positions],
    )
    resistance[np.ix_(physical_positions, physical_positions)] = physical
    port, currents, quality = solve_port(mesh, nodes, indices, source, sink,
                                         resistance, diagnostics=True)
    balance = {node: 0j for node in nodes}
    attachments = []
    loss_by_kind = {}
    for branch, current in zip(branches, currents):
        balance[branch.node_p] += current
        balance[branch.node_n] -= current
        if branch.kind in TOPOLOGY_ONLY_BRANCH_KINDS:
            loss = float(abs(current) ** 2 * branch.resistance_ohm)
            loss_by_kind[branch.kind] = loss_by_kind.get(branch.kind, 0.0) + loss
            attachments.append({"branch_id": branch.id, "kind": branch.kind,
                                "length_mm": branch.length_mm, "width_mm": branch.width_mm,
                                "loss_w_at_1a": loss})
    balance[source] -= 1.0
    balance[sink] += 1.0
    return {
        "mesh_size_mm": size_mm, "connected_physical_basis_count": len(physical_positions),
        "physical_basis_count": sum(branch.kind not in TOPOLOGY_ONLY_BRANCH_KINDS
                                    for branch in mesh.branches),
        "zone_basis_count": sum(branch.kind == "zone" for branch in mesh.branches),
        "support_passed": not outside, "outside_basis_count": len(outside),
        "sum_outside_area_mm2": sum(item["outside_area_mm2"] for item in outside),
        "outside_bases": outside, "terminals": terminals,
        "original_C383_load_connected": terminals["C383.1"]["node"] in nodes,
        "diagnostic_port_resistance_ohm": float(port.real),
        "attachment_loss_w_at_1a_by_kind": loss_by_kind,
        "attachment_loss_fraction": sum(loss_by_kind.values()) / port.real,
        "maximum_current_balance_error_a": float(max(map(abs, balance.values()))),
        "network_quality": quality, "resistance_quality": resistance_quality,
        "attachments": attachments,
    }


def run(board: Path) -> dict:
    digest = hashlib.sha256(board.read_bytes()).hexdigest()
    if digest != PINNED_SHA256:
        raise ValueError("board hash differs from pinned Marble v1.4.4")
    imported = _design_from_kicad(str(board))
    copper = {field: [item for item in getattr(imported, field)
                      if str(item.get("net_name", item.get("net", ""))) == NET]
              for field in ("tracks", "vias", "pads", "zones")}
    design = DesignIR(layers=imported.layers, stackup=imported.stackup,
                      nets=[item for item in imported.nets if item.get("name") == NET],
                      **copper)
    return {"contract": "spike/peec-conforming-basis-diagnostic/v1",
            "board_sha256": digest, "status": "diagnostic_unqualified_mesh",
            "inductance_recomputed": False,
            "manufactured_face_oracle": triangular_face_oracle(),
            "levels": [audit(design, size) for size in (1.0, 0.75, 0.5)]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.board)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "levels": [{
        key: level[key] for key in ("mesh_size_mm", "physical_basis_count",
        "outside_basis_count", "sum_outside_area_mm2", "diagnostic_port_resistance_ohm",
        "attachment_loss_fraction", "maximum_current_balance_error_a")
    } for level in report["levels"]]}, allow_nan=False))
