"""DC resistive-network solver for routed and planar PCB copper.

Tracks, vias, pads, and polygonal copper zones are converted into one sparse
conductance network. Package and contact resistance are supported when supplied
on source/load terminals; they are never silently inferred.
"""

from __future__ import annotations

from dataclasses import asdict
from math import cos, hypot, pi, radians, sin, sqrt
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve
import warnings

from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from .layers import copper_stack_profile, ordered_copper_layer_names


COPPER_CONDUCTIVITY_S_M = 5.8e7
DEFAULT_COPPER_THICKNESS_MM = 0.035
NODE_TOLERANCE_MM = 0.05


def _point(value: Any) -> Tuple[float, float]:
    if isinstance(value, dict):
        return float(value.get("x", 0)), float(value.get("y", 0))
    return float(value[0]), float(value[1])


def _node_key(point: Tuple[float, float], layer: str) -> Tuple[int, int, str]:
    return (round(point[0] / NODE_TOLERANCE_MM), round(point[1] / NODE_TOLERANCE_MM), layer)


def _net(item: Dict[str, Any]) -> str:
    return str(item.get("net_name", item.get("net", "")))


def _point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    inside = False
    x, y = point
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / ((y2 - y1) or np.finfo(float).eps) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _pad_size(pad: Dict[str, Any]) -> Tuple[float, float]:
    size = pad.get("size")
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        return max(float(size[0]), NODE_TOLERANCE_MM), max(float(size[1]), NODE_TOLERANCE_MM)
    return (
        max(float(pad.get("width", 1.0)), NODE_TOLERANCE_MM),
        max(float(pad.get("height", 1.0)), NODE_TOLERANCE_MM),
    )


def _point_in_pad(point: Tuple[float, float], pad: Dict[str, Any]) -> bool:
    center = _point(pad.get("at", (0, 0)))
    width, height = _pad_size(pad)
    angle = -radians(float(pad.get("rotation", 0)))
    dx, dy = point[0] - center[0], point[1] - center[1]
    x = dx * cos(angle) - dy * sin(angle)
    y = dx * sin(angle) + dy * cos(angle)
    shape = str(pad.get("shape", "rect")).lower()
    if shape in {"circle", "oval"}:
        return (x / (width / 2)) ** 2 + (y / (height / 2)) ** 2 <= 1.0
    return abs(x) <= width / 2 and abs(y) <= height / 2


def _copper_layers(design: DesignIR) -> List[str]:
    return ordered_copper_layer_names(design)


def _pad_layers(pad: Dict[str, Any], copper_layers: List[str]) -> List[str]:
    raw = [str(value).strip('"') for value in pad.get("layers", [])]
    if any(value in {"*.Cu", "F&B.Cu"} for value in raw):
        return copper_layers or ["F.Cu", "B.Cu"]
    layers = [value for value in raw if value.endswith(".Cu")]
    if not layers:
        primary = str(pad.get("layer", "F.Cu"))
        layers = [primary] if primary.endswith(".Cu") else ["F.Cu"]
    return list(dict.fromkeys(layers))


def _terminal_resistance(item: Dict[str, Any], spec: AnalysisSpec) -> float:
    package_models = spec.options.get("package_models", {})
    model = package_models.get(str(item.get("component_ref", "")), {}) if isinstance(package_models, dict) else {}
    return max(0.0, sum(float(value or 0) for value in (
        item.get("series_resistance_ohm", 0),
        item.get("contact_resistance_ohm", model.get("contact_resistance_ohm", 0)),
        item.get("package_resistance_ohm", model.get("package_resistance_ohm", 0)),
    )))


def _copper_thicknesses(design: DesignIR) -> Dict[str, float]:
    return copper_stack_profile(design, DEFAULT_COPPER_THICKNESS_MM)[2]


def _copper_layer_z(design: DesignIR) -> Dict[str, float]:
    return copper_stack_profile(design, DEFAULT_COPPER_THICKNESS_MM)[1]


def _requested_nets(spec: AnalysisSpec) -> set[str]:
    return {str(value) for value in spec.net_names if str(value)}


def _nearest_node(nodes: Dict[Tuple[int, int, str], int], point: Tuple[float, float], layer: str | None, max_distance_mm: float = 2.0, layers: set[str] | None = None) -> int | None:
    best: Tuple[float, int] | None = None
    for (qx, qy, node_layer), index in nodes.items():
        if layer and node_layer != layer:
            continue
        if layers and node_layer not in layers:
            continue
        x, y = qx * NODE_TOLERANCE_MM, qy * NODE_TOLERANCE_MM
        distance = hypot(point[0] - x, point[1] - y)
        if distance <= max_distance_mm and (best is None or distance < best[0]):
            best = (distance, index)
    return best[1] if best else None


def _resolve_terminal(item: Dict[str, Any], nodes: Dict[Tuple[int, int, str], int]) -> int | None:
    if "position_mm" in item:
        point = _point(item["position_mm"])
    elif "at" in item:
        point = _point(item["at"])
    elif "x" in item and "y" in item:
        point = (float(item["x"]), float(item["y"]))
    else:
        return None
    layer = str(item.get("layer", "")) or None
    layer_scope = str(item.get("layer_scope", "single" if layer else "connected_conductor"))
    layers = {str(value) for value in item.get("layer_candidates", []) if str(value)}
    return _nearest_node(
        nodes,
        point,
        layer if layer_scope == "single" else None,
        float(item.get("snap_distance_mm", 2.0)),
        layers or None,
    )


def _solve_dc_legacy(design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
    issues: List[ValidationIssue] = []
    if spec.mode != "dc":
        return AnalysisResult(analysis_id=spec.analysis_id, mode=spec.mode, status="failed", model_status="unsupported", issues=[ValidationIssue(code="SPIKE-BE-PI-E-0002", severity="error", message="The routed-copper solver supports DC mode only.", path="analysis.mode", suggestion="Select the DC PI formulation or choose a solver that supports the requested mode.")])
    if not spec.sources or not spec.loads:
        return AnalysisResult(analysis_id=spec.analysis_id, mode="dc", status="failed", model_status="approximate", issues=[ValidationIssue(code="SPIKE-BE-PI-E-0003", severity="error", message="DC analysis requires at least one explicit voltage source and one current load.", path="analysis.terminals", suggestion="Place source and load terminals on exact routed copper before running.")])

    requested = _requested_nets(spec)
    thicknesses = _copper_thicknesses(design)
    copper_layers = _copper_layers(design)
    layer_z = _copper_layer_z(design)
    nodes: Dict[Tuple[int, int, str], int] = {}
    node_positions: List[Tuple[float, float, str]] = []
    node_nets: List[set[str]] = []
    edges: List[Dict[str, Any]] = []
    zone_mesh: List[Dict[str, Any]] = []
    geometry_counts = {"track": 0, "via": 0, "pad": 0, "zone": 0, "contact": 0}

    def node(point: Tuple[float, float], layer: str, net: str = "") -> int:
        key = _node_key(point, layer)
        if key not in nodes:
            nodes[key] = len(node_positions)
            node_positions.append((point[0], point[1], layer))
            node_nets.append(set())
        index = nodes[key]
        if net:
            node_nets[index].add(net)
        return index

    def floating_node(point: Tuple[float, float], layer: str, net: str) -> int:
        index = len(node_positions)
        node_positions.append((point[0], point[1], layer))
        node_nets.append({net} if net else set())
        return index

    def add_edge(edge_id: str, kind: str, a: int, b: int, resistance: float, width_mm: float, thickness_mm: float, layer: str, net: str, start: Tuple[float, float], end: Tuple[float, float], **extra: Any) -> None:
        if a == b:
            return
        edges.append({
            "id": edge_id,
            "kind": kind,
            "a": a,
            "b": b,
            "start_mm": list(start),
            "end_mm": list(end),
            "x_mm": (start[0] + end[0]) / 2,
            "y_mm": (start[1] + end[1]) / 2,
            "resistance_ohm": max(float(resistance), 1e-12),
            "length_mm": hypot(end[0] - start[0], end[1] - start[1]),
            "width_mm": max(float(width_mm), NODE_TOLERANCE_MM),
            "thickness_mm": max(float(thickness_mm), 1e-6),
            "layer": layer,
            "net": net,
            **extra,
        })

    for index, track in enumerate(design.tracks):
        net = _net(track)
        if requested and net not in requested:
            continue
        layer = str(track.get("layer", "F.Cu"))
        start, end = _point(track["start"]), _point(track["end"])
        length_mm = hypot(end[0] - start[0], end[1] - start[1])
        width_mm = float(track.get("width", 0.2))
        thickness_mm = thicknesses.get(layer, float(spec.mesh.get("copper_thickness_mm", DEFAULT_COPPER_THICKNESS_MM)))
        if length_mm <= 0 or width_mm <= 0 or thickness_mm <= 0:
            issues.append(ValidationIssue(code="SPIKE-BE-MESH-W-0004", severity="warning", message=f"Track {index + 1} has invalid dimensions and was skipped.", path=f"design.tracks[{index}]", suggestion="Repair the track length, width, or copper thickness and re-import the design."))
            continue
        resistance = (length_mm * 1e-3) / (COPPER_CONDUCTIVITY_S_M * (width_mm * 1e-3) * (thickness_mm * 1e-3))
        add_edge(f"track-{index + 1}", "track", node(start, layer, net), node(end, layer, net), resistance, width_mm, thickness_mm, layer, net, start, end)
        geometry_counts["track"] += 1

    for index, via in enumerate(design.vias):
        net = _net(via)
        if requested and net not in requested:
            continue
        point = _point(via["at"])
        via_layers = tuple(via.get("layers", ("F.Cu", "B.Cu")))
        if len(via_layers) < 2:
            continue
        a, b = node(point, str(via_layers[0]), net), node(point, str(via_layers[-1]), net)
        drill_mm = max(float(via.get("drill", 0.3)), 0.01)
        plating_mm = max(float(via.get("plating_thickness", via.get("plating_thickness_mm", spec.mesh.get("via_plating_thickness_mm", 0.025)))), 0.005)
        barrel_width_mm = pi * (drill_mm + plating_mm)
        span_mm = abs(layer_z.get(str(via_layers[0]), 0.0) - layer_z.get(str(via_layers[-1]), -float(spec.mesh.get("board_thickness_mm", 1.6))))
        area_m2 = barrel_width_mm * plating_mm * 1e-6
        resistance = (span_mm * 1e-3) / (COPPER_CONDUCTIVITY_S_M * area_m2)
        add_edge(f"via-{index + 1}", "via", a, b, resistance, barrel_width_mm, plating_mm, "through", net, point, point, vertical_length_mm=span_mm)
        geometry_counts["via"] += 1

    zone_cell_target = max(float(spec.mesh.get("zone_cell_mm", spec.mesh.get("target_size_mm", 1.0))), 0.15)
    max_zone_cells = max(int(spec.mesh.get("max_zone_cells", 3000)), 16)
    for zone_index, zone in enumerate(design.zones):
        net = _net(zone)
        if requested and net not in requested:
            continue
        layer = str(zone.get("layer", "F.Cu"))
        polygon = [_point(value) for value in zone.get("points", [])]
        if len(polygon) < 3 or not net:
            continue
        min_x, max_x = min(point[0] for point in polygon), max(point[0] for point in polygon)
        min_y, max_y = min(point[1] for point in polygon), max(point[1] for point in polygon)
        estimated = max(1.0, (max_x - min_x) * (max_y - min_y) / zone_cell_target ** 2)
        cell = zone_cell_target * sqrt(max(1.0, estimated / max_zone_cells))
        columns = max(1, int((max_x - min_x) / cell) + 1)
        rows = max(1, int((max_y - min_y) / cell) + 1)
        grid: Dict[Tuple[int, int], int] = {}
        nodes_before_zone = len(node_positions)
        thickness_mm = thicknesses.get(layer, float(spec.mesh.get("copper_thickness_mm", DEFAULT_COPPER_THICKNESS_MM)))
        for row in range(rows):
            for column in range(columns):
                point = (min_x + (column + 0.5) * cell, min_y + (row + 0.5) * cell)
                if not _point_in_polygon(point, polygon):
                    continue
                grid[(column, row)] = node(point, layer, net)
                half = cell / 2
                zone_mesh.append({
                    "id": f"zone-{zone_index + 1}-cell-{column}-{row}",
                    "layer": layer,
                    "net": net,
                    "vertices_mm": [
                        [point[0] - half, point[1] - half, 0],
                        [point[0] + half, point[1] - half, 0],
                        [point[0] + half, point[1] + half, 0],
                        [point[0] - half, point[1] + half, 0],
                    ],
                })
        sheet_edge_resistance = (cell * 1e-3) / (COPPER_CONDUCTIVITY_S_M * (cell * 1e-3) * (thickness_mm * 1e-3))
        for (column, row), current in grid.items():
            current_point = node_positions[current][:2]
            for neighbor_key in ((column + 1, row), (column, row + 1)):
                neighbor = grid.get(neighbor_key)
                if neighbor is not None:
                    add_edge(f"zone-{zone_index + 1}-{column}-{row}-{neighbor_key[0]}-{neighbor_key[1]}", "zone", current, neighbor, sheet_edge_resistance, cell, thickness_mm, layer, net, current_point, node_positions[neighbor][:2])
        zone_nodes = list(grid.values())
        if zone_nodes:
            for existing in range(nodes_before_zone):
                point = node_positions[existing][:2]
                if node_positions[existing][2] != layer or net not in node_nets[existing] or not _point_in_polygon(point, polygon):
                    continue
                nearest = min(zone_nodes, key=lambda candidate: hypot(point[0] - node_positions[candidate][0], point[1] - node_positions[candidate][1]))
                distance = max(hypot(point[0] - node_positions[nearest][0], point[1] - node_positions[nearest][1]), NODE_TOLERANCE_MM)
                resistance = (distance * 1e-3) / (COPPER_CONDUCTIVITY_S_M * (cell * 1e-3) * (thickness_mm * 1e-3))
                add_edge(f"zone-{zone_index + 1}-attachment-{existing}", "zone_attachment", existing, nearest, resistance, cell, thickness_mm, layer, net, point, node_positions[nearest][:2])
            geometry_counts["zone"] += 1
        if cell > zone_cell_target * 1.01:
            issues.append(ValidationIssue(code="SPIKE-BE-MESH-P-0001", severity="warning", message=f"Zone {zone_index + 1} used a {cell:.3f} mm cell to remain below the configured cell limit.", path=f"design.zones[{zone_index}]", suggestion="Reduce the selected geometry or increase max_zone_cells for convergence studies.", status="approximate"))

    for pad_index, pad in enumerate(design.pads):
        net = _net(pad)
        if requested and net not in requested:
            continue
        if not net:
            continue
        center = _point(pad.get("at", (0, 0)))
        width, height = _pad_size(pad)
        layers = _pad_layers(pad, copper_layers)
        pad_nodes: List[int] = []
        for layer in layers:
            thickness_mm = thicknesses.get(layer, float(spec.mesh.get("copper_thickness_mm", DEFAULT_COPPER_THICKNESS_MM)))
            center_node = node(center, layer, net)
            pad_nodes.append(center_node)
            candidates = [
                index for index, position in enumerate(node_positions)
                if index != center_node and position[2] == layer and net in node_nets[index] and _point_in_pad(position[:2], pad)
            ]
            for candidate in candidates:
                distance = max(hypot(center[0] - node_positions[candidate][0], center[1] - node_positions[candidate][1]), NODE_TOLERANCE_MM)
                effective_width = max(min(width, height), NODE_TOLERANCE_MM)
                resistance = (distance * 1e-3) / (COPPER_CONDUCTIVITY_S_M * (effective_width * 1e-3) * (thickness_mm * 1e-3))
                add_edge(f"pad-{pad_index + 1}-{layer}-{candidate}", "pad", center_node, candidate, resistance, effective_width, thickness_mm, layer, net, center, node_positions[candidate][:2])
        if len(pad_nodes) > 1:
            drill_mm = max(float(pad.get("drill", 0)), 0.1)
            plating_mm = max(float(pad.get("plating_thickness", spec.mesh.get("pad_plating_thickness_mm", spec.mesh.get("via_plating_thickness_mm", 0.025)))), 0.005)
            span_mm = abs(layer_z.get(layers[0], 0.0) - layer_z.get(layers[-1], -float(spec.mesh.get("board_thickness_mm", 1.6))))
            barrel_width_mm = pi * (drill_mm + plating_mm)
            area_m2 = barrel_width_mm * plating_mm * 1e-6
            barrel_resistance = (span_mm * 1e-3) / (COPPER_CONDUCTIVITY_S_M * area_m2)
            for layer_index in range(len(pad_nodes) - 1):
                add_edge(f"pad-{pad_index + 1}-barrel-{layer_index}", "pad_barrel", pad_nodes[layer_index], pad_nodes[layer_index + 1], barrel_resistance / (len(pad_nodes) - 1), barrel_width_mm, plating_mm, "through", net, center, center, vertical_length_mm=span_mm / (len(pad_nodes) - 1))
        geometry_counts["pad"] += 1

    if not edges:
        return AnalysisResult(analysis_id=spec.analysis_id, mode="dc", status="failed", model_status="approximate", issues=issues + [ValidationIssue(code="SPIKE-BE-PI-E-0004", severity="error", message="No connected tracks, vias, pads, or zones matched the selected DC nets.", path="analysis.net_names", suggestion="Review managed nets and the mesh preview, then select connected copper geometry.")])

    source_nodes: Dict[int, float] = {}
    for source in spec.sources:
        copper_index = _resolve_terminal(source, nodes)
        if copper_index is None:
            source_id = str(source.get("id", "unnamed"))
            issues.append(ValidationIssue(code="SPIKE-BE-PI-E-0001", severity="error", message=f"Source {source_id} could not be snapped to routed copper.", path=f"analysis.sources[{source_id}]", suggestion="Assign the source to an exact copper object on the analyzed net."))
        else:
            resistance = _terminal_resistance(source, spec)
            index = copper_index
            if resistance > 0:
                position = node_positions[copper_index]
                index = floating_node(position[:2], position[2], next(iter(node_nets[copper_index]), ""))
                add_edge(f"source-contact-{source.get('id', len(source_nodes) + 1)}", "contact", index, copper_index, resistance, 1, 1, position[2], next(iter(node_nets[copper_index]), ""), position[:2], position[:2], current_density_supported=False)
                geometry_counts["contact"] += 1
            source_nodes[index] = float(source.get("voltage_v", source.get("voltage", 0)))
    load_nodes: Dict[int, float] = {}
    for load in spec.loads:
        copper_index = _resolve_terminal(load, nodes)
        if copper_index is None:
            load_id = str(load.get("id", "unnamed"))
            issues.append(ValidationIssue(code="SPIKE-BE-PI-E-0001", severity="error", message=f"Load {load_id} could not be snapped to routed copper.", path=f"analysis.loads[{load_id}]", suggestion="Assign the load to an exact copper object on the analyzed net."))
        else:
            resistance = _terminal_resistance(load, spec)
            index = copper_index
            if resistance > 0:
                position = node_positions[copper_index]
                index = floating_node(position[:2], position[2], next(iter(node_nets[copper_index]), ""))
                add_edge(f"load-contact-{load.get('id', len(load_nodes) + 1)}", "contact", copper_index, index, resistance, 1, 1, position[2], next(iter(node_nets[copper_index]), ""), position[:2], position[:2], current_density_supported=False)
                geometry_counts["contact"] += 1
            load_nodes[index] = load_nodes.get(index, 0.0) + float(load.get("current_a", load.get("current", 0)))
    if any(issue.severity == "error" for issue in issues):
        return AnalysisResult(analysis_id=spec.analysis_id, mode="dc", status="failed", model_status="approximate", issues=issues)

    adjacency: Dict[int, set[int]] = {index: set() for index in range(len(node_positions))}
    for edge in edges:
        adjacency[edge["a"]].add(edge["b"])
        adjacency[edge["b"]].add(edge["a"])
    reachable = set(source_nodes)
    pending = list(source_nodes)
    while pending:
        current = pending.pop()
        for neighbor in adjacency[current]:
            if neighbor not in reachable:
                reachable.add(neighbor)
                pending.append(neighbor)
    unreachable_loads = [index for index in load_nodes if index not in reachable]
    if unreachable_loads:
        return AnalysisResult(analysis_id=spec.analysis_id, mode="dc", status="failed", model_status="approximate", issues=issues + [ValidationIssue(code="SPIKE-BE-PI-E-0005", severity="error", message="At least one load is not connected to any defined source through routed copper.", path="analysis.loads", suggestion="Choose terminals on one connected copper path or define the missing series-component bridge.")])
    disconnected_edges = len(edges) - sum(edge["a"] in reachable and edge["b"] in reachable for edge in edges)
    if disconnected_edges:
        issues.append(ValidationIssue(code="SPIKE-BE-PI-W-0001", severity="warning", message=f"{disconnected_edges} routed elements on the selected net are not connected to the defined source and were excluded.", path="analysis.net_names", suggestion="Inspect the excluded copper in the mesh preview and define missing connectivity where required."))
    active_edges = [edge for edge in edges if edge["a"] in reachable and edge["b"] in reachable]
    active_nodes = sorted(reachable)
    reindex = {old: new for new, old in enumerate(active_nodes)}
    for edge in active_edges:
        edge["a"] = reindex[edge["a"]]
        edge["b"] = reindex[edge["b"]]
    source_nodes = {reindex[index]: voltage for index, voltage in source_nodes.items()}
    load_nodes = {reindex[index]: current for index, current in load_nodes.items()}
    node_positions = [node_positions[index] for index in active_nodes]
    edges = active_edges
    size = len(node_positions)
    conductance = lil_matrix((size, size), dtype=float)
    rhs = np.zeros(size, dtype=float)
    for edge in edges:
        a, b, g = edge["a"], edge["b"], 1.0 / edge["resistance_ohm"]
        conductance[a, a] += g; conductance[b, b] += g; conductance[a, b] -= g; conductance[b, a] -= g
    for index, current in load_nodes.items():
        rhs[index] -= current
    known = sorted(source_nodes)
    unknown = [index for index in range(size) if index not in source_nodes]
    conductance = conductance.tocsr()
    voltages = np.zeros(size, dtype=float)
    for index, voltage in source_nodes.items():
        voltages[index] = voltage
    try:
        if unknown:
            reduced_rhs = rhs[unknown]
            if known:
                reduced_rhs = reduced_rhs - conductance[unknown][:, known] @ np.array([source_nodes[index] for index in known])
            with warnings.catch_warnings():
                warnings.simplefilter("error", MatrixRankWarning)
                voltages[unknown] = spsolve(conductance[unknown][:, unknown], reduced_rhs)
        if not np.all(np.isfinite(voltages)):
            raise ValueError("non-finite network solution")
    except (MatrixRankWarning, ValueError, RuntimeError):
        return AnalysisResult(analysis_id=spec.analysis_id, mode="dc", status="failed", model_status="approximate", issues=issues + [ValidationIssue(code="SPIKE-BE-SOLVER-E-0002", severity="error", message="The selected source/load network is disconnected or has no valid return path.", path="analysis.return_path", suggestion="Add an explicit return source/load terminal on connected routed copper.")])

    for edge in edges:
        edge["current_a"] = float((voltages[edge["a"]] - voltages[edge["b"]]) / edge["resistance_ohm"])
        area_mm2 = edge["width_mm"] * edge["thickness_mm"]
        edge["current_density_a_mm2"] = abs(edge["current_a"]) / area_mm2 if area_mm2 and edge.get("current_density_supported", True) else 0.0
        edge["voltage_drop_v"] = abs(voltages[edge["a"]] - voltages[edge["b"]])
    source_voltage = max(source_nodes.values())
    max_drop_v = max((source_voltage - value for value in voltages), default=0.0)
    density_edges = [edge for edge in edges if edge.get("current_density_supported", True)]
    max_edge = max(density_edges or edges, key=lambda edge: edge["current_density_a_mm2"])
    max_drop_limit = float(spec.limits.get("max_voltage_drop_v", spec.limits.get("max_voltage_drop_mv", 50) / 1000))
    max_density_limit = float(spec.limits.get("max_current_density_a_mm2", 100.0))
    if max_drop_v > max_drop_limit:
        issues.append(ValidationIssue(code="SPIKE-BE-PI-W-0002", severity="warning", message=f"Maximum voltage drop {max_drop_v * 1000:.2f} mV exceeds the configured limit.", path="analysis.limits.max_voltage_drop", suggestion="Inspect the highest-drop current path and its conductor and contact resistance.", status="violated"))
    if max_edge["current_density_a_mm2"] > max_density_limit:
        issues.append(ValidationIssue(code="SPIKE-BE-PI-W-0003", severity="warning", message=f"{max_edge['id']} reaches {max_edge['current_density_a_mm2']:.2f} A/mm2.", path=f"result.edges[{max_edge['id']}]", suggestion="Inspect and increase the affected conductor cross-section or reduce current.", status="violated"))
    issues.append(ValidationIssue(code="SPIKE-BE-PI-W-0004", severity="warning", message="Tracks, vias, pads, and copper zones are included. Zone current spreading uses the configured finite-volume mesh; run a mesh-convergence comparison for sign-off.", path="analysis.mesh", suggestion="Run the configured coarse-to-fine convergence study before engineering sign-off.", status="approximate"))
    if geometry_counts["contact"] == 0:
        issues.append(ValidationIssue(code="SPIKE-BE-PI-W-0005", severity="warning", message="No package or contact resistance models were assigned, so source and load terminals use ideal zero-ohm contacts.", path="analysis.terminals", suggestion="Assign terminal contact_resistance_ohm/package_resistance_ohm or a component package model.", status="approximate"))

    probe_results: List[Dict[str, Any]] = []
    solved_nodes = {
        _node_key((position[0], position[1]), position[2]): index
        for index, position in enumerate(node_positions)
    }
    for probe_index, probe in enumerate(spec.probes):
        result: Dict[str, Any] = {
            "id": probe.get("id", f"probe-{probe_index + 1}"),
            "name": probe.get("name", f"Probe {probe_index + 1}"),
            "net": probe.get("net", ""),
            "layer": probe.get("layer", ""),
        }
        raw_position = probe.get("position_mm") or probe.get("at")
        if raw_position is None:
            result.update(status="unmapped", message="Probe has no physical position.")
            probe_results.append(result)
            continue
        point = _point(raw_position)
        layer = str(probe.get("layer", "")) or None
        nearest = _nearest_node(solved_nodes, point, layer, float(probe.get("snap_distance_mm", 2.0)))
        if nearest is None:
            result.update(status="unmapped", position_mm=list(point), message="Probe is not within snap distance of solved copper.")
            probe_results.append(result)
            continue
        local_edges = [edge for edge in edges if edge["a"] == nearest or edge["b"] == nearest]
        position = node_positions[nearest]
        result.update(
            status="mapped",
            position_mm=[position[0], position[1]],
            layer=position[2],
            voltage_v=float(voltages[nearest]),
            voltage_drop_v=float(max(0.0, source_voltage - voltages[nearest])),
            peak_adjacent_current_density_a_mm2=float(max((edge["current_density_a_mm2"] for edge in local_edges), default=0.0)),
            peak_adjacent_current_a=float(max((abs(edge["current_a"]) for edge in local_edges), default=0.0)),
            adjacent_element_ids=[edge["id"] for edge in local_edges],
        )
        probe_results.append(result)

    return AnalysisResult(
        analysis_id=spec.analysis_id or "dc-local",
        mode="dc",
        status="completed",
        model_status="approximate",
        summary={"max_voltage_drop_v": float(max_drop_v), "max_current_density_a_mm2": float(max_edge["current_density_a_mm2"]), "max_current_edge": max_edge["id"], "source_voltage_v": source_voltage, "node_count": size, "edge_count": len(edges), "geometry_counts": geometry_counts},
        fields={
            "node_voltages": [{"x_mm": x, "y_mm": y, "layer": layer, "voltage_v": float(voltages[index])} for index, (x, y, layer) in enumerate(node_positions)],
            "edge_results": edges,
            "visualization": {
                "schema": "spike/result-visualization/v1",
                "scalar_fields": {
                    "voltage_v": [{"x_mm": x, "y_mm": y, "layer": layer, "value": float(voltages[index])} for index, (x, y, layer) in enumerate(node_positions)],
                    "voltage_drop_v": [{"x_mm": x, "y_mm": y, "layer": layer, "value": float(max(0.0, source_voltage - voltages[index]))} for index, (x, y, layer) in enumerate(node_positions)],
                    "current_density_a_mm2": [{"x_mm": edge["x_mm"], "y_mm": edge["y_mm"], "layer": edge["layer"], "net": edge["net"], "element_id": edge["id"], "value": edge["current_density_a_mm2"]} for edge in edges if edge.get("current_density_supported", True)],
                },
                "vector_fields": {},
                "mesh": zone_mesh,
            },
        },
        probes=probe_results,
        issues=issues,
        provenance={"solver": "spike-copper-dc/v2", "conductivity_s_m": COPPER_CONDUCTIVITY_S_M, "default_copper_thickness_mm": DEFAULT_COPPER_THICKNESS_MM, "node_tolerance_mm": NODE_TOLERANCE_MM, "zone_cell_target_mm": zone_cell_target, "geometry_counts": geometry_counts, "assumptions": ["uniform copper conductivity", "finite-volume zone current spreading", "pad spreading resistance from extracted dimensions", "package/contact resistance from assigned models only", "DC resistance only"]},
    )


def solve_dc(design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
    """Run production DCIR on the same hybrid topology used by preflight."""

    from .hybrid_dc_solver import solve_hybrid_dc

    return solve_hybrid_dc(design, spec)
