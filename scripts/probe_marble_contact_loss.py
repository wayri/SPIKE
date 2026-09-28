# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""DC-only sensitivity probe for Marble pad/zone attachment losses.

This is a diagnostic perturbation of graph-link resistances, not a proposed
contact model or a qualified PEEC solve. The physical copper overlap matrix
is left unchanged. No native inductance or capacitance is evaluated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from python.spike_core.contracts import AnalysisSpec  # noqa: E402
from python.spike_core.hybrid_mesh import (  # noqa: E402
    TOPOLOGY_ONLY_BRANCH_KINDS, build_hybrid_mesh, nearest_mesh_node,
)
from python.spike_core.peec_network import solve_port  # noqa: E402
from python.spike_core.peec_plugin import _connected_component  # noqa: E402
from python.spike_core.peec_volume_resistance import assemble_overlap_resistance  # noqa: E402
from python.spike_core.service import _design_from_kicad  # noqa: E402


NET = "Net-(C383-Pad1)"
CONTACT_KINDS = ("zone_attachment", "pad_attachment", "pad_zone_attachment")


def probe(board: Path, mesh_size_mm: float, contact_kind: str,
          contact_scale: float) -> dict:
    if mesh_size_mm <= 0 or not 0 < contact_scale <= 1:
        raise ValueError("mesh size must be positive and contact scale in (0, 1]")
    if contact_kind not in (*CONTACT_KINDS, "all", "none"):
        raise ValueError("contact_kind must identify one graph attachment type, all, or none")
    design = _design_from_kicad(str(board))
    for field in ("tracks", "vias", "pads", "zones"):
        setattr(design, field, [item for item in getattr(design, field)
                               if str(item.get("net_name", item.get("net", ""))) == NET])
    spec = AnalysisSpec(mode="ac", net_names=[NET], mesh={
        "target_size_mm": mesh_size_mm, "zone_cell_mm": mesh_size_mm,
        "max_zone_cells": 1000, "max_conductors": 2000,
        "memory_budget_mb": 512,
    })
    mesh = build_hybrid_mesh(design, spec)
    if mesh.truncated:
        raise ValueError("partial copper mesh rejected")
    pads = {str(item.get("component_pad")): item for item in design.pads}

    def terminal(name: str) -> int:
        pad = pads[name]
        node = nearest_mesh_node(mesh, {
            "id": name, "position_mm": pad["at"],
            "layer": pad.get("layer", "F.Cu"), "net": NET,
            "geometry_anchor": {"id": pad["id"], "type": "pad"},
        }, NET)
        if node is None:
            raise ValueError(f"{name} is not attached to copper")
        return node

    source, load = terminal("U37.18"), terminal("R195.1")
    nodes, connected = _connected_component(mesh, NET, source)
    if load not in nodes:
        raise ValueError("routed pad pair is disconnected")
    physical = [index for index, branch in enumerate(mesh.branches)
                if branch.kind not in TOPOLOGY_ONLY_BRANCH_KINDS]
    resistance = np.diag([branch.resistance_ohm for branch in mesh.branches])
    physical_resistance, quality = assemble_overlap_resistance(
        design, [mesh.branches[index] for index in physical])
    resistance[np.ix_(physical, physical)] = physical_resistance
    if contact_kind != "none":
        for index in connected:
            if (mesh.branches[index].kind == contact_kind
                    or contact_kind == "all" and mesh.branches[index].kind in CONTACT_KINDS):
                resistance[index, index] *= contact_scale
    local_resistance = resistance[np.ix_(connected, connected)]
    impedance, currents, solution_quality = solve_port(
        mesh, nodes, connected, source, load, local_resistance, diagnostics=True)
    losses = {kind: float(sum(
        abs(currents[local_index]) ** 2 * resistance[index, index]
        for local_index, index in enumerate(connected)
        if mesh.branches[index].kind == kind)) for kind in CONTACT_KINDS}
    return {
        "contract": "spike/marble-contact-loss-diagnostic/v1",
        "qualification": "diagnostic_only",
        "mesh_size_mm": mesh_size_mm,
        "contact_kind_scaled": contact_kind,
        "contact_resistance_scale": contact_scale,
        "physical_branch_count": len(physical),
        "connected_branch_count": len(connected),
        "dc_port_resistance_ohm": float(impedance.real),
        "contact_loss_ohm_per_ampere_squared": losses,
        "relative_mna_residual": float(solution_quality["relative_residual"]),
        "minimum_physical_resistance_eigenvalue_ohm":
            quality["minimum_resistance_eigenvalue_ohm"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--mesh-size-mm", type=float, required=True)
    parser.add_argument("--contact-kind", choices=("none", "all", *CONTACT_KINDS), default="none")
    parser.add_argument("--contact-scale", type=float, default=1.0)
    args = parser.parse_args()
    print(json.dumps(probe(args.board, args.mesh_size_mm,
                           args.contact_kind, args.contact_scale), allow_nan=False))
