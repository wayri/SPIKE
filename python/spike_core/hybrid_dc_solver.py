"""Sparse DCIR solution on the shared hybrid conductor mesh."""

from __future__ import annotations

from math import hypot
from time import perf_counter
from typing import Any, Dict, List

import numpy as np
from scipy.sparse import coo_matrix

from .acceleration import (
    AccelerationUnavailableError,
    assemble_graph_laplacian,
    solve_sparse_system,
)
from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from .dc_result_utils import (
    sample_indexes,
    stratified_sample_records,
    terminal_net,
    terminal_resistance,
    weighted_percentile_density,
)
from .dc_terminal_validation import (
    build_source_to_load_evidence,
    terminal_anchor_id,
    terminal_copper_weights,
    terminal_boundary_voltage,
)
from .hybrid_mesh import HybridMesh, build_hybrid_mesh, nearest_mesh_node
from .pi_path_dc import stamp_pi_path_interfaces
from .result_face_projection import (
    TOPOLOGY_VISUALIZATION_KINDS,
    bind_result_faces,
    physical_result_edges,
    project_result_faces,
)


def solve_hybrid_dc(design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
    overall_started = perf_counter()
    if spec.mode != "dc":
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode=spec.mode,
            status="failed",
            model_status="unsupported",
            issues=[ValidationIssue("SPIKE-BE-PI-E-0002", "error", "The hybrid DC solver supports DC mode only.", path="analysis.mode", suggestion="Select the DC PI formulation or choose a solver that supports the requested mode.")],
        )
    if not spec.sources or not spec.loads:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode="dc",
            status="failed",
            model_status="approximate",
            issues=[ValidationIssue("SPIKE-BE-PI-E-0003", "error", "DC analysis requires explicit voltage sources and current loads.", path="analysis.terminals", suggestion="Assign at least one source and one load to exact connected copper objects.")],
        )

    mesh_started = perf_counter()
    mesh = build_hybrid_mesh(design, spec)
    mesh_time_s = perf_counter() - mesh_started
    issues = list(mesh.issues)
    if mesh.truncated or not mesh.branches:
        if not mesh.branches:
            issues.append(ValidationIssue("SPIKE-BE-PI-E-0004", "error", "No hybrid copper geometry matched the selected nets.", path="analysis.net_names", suggestion="Review managed nets, import diagnostics, and the mesh preview before retrying."))
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode="dc",
            status="failed",
            model_status="failed" if mesh.truncated else "unsupported",
            issues=issues,
        )

    node_positions: List[tuple[float, float, str]] = [
        (node.x_mm, node.y_mm, node.layer) for node in mesh.nodes
    ]
    node_nets: List[str] = [node.net for node in mesh.nodes]
    edges: List[Dict[str, Any]] = []
    for branch in mesh.branches:
        edges.append({
            "id": branch.id,
            "kind": branch.kind,
            "a": branch.node_p,
            "b": branch.node_n,
            "start_mm": list(branch.start_mm[:2]),
            "end_mm": list(branch.end_mm[:2]),
            "start_z_mm": branch.start_mm[2],
            "end_z_mm": branch.end_mm[2],
            "x_mm": (branch.start_mm[0] + branch.end_mm[0]) / 2,
            "y_mm": (branch.start_mm[1] + branch.end_mm[1]) / 2,
            "z_mm": (branch.start_mm[2] + branch.end_mm[2]) / 2,
            "resistance_ohm": max(branch.resistance_ohm, 1e-12),
            "length_mm": branch.length_mm,
            "width_mm": branch.width_mm,
            "thickness_mm": branch.thickness_mm,
            "layer": branch.layer,
            "net": branch.net,
            "source_id": branch.source_id,
            "current_density_supported": True,
        })

    source_nodes: Dict[int, float] = {}
    source_records: List[Dict[str, Any]] = []
    load_nodes: Dict[int, float] = {}
    load_records: List[Dict[str, Any]] = []
    contact_count = 0
    exact_terminals = bool(spec.options.get("require_exact_terminal_geometry", False))

    issues.extend(stamp_pi_path_interfaces(mesh, design, spec, node_positions, edges))

    def attach_contact(copper_weights: Dict[int, float], resistance: float, item_id: str, kind: str) -> Dict[int, float]:
        nonlocal contact_count
        if resistance <= 0:
            return copper_weights
        copper_node = next(iter(copper_weights))
        x, y, layer = node_positions[copper_node]
        floating = len(node_positions)
        node_positions.append((x, y, layer))
        node_nets.append(node_nets[copper_node])
        # Parallel conductances sum to 1/R under cell subdivision; surface
        # fractions, not the count of mesh and attachment nodes, set the measure.
        for index, (copper_node, weight) in enumerate(copper_weights.items()):
            branch_resistance = resistance / weight
            cx, cy, copper_layer = node_positions[copper_node]
            a, b = (floating, copper_node) if kind == "source" else (copper_node, floating)
            edges.append({
                "id": f"{kind}-contact-{item_id}-{index + 1}",
                "kind": "contact",
                "a": a,
                "b": b,
                "start_mm": [x, y],
                "end_mm": [cx, cy],
                "start_z_mm": 0.0,
                "end_z_mm": 0.0,
                "x_mm": (x + cx) / 2,
                "y_mm": (y + cy) / 2,
                "z_mm": 0.0,
                "resistance_ohm": branch_resistance,
                "length_mm": 0.0,
                "width_mm": 1.0,
                "thickness_mm": 1.0,
                "layer": copper_layer,
                "net": node_nets[copper_node],
                "source_id": item_id,
                "current_density_supported": False,
            })
            contact_count += 1
        return {floating: 1.0}

    for index, source in enumerate(spec.sources):
        coppers = terminal_copper_weights(mesh, spec, source, exact_terminals)
        if not coppers:
            source_id = str(source.get("id", index + 1))
            issues.append(ValidationIssue("SPIKE-BE-PI-E-0001", "error", f"Source {source_id} could not snap to selected copper.", path=f"analysis.sources[{source_id}]", suggestion="Assign the source to an exact copper object on the analyzed net."))
            continue
        terminals = attach_contact(coppers, terminal_resistance(source, spec), str(source.get("id", index + 1)), "source")
        source_voltage = float(source.get("voltage_v", source.get("voltage", 0)))
        for terminal in terminals:
            if terminal in source_nodes and source_nodes[terminal] != source_voltage:
                issues.append(ValidationIssue("SPIKE-BE-PI-E-0006", "error", "Two source boundaries assign different voltages to the same copper node.", path="analysis.sources", suggestion="Remove the duplicate source or place it on a distinct conductor domain."))
            source_nodes[terminal] = source_voltage
        source_records.append({
            "id": str(source.get("id", index + 1)),
            "geometry_anchor_id": terminal_anchor_id(source),
            "node": next(iter(terminals)),
            "boundary_nodes": list(terminals),
            "boundary_weights": list(terminals.values()),
            "net": node_nets[next(iter(terminals))],
            "voltage_v": source_voltage,
            "role": str(source.get("terminal_role", "source_positive")),
            "domain_id": str(source.get("domain_id", "default")),
        })

    for index, load in enumerate(spec.loads):
        coppers = terminal_copper_weights(mesh, spec, load, exact_terminals)
        if not coppers:
            load_id = str(load.get("id", index + 1))
            issues.append(ValidationIssue("SPIKE-BE-PI-E-0001", "error", f"Load {load_id} could not snap to selected copper.", path=f"analysis.loads[{load_id}]", suggestion="Assign the load to an exact copper object on the analyzed net."))
            continue
        terminals = attach_contact(coppers, terminal_resistance(load, spec), str(load.get("id", index + 1)), "load")
        load_current = float(load.get("current_a", load.get("current", 0)))
        for terminal, weight in terminals.items():
            load_nodes[terminal] = load_nodes.get(terminal, 0.0) + load_current * weight
        load_records.append({
            "id": str(load.get("id", index + 1)),
            "geometry_anchor_id": terminal_anchor_id(load),
            "node": next(iter(terminals)),
            "boundary_nodes": list(terminals),
            "boundary_weights": list(terminals.values()),
            "net": node_nets[next(iter(terminals))],
            "current_a": load_current,
            "role": str(load.get("terminal_role", "load_positive")),
            "pair_id": str(load.get("pair_id", load.get("id", index + 1))),
            "domain_id": str(load.get("domain_id", "default")),
        })

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
    if any(node not in reachable for node in load_nodes):
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode="dc",
            status="failed",
            model_status="approximate",
            issues=issues + [ValidationIssue("SPIKE-BE-PI-E-0005", "error", "At least one load is disconnected from all defined sources in the shared hybrid mesh.", path="analysis.loads", suggestion="Correct terminal anchors or define the missing series-component and cross-net bridge.")],
        )

    disconnected = len(edges) - sum(edge["a"] in reachable and edge["b"] in reachable for edge in edges)
    if disconnected:
        issues.append(ValidationIssue("SPIKE-BE-PI-W-0001", "warning", f"{disconnected} hybrid-mesh branches are outside the driven component and were excluded.", path="analysis.net_names", suggestion="Inspect the excluded copper and define missing connectivity where it belongs to the intended path."))
    active_nodes = sorted(reachable)
    reindex = {old: new for new, old in enumerate(active_nodes)}
    active_edges = [
        {**edge, "a": reindex[edge["a"]], "b": reindex[edge["b"]]}
        for edge in edges
        if edge["a"] in reachable and edge["b"] in reachable
    ]
    for edge in active_edges:
        if edge.get("kind") == "series_component":
            edge["input_node"] = edge["a"]
            edge["output_node"] = edge["b"]
    source_nodes = {reindex[node]: voltage for node, voltage in source_nodes.items()}
    load_nodes = {reindex[node]: current for node, current in load_nodes.items()}
    source_records = [{
        **item,
        "node": reindex[item["node"]],
        "boundary_nodes": [reindex[node] for node in item["boundary_nodes"]],
    } for item in source_records]
    load_records = [{
        **item,
        "node": reindex[item["node"]],
        "boundary_nodes": [reindex[node] for node in item["boundary_nodes"]],
    } for item in load_records]
    node_positions = [node_positions[node] for node in active_nodes]
    node_nets = [node_nets[node] for node in active_nodes]
    size = len(node_positions)

    assembly_started = perf_counter()
    rhs = np.zeros(size, dtype=float)
    try:
        rows, columns, values, assembly_backend = assemble_graph_laplacian(
            (edge["a"] for edge in active_edges),
            (edge["b"] for edge in active_edges),
            (1.0 / edge["resistance_ohm"] for edge in active_edges),
            requested=str(spec.options.get("assembly_backend", "auto")),
        )
    except (AccelerationUnavailableError, ValueError) as exc:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode="dc",
            status="failed",
            model_status="failed",
            issues=issues + [ValidationIssue(
                "SPIKE-BE-SOLVER-E-0001",
                "error",
                str(exc),
                suggestion="Select auto or numpy assembly, or install the approved optional Numba bundle.",
            )],
        )
    conductance = coo_matrix((values, (rows, columns)), shape=(size, size), dtype=float).tocsr()
    conductance.sum_duplicates()
    for node, current in load_nodes.items():
        rhs[node] -= current
    known = np.array(sorted(source_nodes), dtype=np.int64)
    known_mask = np.zeros(size, dtype=bool)
    known_mask[known] = True
    unknown = np.flatnonzero(~known_mask)
    voltage = np.zeros(size, dtype=float)
    for node, value in source_nodes.items():
        voltage[node] = value
    assembly_time_s = perf_counter() - assembly_started
    solve_started = perf_counter()
    scaled_residual = 0.0
    linear_backend: Dict[str, Any] = {}
    try:
        if unknown.size:
            reduced = conductance[unknown][:, unknown].tocsr()
            known_values = np.array([source_nodes[int(node)] for node in known])
            reduced_rhs = rhs[unknown] - conductance[unknown][:, known] @ known_values
            solution, linear_backend = solve_sparse_system(
                reduced,
                reduced_rhs,
                requested=str(spec.options.get("sparse_backend", "auto")),
            )
            voltage[unknown] = solution
            residual = reduced @ solution - reduced_rhs
            denominator = (
                np.linalg.norm(reduced_rhs, ord=np.inf)
                + np.linalg.norm(abs(reduced) @ np.abs(solution), ord=np.inf)
                + 1e-30
            )
            scaled_residual = float(np.linalg.norm(residual, ord=np.inf) / denominator)
        if not np.all(np.isfinite(voltage)):
            raise ValueError("non-finite network solution")
    except AccelerationUnavailableError as exc:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode="dc",
            status="failed",
            model_status="failed",
            issues=issues + [ValidationIssue(
                "SPIKE-BE-SOLVER-E-0001",
                "error",
                str(exc),
                suggestion="Select auto or scipy-superlu, or install an approved PETSc build with MUMPS.",
            )],
        )
    except (ValueError, RuntimeError):
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode="dc",
            status="failed",
            model_status="failed",
            issues=issues + [ValidationIssue("SPIKE-BE-SOLVER-E-0002", "error", "The hybrid DC conductance matrix is singular.", path="solver.linear_system", suggestion="Review disconnected copper, return paths, terminal placement, and extreme resistance ratios.")],
        )
    solve_time_s = perf_counter() - solve_started
    if scaled_residual > 1e-8:
        issues.append(ValidationIssue(
            "SPIKE-BE-SOLVER-W-0005",
            "warning",
            f"The scaled DC linear-system residual is {scaled_residual:.3g}.",
            suggestion="Review disconnected copper, extreme resistance ratios, and terminal placement; then refine locally.",
            status="approximate",
        ))

    for edge in active_edges:
        edge["current_a"] = float((voltage[edge["a"]] - voltage[edge["b"]]) / edge["resistance_ohm"])
        area_mm2 = edge["width_mm"] * edge["thickness_mm"]
        edge["current_density_a_mm2"] = (
            abs(edge["current_a"]) / area_mm2
            if area_mm2 and edge["current_density_supported"]
            else 0.0
        )
        edge["voltage_drop_v"] = abs(voltage[edge["a"]] - voltage[edge["b"]])
        edge["power_loss_w"] = edge["current_a"] ** 2 * edge["resistance_ohm"]

    source_voltage = max(source_nodes.values())
    return_mode = str(spec.return_path.get("mode", "implicit"))
    explicit_return = return_mode in {"explicit", "isolated_secondary"}
    supply_records = [item for item in source_records if item["role"] != "source_return"]
    return_records = [item for item in source_records if item["role"] == "source_return"]
    reference_by_net: Dict[str, float] = {}
    for item in source_records:
        net = item["net"]
        value = float(item["voltage_v"])
        if item["role"] == "source_return":
            reference_by_net[net] = value
        else:
            reference_by_net[net] = max(reference_by_net.get(net, value), value)

    def node_drop(node: int) -> float:
        reference = reference_by_net.get(node_nets[node], source_voltage)
        return abs(reference - float(voltage[node]))

    def boundary_voltage(record: Dict[str, Any]) -> float:
        return terminal_boundary_voltage(record, voltage)

    def boundary_drop(record: Dict[str, Any]) -> float:
        nodes = record.get("boundary_nodes", [record["node"]])
        weights = record.get("boundary_weights", [1.0 / len(nodes)] * len(nodes))
        return float(sum(node_drop(node) * weight for node, weight in zip(nodes, weights)))

    supply_nets = {item["net"] for item in supply_records}
    return_nets = {item["net"] for item in return_records}
    max_supply_drop = max((node_drop(index) for index, net in enumerate(node_nets) if net in supply_nets), default=0.0)
    max_return_rise = max((node_drop(index) for index, net in enumerate(node_nets) if net in return_nets), default=0.0)
    max_load_drop = max(
        (boundary_drop(item) for item in load_records if item["role"] != "load_return"),
        default=max_supply_drop,
    )
    paired_loop_drops: List[Dict[str, Any]] = []
    positive_by_pair = {item["pair_id"]: item for item in load_records if item["role"] != "load_return"}
    return_by_pair = {item["pair_id"]: item for item in load_records if item["role"] == "load_return"}
    for pair_id, positive in positive_by_pair.items():
        return_load = return_by_pair.get(pair_id)
        if not return_load:
            continue
        domain_id = positive["domain_id"]
        source_positive = next((item for item in supply_records if item["domain_id"] == domain_id), supply_records[0] if supply_records else None)
        source_return = next((item for item in return_records if item["domain_id"] == domain_id), return_records[0] if return_records else None)
        if not source_positive or not source_return:
            continue
        source_differential = float(source_positive["voltage_v"]) - float(source_return["voltage_v"])
        load_differential = boundary_voltage(positive) - boundary_voltage(return_load)
        paired_loop_drops.append({
            "pair_id": pair_id,
            "domain_id": domain_id,
            "supply_net": positive["net"],
            "return_net": return_load["net"],
            "source_differential_v": source_differential,
            "load_differential_v": load_differential,
            "loop_drop_v": abs(source_differential - load_differential),
        })
    max_loop_drop = max((item["loop_drop_v"] for item in paired_loop_drops), default=max_supply_drop + max_return_rise)
    max_drop = max_loop_drop if explicit_return else max_supply_drop

    terminal_evidence = build_source_to_load_evidence(
        source_records, load_records, voltage, conductance, rhs, scaled_residual, explicit_return,
    )
    if exact_terminals and terminal_evidence["status"] != "validated":
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode="dc",
            status="failed",
            model_status="approximate",
            issues=issues + [ValidationIssue(
                "SPIKE-BE-PI-E-0007", "error",
                "Exact source-to-load terminal validation failed: " + "; ".join(terminal_evidence["issues"] or ["a terminal lacks an exact geometry anchor"]),
                path="analysis.terminals",
                suggestion="Give every terminal a unique geometry anchor on its declared net and layer, and pair each load with one source.",
            )],
        )
    density_edges = [edge for edge in active_edges if edge["current_density_supported"]]
    max_density_edge = max(density_edges, key=lambda edge: edge["current_density_a_mm2"])
    p95_density = weighted_percentile_density(density_edges, 0.95)
    p99_density = weighted_percentile_density(density_edges, 0.99)
    total_network_loss = sum(edge["power_loss_w"] for edge in active_edges)
    total_copper_loss = sum(
        edge["power_loss_w"]
        for edge in active_edges
        if edge.get("kind") not in {"series_component", "contact"}
    )
    net_power_loss_w: dict[str, float] = {}
    layer_power_loss_w: dict[str, float] = {}
    geometry_power_loss_w: dict[str, float] = {}
    component_power_loss_w: dict[str, float] = {}
    for edge in active_edges:
        loss = float(edge["power_loss_w"])
        net = str(edge.get("net") or "unassigned")
        layer = str(edge.get("layer") or "through")
        geometry_kind = str(edge.get("kind") or "unknown")
        geometry_power_loss_w[geometry_kind] = geometry_power_loss_w.get(geometry_kind, 0.0) + loss
        if geometry_kind == "series_component":
            component = str(edge.get("component_ref") or edge.get("id") or "unassigned")
            component_power_loss_w[component] = component_power_loss_w.get(component, 0.0) + loss
        else:
            net_power_loss_w[net] = net_power_loss_w.get(net, 0.0) + loss
            layer_power_loss_w[layer] = layer_power_loss_w.get(layer, 0.0) + loss
    via_edges = [edge for edge in active_edges if edge["kind"] == "via"]
    peak_via_density = max(
        (edge["current_density_a_mm2"] for edge in via_edges),
        default=0.0,
    )
    max_drop_limit = float(spec.limits.get("max_voltage_drop_v", spec.limits.get("max_voltage_drop_mv", 50) / 1000))
    max_density_limit = float(spec.limits.get("max_current_density_a_mm2", 100.0))
    if max_drop > max_drop_limit:
        issues.append(ValidationIssue("SPIKE-BE-PI-W-0002", "warning", f"Maximum drop {max_drop * 1000:.3f} mV exceeds the configured limit.", path="analysis.limits.max_voltage_drop", suggestion="Inspect the highest-drop current path and its conductor and contact resistance.", status="violated"))
    if max_density_edge["current_density_a_mm2"] > max_density_limit:
        issues.append(ValidationIssue("SPIKE-BE-PI-W-0003", "warning", f"{max_density_edge['id']} reaches {max_density_edge['current_density_a_mm2']:.3f} A/mm2.", path=f"result.edges[{max_density_edge['id']}]", suggestion="Inspect and increase the affected conductor cross-section or reduce current.", status="violated"))
    issues.append(ValidationIssue(
        "SPIKE-BE-PI-W-0004",
        "warning",
        "Tracks, zones, pads, vias, and THT barrels use the shared finite-volume hybrid mesh; run mesh convergence before sign-off.",
        status="approximate",
    ))
    issues.append(ValidationIssue(
        "SPIKE-BE-PI-W-0004",
        "warning",
        "Compatibility notice: conductor discretization remains approximate until a mesh-convergence run passes.",
        status="approximate",
    ))
    if explicit_return:
        issues.append(ValidationIssue(
            "SPIKE-BE-PI-I-0001",
            "info",
            f"Supply and {spec.return_path.get('net', 'return')} conductors were solved as a paired current loop.",
            status="validated",
        ))
    if return_mode == "isolated_secondary":
        issues.append(ValidationIssue(
            "SPIKE-BE-PI-W-0006",
            "warning",
            "The transformer secondary is a galvanically isolated local DC boundary source; transformer magnetic behavior is not part of this DCIR result.",
            suggestion="Assign a coupled transformer or SPICE model for leakage, saturation, regulation, loss, and interwinding effects.",
            status="approximate",
        ))
    if contact_count == 0:
        issues.append(ValidationIssue(
            "SPIKE-BE-PI-W-0005",
            "warning",
            "No terminal package/contact resistance was assigned.",
            suggestion="Assign measured connector, shunt, package, and contact resistance where applicable.",
            status="approximate",
        ))

    probes: List[Dict[str, Any]] = []
    active_mesh_to_solution = {old: reindex[old] for old in active_nodes if old < len(mesh.nodes)}
    for index, probe in enumerate(spec.probes):
        mesh_node = nearest_mesh_node(mesh, probe, terminal_net(spec, probe))
        result: Dict[str, Any] = {
            "id": probe.get("id", f"probe-{index + 1}"),
            "name": probe.get("name", f"Probe {index + 1}"),
            "requested_layer": probe.get("layer"),
        }
        if mesh_node is None or mesh_node not in active_mesh_to_solution:
            result.update(status="unmapped", message="Probe is not on solved copper.")
        else:
            solved = active_mesh_to_solution[mesh_node]
            x, y, layer = node_positions[solved]
            resolved_mesh_node = mesh.nodes[mesh_node]
            connected_layers = sorted({
                node.layer
                for node in mesh.nodes
                if node.net == resolved_mesh_node.net
                and abs(node.x_mm - resolved_mesh_node.x_mm) <= 1e-6
                and abs(node.y_mm - resolved_mesh_node.y_mm) <= 1e-6
            })
            local_edges = [edge for edge in active_edges if edge["a"] == solved or edge["b"] == solved]
            result.update(
                status="mapped",
                position_mm=[x, y],
                layer=layer,
                resolved_layer=layer,
                connected_layers=connected_layers or [layer],
                net=node_nets[solved],
                voltage_v=float(voltage[solved]),
                voltage_drop_v=float(node_drop(solved)),
                peak_adjacent_current_a=float(max((abs(edge["current_a"]) for edge in local_edges), default=0.0)),
                peak_adjacent_current_density_a_mm2=float(max((edge["current_density_a_mm2"] for edge in local_edges), default=0.0)),
                adjacent_power_loss_w=float(sum(edge["power_loss_w"] for edge in local_edges) / 2.0),
                local_series_resistance_ohm=float(sum(edge["resistance_ohm"] for edge in local_edges)),
                adjacent_element_ids=[edge["id"] for edge in local_edges],
            )
        probes.append(result)

    visual_limit = max(1000, int(spec.options.get("visual_sample_limit", 50000)))
    physical_edges = physical_result_edges(active_edges)
    visual_edges = stratified_sample_records(
        physical_edges,
        visual_limit,
        value_key="current_density_a_mm2",
    )
    if (
        max_density_edge["kind"] not in TOPOLOGY_VISUALIZATION_KINDS
        and max_density_edge not in visual_edges
    ):
        visual_edges.append(max_density_edge)
    # Results are projected onto the authoritative mesh faces. Older result
    # bundles only carried branch centres, which forced clients to invent a
    # square footprint and visibly painted outside narrow/concave copper.
    physical_source_ids = {str(edge["source_id"]) for edge in physical_edges}
    active_cells = [
        cell
        for cell in mesh.cells
        if str(cell.get("source_id", "")) in physical_source_ids
        and len(cell.get("vertices_mm", [])) >= 3
    ]
    if len(active_cells) > visual_limit:
        active_cells = stratified_sample_records(active_cells, visual_limit)
        issues.append(ValidationIssue(
            "SPIKE-BE-SOLVER-P-0005",
            "info",
            f"Result-face output was deterministically reduced to {len(active_cells)} cells.",
            suggestion="Raise options.visual_sample_limit for a complete interactive field surface.",
            status="validated",
        ))

    face_bindings = bind_result_faces(active_cells, physical_edges)
    scalar_voltage = project_result_faces(active_cells, physical_edges,
        lambda edge: (float(voltage[edge["a"]]) + float(voltage[edge["b"]])) / 2.0,
        bindings=face_bindings,
    )
    scalar_drop = project_result_faces(active_cells, physical_edges,
        lambda edge: (node_drop(edge["a"]) + node_drop(edge["b"])) / 2.0,
        bindings=face_bindings,
    )
    current_density = project_result_faces(active_cells, physical_edges,
        lambda edge: edge["current_density_a_mm2"] if edge["current_density_supported"] else None,
        bindings=face_bindings,
    )
    current_field = project_result_faces(active_cells, physical_edges, lambda edge: abs(edge["current_a"]), bindings=face_bindings)
    operating_point_impedance = project_result_faces(active_cells, physical_edges,
        lambda edge: abs(
            (float(voltage[edge["a"]]) + float(voltage[edge["b"]]))
            / (2.0 * float(edge["current_a"]))
        ) if abs(float(edge["current_a"])) > 1e-15 else None,
        bindings=face_bindings,
    )
    power_loss = project_result_faces(active_cells, physical_edges, lambda edge: edge["power_loss_w"], bindings=face_bindings)
    via_source_ids = {str(edge["source_id"]) for edge in via_edges}
    via_cells = [cell for cell in active_cells if str(cell.get("source_id", "")) in via_source_ids]
    via_stress = project_result_faces(
        via_cells,
        via_edges,
        lambda edge: edge["current_density_a_mm2"],
    )
    current_vectors = []
    for edge in visual_edges:
        dx = float(edge["end_mm"][0] - edge["start_mm"][0])
        dy = float(edge["end_mm"][1] - edge["start_mm"][1])
        dz = float(edge["end_z_mm"] - edge["start_z_mm"])
        length = max(float(edge["length_mm"]), 1e-15)
        direction = 1.0 if edge["current_a"] >= 0 else -1.0
        magnitude = abs(float(edge["current_density_a_mm2"]))
        current_vectors.append({
            "x_mm": edge["x_mm"],
            "y_mm": edge["y_mm"],
            "z_mm": edge["z_mm"],
            "layer": edge["layer"],
            "net": edge["net"],
            "element_id": edge["id"],
            "value": magnitude,
            "magnitude": magnitude,
            "vector": [direction * dx / length, direction * dy / length, dz],
        })
    track_groups: Dict[str, List[Dict[str, Any]]] = {}
    for edge in active_edges:
        if edge["kind"] == "track":
            track_groups.setdefault(str(edge["source_id"]), []).append(edge)
    track_results: List[Dict[str, Any]] = []
    for source_id, segments in track_groups.items():
        peak = max(segments, key=lambda edge: abs(edge["current_a"]))
        track_results.append({
            **peak,
            "id": source_id,
            "kind": "track",
            "segment_count": len(segments),
            "resistance_ohm": float(sum(edge["resistance_ohm"] for edge in segments)),
            "length_mm": float(sum(edge["length_mm"] for edge in segments)),
            "voltage_drop_v": float(sum(edge["voltage_drop_v"] for edge in segments)),
            "power_loss_w": float(sum(edge["power_loss_w"] for edge in segments)),
            "current_density_a_mm2": float(max(edge["current_density_a_mm2"] for edge in segments)),
        })
    edge_results = [
        edge for edge in active_edges if edge["kind"] != "track"
    ] + track_results
    component_bridges = [
        {
            key: value
            for key, value in edge.items()
            if key not in {"a", "b", "width_mm", "thickness_mm"}
        }
        for edge in active_edges
        if edge["kind"] == "series_component"
    ]
    series_component_loss_w = float(sum(
        float(item["power_loss_w"]) for item in component_bridges
    ))
    detail_limit = max(1000, int(spec.options.get("result_detail_limit", 100000)))
    node_detail_indexes = sample_indexes(len(node_positions), detail_limit)
    edge_results_truncated = len(edge_results) > detail_limit
    if edge_results_truncated:
        edge_results = [edge_results[index] for index in sample_indexes(len(edge_results), detail_limit)]
        issues.append(ValidationIssue(
            "SPIKE-BE-SOLVER-P-0005",
            "info",
            f"Detailed branch output was deterministically reduced to {len(edge_results)} records; numerical summaries use the full solve.",
            suggestion="Raise options.result_detail_limit when complete per-branch export is required.",
            status="validated",
        ))
    total_time_s = perf_counter() - overall_started
    total_load_current_a = float(sum(
        item["current_a"]
        for item in load_records
        if item["role"] != "load_return" and item["current_a"] > 0
    ))
    return AnalysisResult(
        analysis_id=spec.analysis_id or "dc-hybrid-local",
        mode="dc",
        status="completed",
        model_status="approximate",
        summary={
            "max_voltage_drop_v": float(max_drop),
            "max_load_voltage_drop_v": float(max_load_drop),
            "max_supply_drop_v": float(max_supply_drop),
            "max_return_rise_v": float(max_return_rise),
            "max_loop_drop_v": float(max_loop_drop),
            "max_current_density_a_mm2": float(max_density_edge["current_density_a_mm2"]),
            "p95_current_density_a_mm2": float(p95_density),
            "p99_current_density_a_mm2": float(p99_density),
            "max_current_edge": max_density_edge["id"],
            "source_voltage_v": source_voltage,
            "total_load_current_a": total_load_current_a,
            "operating_point_impedance_ohm": (
                abs(float(source_voltage) / total_load_current_a)
                if total_load_current_a > 1e-15 else None
            ),
            "operating_point_impedance_definition": "absolute local conductor voltage divided by absolute branch current",
            "return_path_count": len(paired_loop_drops),
            "isolated_domain_count": 1 if return_mode == "isolated_secondary" else 0,
            "total_network_loss_w": float(total_network_loss),
            "total_copper_loss_w": float(total_copper_loss),
            "series_component_loss_w": series_component_loss_w,
            "series_component_count": len(component_bridges),
            "net_power_loss_w": net_power_loss_w,
            "layer_power_loss_w": layer_power_loss_w,
            "geometry_power_loss_w": geometry_power_loss_w,
            "component_power_loss_w": component_power_loss_w,
            "max_via_current_density_a_mm2": float(peak_via_density),
            "via_branch_count": len(via_edges),
            "node_count": size,
            "edge_count": len(active_edges),
            "matrix_nnz": int(conductance.nnz),
            "assembly_backend": assembly_backend.get("selected", "numpy"),
            "sparse_backend": linear_backend.get("selected", "boundary_only"),
            "max_scaled_linear_residual": scaled_residual,
            "mesh_build_time_s": mesh_time_s,
            "matrix_assembly_time_s": assembly_time_s,
            "linear_solve_time_s": solve_time_s,
            "total_solver_time_s": total_time_s,
            "visualization_sample_count": len(active_cells),
            "visualization_decimated": len(active_cells) < len(mesh.cells),
            "geometry_counts": {**mesh.geometry_counts, "contact": contact_count},
        },
        fields={
            "node_voltages": [
                {"x_mm": x, "y_mm": y, "layer": layer, "net": node_nets[index], "voltage_v": float(voltage[index])}
                for index in node_detail_indexes
                for x, y, layer in (node_positions[index],)
            ],
            "edge_results": edge_results,
            "branch_results": active_edges if spec.options.get("include_branch_results", False) else [],
            "visualization": {
                "schema": "spike/result-visualization/v1",
                "scalar_fields": {
                    "voltage_v": scalar_voltage,
                    "voltage_drop_v": scalar_drop,
                    "current_a": current_field,
                    "operating_point_impedance_ohm": operating_point_impedance,
                    "current_density_a_mm2": current_density,
                    "power_loss_w": power_loss,
                    "via_current_density_a_mm2": via_stress,
                },
                "vector_fields": {"current_density": current_vectors},
                "mesh": active_cells,
                "component_bridges": component_bridges,
            },
            "component_bridges": component_bridges,
        },
        networks={
            "source_to_load": terminal_evidence,
            "return_path": {
                "mode": return_mode,
                "net": str(spec.return_path.get("net", "")),
                "domain_id": str(spec.return_path.get("domain_id", "default")),
                "pairs": paired_loop_drops,
                "galvanically_isolated": return_mode == "isolated_secondary",
            },
        },
        probes=probes,
        issues=issues,
        provenance={
            "solver": "spike-hybrid-dc/v4",
            "formulation": "sparse_finite_volume_conductor_network",
            "mesh_contract": "spike/mesh-preview/v2",
            "conductivity_s_m": 5.8e7,
            "mesh_target_mm": mesh.target_size_mm,
            "via_model": str(spec.mesh.get("via_model", "extracted")),
            "via_plating_thickness_mm": float(spec.mesh.get("via_plating_thickness_mm", 0.025)),
            "geometry_counts": mesh.geometry_counts,
            "performance": {
                "mesh_build_s": mesh_time_s,
                "matrix_assembly_s": assembly_time_s,
                "linear_solve_s": solve_time_s,
                "total_s": total_time_s,
                "matrix_nnz": int(conductance.nnz),
                "scaled_residual": scaled_residual,
            },
            "acceleration": {
                "assembly": assembly_backend,
                "linear_solver": linear_backend or {
                    "requested": str(spec.options.get("sparse_backend", "auto")),
                    "selected": "boundary_only",
                    "selection_reason": "All solved nodes were fixed boundaries; no sparse solve was required.",
                    "fallback_used": False,
                },
            },
            "assumptions": [
                "uniform copper conductivity",
                "explicit source and load terminals",
                "explicit return copper is solved when a return path is configured",
                "ideal contacts unless assigned",
                "DC resistance only",
                "operating-point impedance is local V/I and is not frequency-domain Z(f)",
            ],
            "model_limits": ([
                "Transformer secondary is represented by a local DC voltage boundary only.",
                "Transformer magnetics, leakage inductance, saturation, regulation, losses, isolation breakdown, and interwinding capacitance are not modeled.",
            ] if return_mode == "isolated_secondary" else []),
        },
    )
