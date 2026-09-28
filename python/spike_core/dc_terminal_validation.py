# SPDX-License-Identifier: Apache-2.0
"""Exact DC terminal mapping and solved source-to-load evidence."""

from __future__ import annotations

from collections import defaultdict
from math import fsum, isfinite
from typing import Any, Dict, List

import numpy as np

from .contracts import AnalysisSpec
from .dc_result_utils import terminal_net
from .hybrid_mesh import HybridMesh, nearest_mesh_node


def terminal_anchor_id(item: Dict[str, Any]) -> str:
    anchor = item.get("geometry_anchor")
    return str(anchor.get("id", "")) if isinstance(anchor, dict) else str(item.get("geometry_anchor_id", ""))


def terminal_copper_weights(mesh: HybridMesh, spec: AnalysisSpec, item: Dict[str, Any], exact: bool) -> Dict[int, float]:
    """Map a pad contact to its physical area, excluding topology attachments.

    For uniform normal current density, I_i = I A_i/A. A distributed contact
    with lumped resistance R has conductance G_i = A_i/(R A) in siemens.
    Subdividing a cell therefore preserves current and contact conductance.
    These weights also define the power-conjugate terminal voltage sum(w_i V_i).
    Pad cell areas are in mm^2; their normalized ratios are dimensionless.
    """
    net = terminal_net(spec, item)
    anchor = item.get("geometry_anchor")
    anchor_id = terminal_anchor_id(item)
    if exact and not anchor_id:
        return {}
    if anchor_id:
        layer = str(item.get("layer", ""))
        anchor_type = str(anchor.get("type", "")) if isinstance(anchor, dict) else ""
        allowed_kinds = {
            "pad": {"pad", "pad_attachment", "pad_zone_attachment", "pad_barrel"},
            "track": {"track"},
            "via": {"via"},
            "zone": {"zone", "zone_attachment"},
        }.get(anchor_type)
        if exact and anchor_type and allowed_kinds is None:
            return {}
        matching = [
            branch for branch in mesh.branches
            if branch.source_id == anchor_id
            and (not net or branch.net == net)
            and (not layer or branch.layer == layer)
            and (allowed_kinds is None or branch.kind in allowed_kinds)
        ]
        if not matching:
            return {}
    primary = nearest_mesh_node(mesh, item, net)
    if primary is None:
        return {}
    pad_kinds = {"pad", "pad_attachment", "pad_zone_attachment", "pad_barrel"}
    source_ids = {
        branch.source_id
        for branch in mesh.branches
        if (branch.node_p == primary or branch.node_n == primary)
        and (branch.source_id == anchor_id if anchor_id else branch.kind in pad_kinds)
    }
    if not source_ids:
        return {primary: 1.0}
    primary_layer = mesh.nodes[primary].layer
    layer_scope = str(item.get("layer_scope", "single" if item.get("layer") else "connected_conductor"))
    pad_cells = [
        cell for cell in mesh.cells
        if exact and anchor_type == "pad"
        and cell.get("source_kind") == "pad" and cell.get("source_id") in source_ids
        and cell.get("net") == net
        and (layer_scope != "single" or cell.get("layer") == primary_layer)
    ]
    if exact and anchor_id and anchor_type == "pad" and not pad_cells:
        return {}
    if pad_cells:
        areas: Dict[int, float] = {}
        for cell in pad_cells:
            node_id = cell.get("node_id")
            # Missing ownership cannot be repaired by including attachment ends:
            # those can be zone nodes outside the physical pad surface.
            if not isinstance(node_id, int) or not 0 <= node_id < len(mesh.nodes):
                return {}
            node = mesh.nodes[node_id]
            if node.net != cell.get("net") or node.layer != cell.get("layer"):
                return {}
            try:
                vertices = cell["vertices_mm"]
                origin = vertices[0]
                xy = [(float(point[0]) - float(origin[0]), float(point[1]) - float(origin[1])) for point in vertices]
                if len(xy) < 3 or not all(isfinite(value) for point in xy for value in point):
                    return {}
                area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(xy, xy[1:] + xy[:1]))) / 2
            except (KeyError, TypeError, ValueError, IndexError, OverflowError):
                return {}
            if not isfinite(area) or area <= 0:
                return {}
            areas[node_id] = areas.get(node_id, 0.0) + area
        total_area = sum(areas.values())
        return {node: area / total_area for node, area in sorted(areas.items())} if isfinite(total_area) and total_area > 0 else {}
    nodes = {
        node_id
        for branch in mesh.branches
        if branch.source_id in source_ids
        for node_id in (branch.node_p, branch.node_n)
        if mesh.nodes[node_id].net == net
        and (layer_scope != "single" or mesh.nodes[node_id].layer == primary_layer)
    }
    nodes = sorted(nodes) or [primary]
    return {node: 1.0 / len(nodes) for node in nodes}


def terminal_copper_nodes(mesh: HybridMesh, spec: AnalysisSpec, item: Dict[str, Any], exact: bool) -> List[int]:
    return list(terminal_copper_weights(mesh, spec, item, exact))


def terminal_boundary_voltage(record: Dict[str, Any], voltage: np.ndarray) -> float:
    nodes = record.get("boundary_nodes", [record["node"]])
    weights = record.get("boundary_weights", [1.0 / len(nodes)] * len(nodes))
    return float(sum(float(voltage[node]) * weight for node, weight in zip(nodes, weights)))


def build_source_to_load_evidence(
    source_records: List[Dict[str, Any]],
    load_records: List[Dict[str, Any]],
    voltage: np.ndarray,
    rhs: np.ndarray,
    scaled_residual: float,
    explicit_return: bool,
    active_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return signed terminal voltages, path drops, and KCL diagnostics."""
    def boundary_voltage(record: Dict[str, Any]) -> float:
        return terminal_boundary_voltage(record, voltage)

    supply_records = [item for item in source_records if item["role"] != "source_return"]
    return_records = [item for item in source_records if item["role"] == "source_return"]
    # A sparse G @ V product subtracts large absolute-voltage terms to recover
    # small drops. Sum the already-solved branch currents at clamped nodes so
    # KCL reflects the physical graph and does not lose digits as it refines.
    source_nodes = {int(node) for item in source_records for node in item["boundary_nodes"]}
    incident_currents: Dict[int, List[float]] = defaultdict(list)
    for edge in active_edges:
        current = float(edge["current_a"])
        if edge["a"] in source_nodes:
            incident_currents[edge["a"]].append(current)
        if edge["b"] in source_nodes:
            incident_currents[edge["b"]].append(-current)
    boundary_source_currents = {
        node: fsum(incident_currents[node]) - float(rhs[node]) for node in source_nodes
    }
    terminal_voltages = [
        {
            "id": item["id"],
            "kind": kind,
            "role": item["role"],
            "domain_id": item["domain_id"],
            "net": item["net"],
            "geometry_anchor_id": item["geometry_anchor_id"],
            "voltage_v": boundary_voltage(item),
            **(
                {"pair_id": item["pair_id"], "current_a": item["current_a"]}
                if kind == "load"
                else {"current_a": fsum(boundary_source_currents[node] for node in item["boundary_nodes"])}
            ),
        }
        for kind, records in (("source", source_records), ("load", load_records))
        for item in records
    ]
    paths: List[Dict[str, Any]] = []
    errors: List[str] = []
    for load in (item for item in load_records if item["role"] != "load_return"):
        source_matches = [
            item for item in supply_records
            if item["net"] == load["net"] and item["domain_id"] == load["domain_id"]
        ]
        if len(source_matches) != 1:
            errors.append(f"Load {load['id']} has {len(source_matches)} matching source terminals on its net and domain.")
            continue
        source = source_matches[0]
        record = {
            "load_id": load["id"],
            "source_id": source["id"],
            "pair_id": load["pair_id"],
            "domain_id": load["domain_id"],
            "supply_net": load["net"],
            "source_voltage_v": boundary_voltage(source),
            "load_voltage_v": boundary_voltage(load),
            "supply_drop_v": boundary_voltage(source) - boundary_voltage(load),
            "load_current_a": load["current_a"],
        }
        if explicit_return:
            return_loads = [
                item for item in load_records
                if item["role"] == "load_return"
                and item["pair_id"] == load["pair_id"]
                and item["domain_id"] == load["domain_id"]
            ]
            if len(return_loads) != 1:
                errors.append(f"Load {load['id']} has {len(return_loads)} matching return load terminals.")
                continue
            return_load = return_loads[0]
            return_sources = [
                item for item in return_records
                if item["net"] == return_load["net"] and item["domain_id"] == load["domain_id"]
            ]
            if len(return_sources) != 1:
                errors.append(f"Load {load['id']} has {len(return_sources)} matching return source terminals.")
                continue
            return_source = return_sources[0]
            source_differential = boundary_voltage(source) - boundary_voltage(return_source)
            load_differential = boundary_voltage(load) - boundary_voltage(return_load)
            record.update(
                return_net=return_load["net"],
                return_source_id=return_source["id"],
                return_load_id=return_load["id"],
                return_source_voltage_v=boundary_voltage(return_source),
                return_load_voltage_v=boundary_voltage(return_load),
                source_differential_v=source_differential,
                load_differential_v=load_differential,
                loop_drop_v=source_differential - load_differential,
            )
        paths.append(record)
    all_anchored = all(item["geometry_anchor_id"] for item in terminal_voltages)
    source_current_balance_a = float(
        fsum(item["current_a"] for item in terminal_voltages if item["kind"] == "source")
        - fsum(item["current_a"] for item in load_records)
    )
    current_scale_a = max(1.0, sum(abs(item["current_a"]) for item in load_records))
    if scaled_residual > 1e-8 or abs(source_current_balance_a) > 1e-8 * current_scale_a:
        errors.append("The terminal current balance or linear residual exceeds tolerance.")
    status = (
        "validated" if all_anchored and not errors
        and len(paths) == len([item for item in load_records if item["role"] != "load_return"])
        else "approximate"
    )
    return {
        "status": status,
        "terminal_voltages": terminal_voltages,
        "paths": paths,
        "issues": errors,
        "source_current_balance_a": source_current_balance_a,
        "voltage_reference": "absolute DC potential at each solved boundary node; supply and loop drops preserve sign",
    }
