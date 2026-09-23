"""DesignIR adapter for topology-correct quasi-static PEEC RL extraction."""

from __future__ import annotations

from math import hypot, log10, sqrt
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from .hybrid_mesh import TOPOLOGY_ONLY_BRANCH_KINDS, HybridMesh, build_hybrid_mesh, nearest_mesh_node
from .loop_parasitics import extract_loop_parasitics
from .peec_matrices import TopologyResistanceSolver, embed_physical_inductance
from .peec_native_factory import dielectric_epsilon as _dielectric_epsilon, make_native_solver
from .peec_volume_adapter import VolumeResistanceOverlay, extract_volume_matrices
from .peec_volume_support import ZoneBasisSupportError
from .peec_network import (
    dense as _dense,
    extract_pdn_multiport as _extract_pdn_multiport,
    solve_port as _solve_port,
    solve_shared_reference_port_matrix as _solve_shared_reference_port_matrix,
)
from .numerics import assess_symmetric_positive_semidefinite
from .quasistatic_capacitance import estimate_branch_capacitance, zone_pad_mesh_dependence_issue

try:
    from python import spike_peec_native as native
except ImportError:  # Installed layouts may place the extension at top level.
    try:
        import spike_peec_native as native  # type: ignore[no-redef]
    except ImportError:
        native = None


def native_available() -> bool:
    return native is not None


def _frequencies(spec: AnalysisSpec) -> np.ndarray:
    start = float(spec.frequency_start_hz or 1e3)
    stop = float(spec.frequency_stop_hz or start)
    points = max(2, min(int(spec.frequency_points), 2001))
    return np.logspace(log10(start), log10(stop), points)


def _connected_component(
    mesh: HybridMesh,
    net: str,
    source_node: int,
) -> Tuple[List[int], List[int]]:
    branch_indices = [
        index for index, branch in enumerate(mesh.branches) if branch.net == net
    ]
    adjacency: Dict[int, List[Tuple[int, int]]] = {}
    for branch_index in branch_indices:
        branch = mesh.branches[branch_index]
        adjacency.setdefault(branch.node_p, []).append((branch.node_n, branch_index))
        adjacency.setdefault(branch.node_n, []).append((branch.node_p, branch_index))
    nodes = {source_node}
    branches: set[int] = set()
    pending = [source_node]
    while pending:
        current = pending.pop()
        for neighbor, branch_index in adjacency.get(current, []):
            branches.add(branch_index)
            if neighbor not in nodes:
                nodes.add(neighbor)
                pending.append(neighbor)
    return sorted(nodes), sorted(branches)


def _inferred_port(mesh: HybridMesh, net: str) -> Tuple[int, int] | None:
    branches = [branch for branch in mesh.branches if branch.net == net]
    if not branches:
        return None
    degree: Dict[int, int] = {}
    adjacency: Dict[int, set[int]] = {}
    for branch in branches:
        degree[branch.node_p] = degree.get(branch.node_p, 0) + 1
        degree[branch.node_n] = degree.get(branch.node_n, 0) + 1
        adjacency.setdefault(branch.node_p, set()).add(branch.node_n)
        adjacency.setdefault(branch.node_n, set()).add(branch.node_p)
    components: List[set[int]] = []
    remaining = set(adjacency)
    while remaining:
        component = {remaining.pop()}
        pending = list(component)
        while pending:
            current = pending.pop()
            for neighbor in adjacency[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    pending.append(neighbor)
        components.append(component)
    largest = max(components, key=len)
    candidates = [node for node in largest if degree[node] == 1] or list(largest)
    if len(candidates) < 2:
        return None

    def distance(a: int, b: int) -> float:
        p, q = mesh.nodes[a], mesh.nodes[b]
        return sqrt((p.x_mm - q.x_mm) ** 2 + (p.y_mm - q.y_mm) ** 2 + (p.z_mm - q.z_mm) ** 2)

    first = candidates[0]
    source = max(candidates, key=lambda node: distance(first, node))
    sink = max(candidates, key=lambda node: distance(source, node))
    return source, sink


def _terminal_ports(
    mesh: HybridMesh,
    spec: AnalysisSpec,
    net: str,
) -> Tuple[int, List[Tuple[str, int]], bool] | None:
    sources = [
        item for item in spec.sources if not item.get("net") or str(item.get("net")) == net
    ]
    loads = [
        item for item in spec.loads if not item.get("net") or str(item.get("net")) == net
    ]
    source_node = nearest_mesh_node(mesh, sources[0], net) if sources else None
    load_nodes = [
        (
            str(load.get("id") or load.get("name") or f"load-{index + 1}"),
            nearest_mesh_node(mesh, load, net),
        )
        for index, load in enumerate(loads)
    ]
    load_nodes = [(name, node) for name, node in load_nodes if node is not None]
    if source_node is not None and load_nodes:
        return source_node, [(name, int(node)) for name, node in load_nodes], False
    inferred = _inferred_port(mesh, net)
    if inferred is None:
        return None
    return inferred[0], [("inferred-load", inferred[1])], True


def _make_native_solver(
    mesh: HybridMesh,
    epsilon_r: float,
    spec: AnalysisSpec | None = None,
) -> Any:
    return make_native_solver(native, mesh, epsilon_r, spec)


def _local_shunt_matrices(
    mesh: HybridMesh,
    node_ids: Sequence[int],
    branch_indices: Sequence[int],
    branch_capacitance: np.ndarray,
    branch_loss_tangent: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Stamp branch C/2 at both endpoints against the ideal reference."""

    local_node = {node_id: index for index, node_id in enumerate(node_ids)}
    capacitance = np.zeros((len(node_ids), len(node_ids)), dtype=float)
    loss_coefficient = np.zeros_like(capacitance)
    for branch_index in branch_indices:
        value = float(branch_capacitance[branch_index])
        if value <= 0:
            continue
        branch = mesh.branches[branch_index]
        tan_delta = max(float(branch_loss_tangent[branch_index]), 0.0)
        for node_id in (branch.node_p, branch.node_n):
            local_index = local_node[node_id]
            capacitance[local_index, local_index] += value / 2.0
            loss_coefficient[local_index, local_index] += value * tan_delta / 2.0
    return capacitance, loss_coefficient


def solve_peec_2_5d(design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
    if native is None:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode=spec.mode,
            status="blocked",
            model_status="unsupported",
            issues=[ValidationIssue("PEEC_NATIVE_MISSING", "error", "The native PEEC runtime is not installed.")],
        )
    if spec.mode not in {"ac", "broadband_hf"}:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode=spec.mode,
            status="failed",
            model_status="unsupported",
            issues=[ValidationIssue("PEEC_MODE_UNSUPPORTED", "error", "The native PEEC adapter supports AC impedance extraction.")],
        )

    conductor_models = spec.options.get("conductor_models", {})
    roughness_model = str(conductor_models.get("surface_roughness_model", "none")).lower()
    if roughness_model not in {"none", "hammerstad"}:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode=spec.mode,
            status="blocked",
            model_status="unsupported",
            issues=[ValidationIssue(
                "ROUGHNESS_MODEL_UNSUPPORTED",
                "error",
                f"The native PEEC adapter does not implement the requested {roughness_model} roughness model.",
                suggestion="Use none or Hammerstad, or install a solver plugin validated for the requested material model.",
            )],
        )

    mesh = build_hybrid_mesh(design, spec)
    issues = list(mesh.issues)
    if mesh.truncated or not mesh.branches:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode=spec.mode,
            status="failed",
            model_status="failed" if mesh.truncated else "unsupported",
            issues=issues + ([] if mesh.truncated else [
                ValidationIssue("NO_PEEC_FILAMENTS", "error", "No connected copper geometry matched the selected nets.")
            ]),
        )

    physical_branch_indices = [
        index for index, branch in enumerate(mesh.branches)
        if branch.kind not in TOPOLOGY_ONLY_BRANCH_KINDS
    ]
    if not physical_branch_indices:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode=spec.mode,
            status="failed",
            model_status="failed",
            issues=issues + [ValidationIssue(
                "PEEC_NO_PHYSICAL_CONDUCTORS",
                "error",
                "The selected net contains only graph-topology links and has no physical conductor for field extraction.",
            )],
        )
    epsilon_r = _dielectric_epsilon(design)
    physical_mesh = HybridMesh(
        nodes=mesh.nodes,
        branches=[mesh.branches[index] for index in physical_branch_indices],
        target_size_mm=mesh.target_size_mm,
    )
    volume_extraction = spec.options.get("peec_volume_extraction") == "enabled"
    volume_quality: Dict[str, Any] | None = None
    try:
        native_solver, config = _make_native_solver(physical_mesh, epsilon_r, spec)
        if volume_extraction:
            volume = extract_volume_matrices(native, design, physical_mesh.branches)
            volume_quality = dict(volume.quality)
            raw_inductance = embed_physical_inductance(
                _dense(volume.inductance_h), len(mesh.branches), physical_branch_indices,
            )
        else:
            volume = None
            raw_inductance = embed_physical_inductance(
                _dense(native_solver.compute_partial_inductance()),
                len(mesh.branches), physical_branch_indices,
            )
        inductance, inductance_quality = assess_symmetric_positive_semidefinite(raw_inductance)
    except (ValueError, RuntimeError, np.linalg.LinAlgError) as error:
        issue_code = error.code if isinstance(error, ZoneBasisSupportError) else (
            "PEEC_VOLUME_EXTRACTION_FAILED" if volume_extraction else "PEEC_MATRIX_EXTRACTION_FAILED")
        return AnalysisResult(analysis_id=spec.analysis_id, mode=spec.mode,
            status="failed", model_status="failed",
            issues=issues + [ValidationIssue(
                issue_code, "error", str(error),
            )],
            provenance={"solved": False, "failure_stage": "volume_matrix_extraction" if volume_extraction else "physical_inductance_admission",
                        "volume_current_model": "uniform_volume_current" if volume_extraction else "disabled",
                        **({"zone_basis_support": error.report} if isinstance(error, ZoneBasisSupportError) else {})})
    topology_indices = [
        index for index in range(len(mesh.branches)) if index not in physical_branch_indices
    ]
    inductance_quality.update({
        "field_branch_count": len(physical_branch_indices),
        "topology_constraint_branch_count": len(topology_indices),
        "topology_constraint_kinds": sorted({mesh.branches[index].kind for index in topology_indices}),
    })
    resistance_indices = [
        index for index, branch in enumerate(mesh.branches) if branch.length_mm > 0.0
    ]
    resistance_solver = native_solver
    if resistance_indices != physical_branch_indices:
        resistance_mesh = HybridMesh(
            nodes=mesh.nodes,
            branches=[mesh.branches[index] for index in resistance_indices],
            target_size_mm=mesh.target_size_mm,
        )
        resistance_solver, _ = _make_native_solver(resistance_mesh, epsilon_r, spec)
    solver = TopologyResistanceSolver(resistance_solver, mesh, resistance_indices)
    if volume_extraction:
        solver = VolumeResistanceOverlay(
            solver, physical_branch_indices, _dense(volume.dc_resistance_ohm)
        )
    if topology_indices:
        issues.append(ValidationIssue(
            "PEEC_TOPOLOGY_FIELD_EXCLUDED",
            "warning",
            f"Excluded {len(topology_indices)} graph-only link(s) from magnetic/capacitive field bases while retaining their mesh resistance in the circuit solve.",
            suggestion="Review attachment geometry and DC resistance; graph links are not finite field filaments.",
            status="approximate",
        ))
    if inductance_quality["negative_eigenmode_count"]:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode=spec.mode,
            status="failed",
            model_status="failed",
            issues=issues + [ValidationIssue(
                "PEEC_INDUCTANCE_NONPASSIVE",
                "error",
                f"The physical partial-inductance matrix contains {inductance_quality['negative_eigenmode_count']} negative-energy mode(s); no passivity projection was applied.",
                suggestion="Refine overlapping physical copper primitives or use a validated volume-integral PEEC extractor.",
            )],
            provenance={
                "solver": "spike-peec-native/v0.4", "solved": False,
                "numerical_quality": {"inductance_passivity": inductance_quality},
                "failure_stage": "physical_inductance_admission",
                "inductance_units": "H",
            },
        )
    branch_capacitance, branch_loss_tangent, capacitance_info = estimate_branch_capacitance(
        design, spec, mesh.branches
    )
    topology_mask = np.ones(len(mesh.branches), dtype=bool)
    topology_mask[physical_branch_indices] = False
    branch_capacitance = np.asarray(branch_capacitance, dtype=float)
    branch_loss_tangent = np.asarray(branch_loss_tangent, dtype=float)
    branch_capacitance[topology_mask] = 0.0
    branch_loss_tangent[topology_mask] = 0.0
    capacitance_info = dict(capacitance_info)
    capacitance_info.update({
        "field_branch_count": len(physical_branch_indices),
        "topology_constraint_branch_count_excluded": len(topology_indices),
        "total_capacitance_f": float(np.sum(branch_capacitance)),
    })
    frequencies = _frequencies(spec)
    requested = sorted({branch.net for branch in mesh.branches})
    ports: List[Dict[str, Any]] = []
    pdn_multiports: List[Dict[str, Any]] = []
    loop_parasitics: List[Dict[str, Any]] = []
    inferred_any = False
    last_branch_currents: Dict[int, float] = {}

    for net in requested:
        terminals = _terminal_ports(mesh, spec, net)
        if terminals is None:
            issues.append(ValidationIssue("PEEC_PORT_UNRESOLVED", "error", f"No two connected port nodes were found for {net}."))
            continue
        source_node, loads, inferred = terminals
        inferred_any = inferred_any or inferred
        node_ids, branch_indices = _connected_component(mesh, net, source_node)
        branch_position = {branch_index: position for position, branch_index in enumerate(branch_indices)}
        local_inductance = inductance[np.ix_(branch_indices, branch_indices)]
        local_capacitance, local_loss_coefficient = _local_shunt_matrices(
            mesh,
            node_ids,
            branch_indices,
            branch_capacitance,
            branch_loss_tangent,
        )
        connected_loads = [
            (load_name, sink_node)
            for load_name, sink_node in loads
            if sink_node in node_ids
        ]
        for load_name, sink_node in loads:
            if sink_node not in node_ids:
                issues.append(
                    ValidationIssue(
                        "PEEC_LOAD_DISCONNECTED",
                        "error",
                        f"{load_name} is disconnected from the selected source on {net}.",
                    )
                )
                continue
            sweep: List[Dict[str, float]] = []
            solve_diagnostics: List[Dict[str, Any]] = []
            equivalent_rl: complex | None = None
            for frequency_index, frequency in enumerate(frequencies):
                resistance = _dense(solver.compute_resistance(float(frequency)))
                local_resistance = resistance[np.ix_(branch_indices, branch_indices)]
                branch_impedance = local_resistance + 1j * 2 * np.pi * float(frequency) * local_inductance
                omega = 2 * np.pi * float(frequency)
                node_admittance = omega * local_loss_coefficient + 1j * omega * local_capacitance
                try:
                    if frequency_index == 0:
                        equivalent_rl, _, _ = _solve_port(
                            mesh,
                            node_ids,
                            branch_indices,
                            source_node,
                            sink_node,
                            branch_impedance,
                        )
                    impedance, currents, solve_quality = _solve_port(
                        mesh,
                        node_ids,
                        branch_indices,
                        source_node,
                        sink_node,
                        branch_impedance,
                        node_admittance,
                        diagnostics=frequency_index in {0, len(frequencies) - 1},
                    )
                except ValueError as exc:
                    issues.append(ValidationIssue("PEEC_MNA_SINGULAR", "error", f"{net}: {exc}."))
                    sweep = []
                    break
                solve_diagnostics.append(solve_quality)
                if frequency_index == len(frequencies) - 1:
                    last_branch_currents.update(
                        {
                            branch_index: float(abs(currents[branch_position[branch_index]]))
                            for branch_index in branch_indices
                        }
                    )
                sweep.append(
                    {
                        "frequency_hz": float(frequency),
                        "resistance_ohm": float(impedance.real),
                        "reactance_ohm": float(impedance.imag),
                        "magnitude_ohm": float(abs(impedance)),
                        "phase_deg": float(np.degrees(np.angle(impedance))),
                    }
                )
            if sweep:
                start = sweep[0]
                start_omega = 2 * np.pi * start["frequency_hz"]
                port_capacitance = float(np.sum(branch_capacitance[branch_indices]))
                port_loss_weighted = float(
                    np.sum(
                        branch_capacitance[branch_indices]
                        * branch_loss_tangent[branch_indices]
                    ) / port_capacitance
                ) if port_capacitance > 0 else 0.0
                max_residual = max(item["relative_residual"] for item in solve_diagnostics)
                sampled_conditions = [
                    item["condition_number"] for item in solve_diagnostics
                    if item["condition_number"] is not None
                ]
                max_condition = max(sampled_conditions, default=None)
                fallback_count = sum(
                    item["method"] != "dense_direct" for item in solve_diagnostics
                )
                ports.append(
                    {
                        "contract": "spike/rlgc-network/v1",
                        "model_status": "approximate",
                        "net": net,
                        "source_node": source_node,
                        "sink_node": sink_node,
                        "load": load_name,
                        "ports_inferred": inferred,
                        "resistance_ohm": float(equivalent_rl.real if equivalent_rl is not None else start["resistance_ohm"]),
                        "inductance_h": float(equivalent_rl.imag / start_omega if equivalent_rl is not None else start["reactance_ohm"] / start_omega),
                        "capacitance_f": port_capacitance if port_capacitance > 0 else None,
                        "conductance_s": start_omega * port_capacitance * port_loss_weighted if port_loss_weighted > 0 else None,
                        "parameter_availability": {
                            "resistance": "extracted",
                            "inductance": "extracted_partial_inductance",
                            "capacitance": "approximate_single_reference" if port_capacitance > 0 else "unsupported",
                            "conductance": "approximate_loss_tangent" if port_loss_weighted > 0 else "unsupported",
                        },
                        "network_uses": ["driving_point_impedance", "spice_rlcg_export", "external_network_processor"],
                        "blocked_uses": ["characteristic_impedance", "propagation_delay", "transmission_line_s_parameters", "eye_diagram"],
                        "quality": {
                            "inductance_passivity": inductance_quality,
                            "capacitance": capacitance_info,
                            "maximum_relative_residual": max_residual,
                            "maximum_sampled_condition_number": max_condition,
                            "least_squares_fallback_count": fallback_count,
                            "frequency_model": {
                                "skin_effect": bool(config.enable_skin_effect),
                                "surface_roughness_model": roughness_model,
                                "rms_roughness_um": float(config.roughness_rms_um),
                            },
                        },
                        "impedance": sweep,
                    }
                )

        if connected_loads:
            pdn_multiport, pdn_issues = _extract_pdn_multiport(
                mesh,
                spec,
                solver,
                net,
                source_node,
                connected_loads[0],
                inferred,
                node_ids,
                branch_indices,
                local_inductance,
                local_capacitance,
                local_loss_coefficient,
                frequencies,
            )
            issues.extend(pdn_issues)
            if pdn_multiport is not None:
                pdn_multiports.append(pdn_multiport)

    loop_parasitics, loop_issues, loop_branch_currents = extract_loop_parasitics(
        mesh,
        spec,
        solver,
        inductance,
        branch_capacitance,
        frequencies,
    )
    issues.extend(loop_issues)
    last_branch_currents.update(loop_branch_currents)

    if inferred_any:
        issues.append(
            ValidationIssue(
                "PEEC_PORTS_INFERRED",
                "warning",
                "No explicit AC source/load pair was supplied for at least one net; the most distant endpoint pair was used.",
                suggestion="Place explicit AC ports for repeatable sign-off extraction.",
                status="approximate",
            )
        )
    issues.append(ValidationIssue(
        "PEEC_RLCG_EXTRACTION_EXPERIMENTAL",
        "warning",
        "R and partial L are extracted from the hybrid conductor mesh. C and dielectric G use a bounded single-reference stackup estimate and are not a multiconductor electrostatic field solve.",
        suggestion="Run mesh convergence and correlate critical ports against a validated BEM/FEM extractor or measurement.",
        status="approximate",
    ))
    if capacitance_info.get("status") == "approximate":
        issues.append(ValidationIssue(
            "PEEC_CAPACITANCE_APPROXIMATE",
            "warning",
            f"Estimated {float(capacitance_info.get('total_capacitance_f', 0.0)) * 1e12:.6g} pF across {int(capacitance_info.get('estimated_branch_count', 0))} planar mesh branches; {int(capacitance_info.get('skipped_via_branch_count', 0))} via/barrel branches were excluded.",
            suggestion="Provide an explicit return conductor and fabrication dielectric/loss data; use a validated electrostatic solver for sign-off capacitance.",
            status="approximate",
        ))
        mesh_c_issue = zone_pad_mesh_dependence_issue(
            mesh.branches, physical_branch_indices, volume_extraction)
        if mesh_c_issue is not None:
            issues.append(mesh_c_issue)
    else:
        issues.append(ValidationIssue(
            "PEEC_CAPACITANCE_UNSUPPORTED",
            "warning",
            str(capacitance_info.get("reason", "No compatible reference/dielectric geometry was available.")),
            suggestion="Import dielectric thickness/permittivity and select a return conductor.",
            status="unsupported",
        ))
    issues.append(
        ValidationIssue(
            "VIA_PLATING_ASSUMPTION",
            "warning",
            f"Via barrels without fabrication plating data use {float(spec.mesh.get('via_plating_thickness_mm', 0.025)):.4g} mm plating.",
            suggestion="Set mesh.via_plating_thickness_mm from fabrication data.",
            status="approximate",
        )
    )

    max_span_mm = max((branch.length_mm for branch in mesh.branches), default=0.0)
    wavelength_mm = 299_792_458_000 / (float(frequencies[-1]) * max(config.eps_r, 1.0) ** 0.5)
    if max_span_mm > wavelength_mm / 10:
        issues.append(
            ValidationIssue(
                "QUASI_STATIC_LIMIT_EXCEEDED",
                "error",
                "The largest mesh branch exceeds one tenth of the dielectric wavelength at the stop frequency.",
                suggestion="Refine the mesh, lower the stop frequency, or use a validated full-wave solver.",
                status="violated",
            )
        )
    if any(issue.severity == "error" for issue in issues) or (not ports and not loop_parasitics):
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            mode=spec.mode,
            status="failed",
            model_status="failed",
            issues=issues,
        )

    worst_residual = max(
        (
            float(port.get("quality", {}).get("maximum_relative_residual", 0.0))
            for port in ports
        ),
        default=0.0,
    )
    worst_residual = max(
        worst_residual,
        max(
            (
                float(item.get("quality", {}).get("maximum_relative_residual", 0.0))
                for item in pdn_multiports
            ),
            default=0.0,
        ),
    )
    worst_residual = max(
        worst_residual,
        max(
            (
                float(item.get("quality", {}).get("maximum_relative_residual", 0.0))
                for item in loop_parasitics
            ),
            default=0.0,
        ),
    )
    sampled_conditions = [
        float(value)
        for port in ports
        for value in [port.get("quality", {}).get("maximum_sampled_condition_number")]
        if value is not None
    ]
    sampled_conditions.extend(
        float(value)
        for item in pdn_multiports
        for value in [item.get("quality", {}).get("maximum_sampled_condition_number")]
        if value is not None
    )
    sampled_conditions.extend(
        float(value)
        for item in loop_parasitics
        for value in [item.get("quality", {}).get("maximum_sampled_condition_number")]
        if value is not None
    )
    worst_condition = max(sampled_conditions, default=0.0)
    if worst_condition > 1e12:
        issues.append(ValidationIssue(
            "PEEC_MATRIX_ILL_CONDITIONED",
            "warning",
            f"The sampled PEEC MNA condition number reached {worst_condition:.6g}.",
            suggestion="Refine/clean overlapping geometry, shorten extreme aspect-ratio branches, and compare mesh levels.",
            status="approximate",
        ))
    if worst_residual > 1e-8:
        issues.append(ValidationIssue(
            "PEEC_SOLVE_RESIDUAL_HIGH",
            "warning",
            f"The maximum normalized linear-solve residual was {worst_residual:.6g}.",
            suggestion="Do not use this extraction for sign-off until conditioning and mesh convergence improve.",
            status="approximate",
        ))

    first = ports[0] if ports else None
    first_loop = loop_parasitics[0] if loop_parasitics else None
    preview = mesh.to_preview(max(int(spec.mesh.get("max_preview_cells", 25000)), 100))
    from .hybrid_mesh import is_visualizable_physical_branch

    physical = [
        (index, branch)
        for index, branch in enumerate(mesh.branches)
        if is_visualizable_physical_branch(branch)
    ]
    physical_by_source: Dict[str, List[tuple[int, Any]]] = {}
    for index, branch in physical:
        physical_by_source.setdefault(branch.source_id, []).append((index, branch))

    def cell_center(cell: Dict[str, Any]) -> tuple[float, float, float]:
        vertices = cell["vertices_mm"]
        count = max(len(vertices), 1)
        return tuple(
            sum(float(vertex[axis]) for vertex in vertices) / count
            for axis in range(3)
        )

    physical_cells = [
        cell for cell in preview["cells"]
        if str(cell.get("source_id", "")) in physical_by_source
        and len(cell.get("vertices_mm", [])) >= 3
    ]
    cell_branches = []
    for cell in physical_cells:
        candidates = physical_by_source[str(cell["source_id"])]
        layer = str(cell.get("layer", ""))
        matching = [
            item for item in candidates
            if item[1].layer == layer
            or layer in item[1].layer.split("->")
            or item[1].layer in layer.split("->")
        ] or candidates
        x, y, z = cell_center(cell)
        cell_branches.append((cell, *min(
            matching,
            key=lambda item: (
                x - (item[1].start_mm[0] + item[1].end_mm[0]) / 2
            ) ** 2 + (
                y - (item[1].start_mm[1] + item[1].end_mm[1]) / 2
            ) ** 2 + (
                z - (item[1].start_mm[2] + item[1].end_mm[2]) / 2
            ) ** 2,
        )))

    current_field = []
    for cell, index, branch in cell_branches:
        x, y, z = cell_center(cell)
        current_field.append({
            "x_mm": x,
            "y_mm": y,
            "z_mm": z,
            "layer": cell.get("layer", branch.layer),
            "net": cell.get("net", branch.net),
            "element_id": cell["id"],
            "source_kind": cell.get("source_kind", branch.kind),
            "vertices_mm": cell["vertices_mm"],
            "branch_index": index,
            "value": last_branch_currents.get(index, 0.0),
        })
    current_density_field = [
        {
            **sample,
            "value": sample["value"] / max(branch.width_mm * branch.thickness_mm, 1e-15),
        }
        for sample, (_, branch_index, branch) in zip(current_field, cell_branches)
    ]
    current_vectors = []
    for sample, (_, index, branch) in zip(current_density_field, cell_branches):
        dx = branch.end_mm[0] - branch.start_mm[0]
        dy = branch.end_mm[1] - branch.start_mm[1]
        dz = branch.end_mm[2] - branch.start_mm[2]
        length = max(branch.length_mm, 1e-15)
        magnitude = sample["value"]
        current_vectors.append({
            **sample,
            "magnitude": magnitude,
            "vector": [dx / length, dy / length, dz / length],
        })
    via_stress = [
        sample for sample, (_, _index, branch) in zip(current_density_field, cell_branches)
        if branch.kind == "via"
    ]
    return AnalysisResult(
        analysis_id=spec.analysis_id or "peec-local",
        mode=spec.mode,
        status="completed",
        model_status="approximate",
        summary={
            "node_count": len(mesh.nodes),
            "filament_count": len(mesh.branches),
            "field_filament_count": len(physical_branch_indices),
            "port_count": len(ports),
            "pdn_multiport_count": len(pdn_multiports),
            "loop_parasitic_count": len(loop_parasitics),
            "geometry_counts": mesh.geometry_counts,
            "partial_inductance_h": first["inductance_h"] if first else None,
            "loop_inductance_h": first_loop["total_loop_inductance_h"] if first_loop else None,
            "resistance_start_ohm": (first or first_loop)["impedance"][0]["resistance_ohm"],
            "resistance_stop_ohm": (first or first_loop)["impedance"][-1]["resistance_ohm"],
            "capacitance_f": first["capacitance_f"] if first else first_loop["estimated_net_capacitance_f"],
            "conductance_start_s": first["conductance_s"] if first else None,
            "frequency_start_hz": float(frequencies[0]),
            "frequency_stop_hz": float(frequencies[-1]),
            "maximum_relative_residual": worst_residual,
            "maximum_sampled_condition_number": worst_condition,
        },
        fields={
            "branch_currents_at_stop_a": current_field,
            "visualization": {
                "schema": "spike/result-visualization/v1",
                "scalar_fields": {
                    "current_a": current_field,
                    "current_density_a_mm2": current_density_field,
                    "via_current_density_a_mm2": via_stress,
                },
                "vector_fields": {"current_density": current_vectors},
                "mesh": physical_cells,
            },
        },
        networks={
            "parasitics": ports,
            "pdn_multiports": pdn_multiports,
            "loop_parasitics": loop_parasitics,
        },
        issues=issues,
        provenance={
            "solver": "spike-peec-native/v0.4",
            "formulation": "topology_correct_peec_rlcg_2_5d",
            "native": True,
            "epsilon_r": config.eps_r,
            "mesh_target_mm": mesh.target_size_mm,
            "branch_admission": dict(mesh.branch_admission),
            "via_model": str(spec.mesh.get("via_model", "extracted")),
            "via_plating_thickness_mm": float(spec.mesh.get("via_plating_thickness_mm", 0.025)),
            "geometry_counts": mesh.geometry_counts,
            "numerical_quality": {
                "inductance_passivity": inductance_quality,
                "capacitance": capacitance_info,
                **({"volume_extraction": volume_quality} if volume_quality is not None else {}),
            },
            "volume_current_model": "uniform_volume_current" if volume_extraction else "disabled",
            "volume_extraction_work": "bounded_adaptive_pair_integration" if volume_extraction else "disabled",
            "limits": [
                "quasi-static RLCG driving-point model",
                ("uniform finite-volume planar and annular magnetic current bases"
                 if volume_extraction else "rectangular filament magnetic approximation"),
                "single-reference approximate capacitance and dielectric loss",
                "PDN candidate matrices use the explicit source terminal as an ideal common reference",
                "loop extraction requires explicit forward/return pad-to-pad paths and includes mutual partial inductance",
                "no proximity effect or multiconductor electrostatic matrix",
            ],
        },
    )
