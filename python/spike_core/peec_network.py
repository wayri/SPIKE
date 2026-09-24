"""PEEC conductor-network assembly and shared-reference PDN extraction.

This module owns the linear network mechanics used by the native PEEC adapter.
It deliberately contains no native-runtime construction or DesignIR orchestration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from .contracts import AnalysisSpec, ValidationIssue
from .hybrid_mesh import HybridMesh, nearest_mesh_node


def dense(value: Any) -> np.ndarray:
    return np.asarray(value.toarray() if hasattr(value, "toarray") else value, dtype=float)


def assemble_mna(
    mesh: HybridMesh,
    node_ids: Sequence[int],
    branch_indices: Sequence[int],
    reference_node: int,
    branch_impedance: np.ndarray,
    node_admittance: np.ndarray | None = None,
) -> Tuple[np.ndarray, Dict[int, int], int, Dict[int, int], int]:
    """Assemble one grounded PEEC MNA matrix for one conductor component."""

    local_node = {node_id: index for index, node_id in enumerate(node_ids)}
    if reference_node not in local_node:
        raise ValueError("reference is not in the connected copper component")
    ground = local_node[reference_node]
    retained = [index for index in range(len(node_ids)) if index != ground]
    voltage_index = {node: index for index, node in enumerate(retained)}
    incidence = np.zeros((len(node_ids), len(branch_indices)), dtype=float)
    for column, branch_index in enumerate(branch_indices):
        branch = mesh.branches[branch_index]
        incidence[local_node[branch.node_p], column] = 1.0
        incidence[local_node[branch.node_n], column] = -1.0
    reduced = incidence[retained, :]
    branch_count, voltage_count = len(branch_indices), len(retained)
    matrix = np.zeros(
        (branch_count + voltage_count, branch_count + voltage_count),
        dtype=complex,
    )
    matrix[:branch_count, :branch_count] = branch_impedance
    matrix[:branch_count, branch_count:] = -reduced.T
    matrix[branch_count:, :branch_count] = reduced
    if node_admittance is not None:
        local_admittance = np.asarray(node_admittance, dtype=complex)
        if local_admittance.shape != (len(node_ids), len(node_ids)):
            raise ValueError("node admittance does not match the local PEEC node count")
        matrix[branch_count:, branch_count:] = local_admittance[np.ix_(retained, retained)]
    return matrix, local_node, ground, voltage_index, branch_count


def solve_linear_system(
    matrix: np.ndarray,
    rhs: np.ndarray,
    diagnostics: bool,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    matrix = np.asarray(matrix, dtype=complex)
    rhs = np.asarray(rhs, dtype=complex)
    if (matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not matrix.size
            or rhs.ndim not in (1, 2) or rhs.shape[0] != matrix.shape[0]
            or not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(rhs))):
        raise ValueError("PEEC MNA requires a finite nonempty square matrix and compatible finite RHS")
    method = "dense_direct"
    rank = matrix.shape[0]
    try:
        solution = np.linalg.solve(matrix, rhs)
    except np.linalg.LinAlgError:
        solution, _, rank, _ = np.linalg.lstsq(matrix, rhs, rcond=1e-11)
        method = "rank_revealing_least_squares"
        if rank < matrix.shape[0]:
            raise ValueError("PEEC MNA matrix is rank deficient")
    if not np.all(np.isfinite(solution)):
        raise ValueError("PEEC MNA solution contains nonfinite values")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        relative_residual = float(
            np.linalg.norm(matrix @ solution - rhs)
            / max(np.linalg.norm(rhs), np.finfo(float).eps)
        )
    if not np.isfinite(relative_residual) or relative_residual > 1e-7:
        raise ValueError("PEEC MNA solution failed its relative residual check")
    condition_number = (
        float(np.linalg.cond(matrix))
        if diagnostics and matrix.shape[0] <= 400
        else None
    )
    if condition_number is not None and not np.isfinite(condition_number):
        raise ValueError("PEEC MNA condition estimate is nonfinite")
    return solution, {
        "method": method,
        "rank": int(rank),
        "order": int(matrix.shape[0]),
        "relative_residual": relative_residual,
        "condition_number": condition_number,
        "condition_estimate_status": (
            "sampled" if condition_number is not None
            else "omitted_scale_limit" if diagnostics
            else "not_requested"
        ),
    }


def solve_excitation(
    mesh: HybridMesh,
    node_ids: Sequence[int],
    branch_indices: Sequence[int],
    source_node: int,
    reference_node: int,
    branch_impedance: np.ndarray,
    node_admittance: np.ndarray | None = None,
    diagnostics: bool = False,
) -> Tuple[np.ndarray, Dict[int, complex], Dict[str, Any]]:
    """Solve one ampere from a conductor node into a shared reference node."""

    matrix, local_node, ground, voltage_index, branch_count = assemble_mna(
        mesh, node_ids, branch_indices, reference_node, branch_impedance, node_admittance
    )
    if source_node not in local_node:
        raise ValueError("source and reference are not in one connected copper component")
    rhs = np.zeros(matrix.shape[0], dtype=complex)
    source_local = local_node[source_node]
    if source_local != ground:
        rhs[branch_count + voltage_index[source_local]] = 1.0
    solution, quality = solve_linear_system(matrix, rhs, diagnostics)
    node_voltages = {
        node_id: 0j if local_index == ground
        else complex(solution[branch_count + voltage_index[local_index]])
        for node_id, local_index in local_node.items()
    }
    return solution[:branch_count], node_voltages, quality


def solve_port(
    mesh: HybridMesh,
    node_ids: Sequence[int],
    branch_indices: Sequence[int],
    source_node: int,
    sink_node: int,
    branch_impedance: np.ndarray,
    node_admittance: np.ndarray | None = None,
    diagnostics: bool = False,
) -> Tuple[complex, np.ndarray, Dict[str, Any]]:
    """Solve [Z -A.T; A 0] [I;V] = [0;J] for a one-ampere port."""

    currents, voltages, quality = solve_excitation(
        mesh,
        node_ids,
        branch_indices,
        source_node,
        sink_node,
        branch_impedance,
        node_admittance,
        diagnostics,
    )
    return voltages[source_node] - voltages[sink_node], currents, quality


def solve_shared_reference_port_matrix(
    mesh: HybridMesh,
    node_ids: Sequence[int],
    branch_indices: Sequence[int],
    port_nodes: Sequence[int],
    reference_node: int,
    branch_impedance: np.ndarray,
    node_admittance: np.ndarray | None = None,
    diagnostics: bool = False,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Return Z(row, column) for rail nodes referenced to one explicit anchor."""

    if not port_nodes:
        raise ValueError("at least one multiport node is required")
    if reference_node in port_nodes or len(set(port_nodes)) != len(port_nodes):
        raise ValueError("multiport nodes must be unique and distinct from the reference")
    system, local_node, ground, voltage_index, branch_count = assemble_mna(
        mesh, node_ids, branch_indices, reference_node, branch_impedance, node_admittance
    )
    if any(node not in local_node for node in port_nodes):
        raise ValueError("every multiport node must be in the connected copper component")
    rhs = np.zeros((system.shape[0], len(port_nodes)), dtype=complex)
    for column, excitation_node in enumerate(port_nodes):
        rhs[branch_count + voltage_index[local_node[excitation_node]], column] = 1.0
    solution, quality = solve_linear_system(system, rhs, diagnostics)
    matrix = np.zeros((len(port_nodes), len(port_nodes)), dtype=complex)
    for row, observation_node in enumerate(port_nodes):
        matrix[row, :] = solution[
            branch_count + voltage_index[local_node[observation_node]], :
        ]
    return matrix, quality


def impedance_point(frequency_hz: float, value: complex) -> Dict[str, float]:
    return {
        "frequency_hz": float(frequency_hz),
        "resistance_ohm": float(value.real),
        "reactance_ohm": float(value.imag),
        "magnitude_ohm": float(abs(value)),
        "phase_deg": float(np.degrees(np.angle(value))),
    }


def extract_pdn_multiport(
    mesh: HybridMesh,
    spec: AnalysisSpec,
    solver: Any,
    net: str,
    reference_node: int,
    observation: Tuple[str, int],
    inferred: bool,
    node_ids: Sequence[int],
    branch_indices: Sequence[int],
    local_inductance: np.ndarray,
    local_capacitance: np.ndarray,
    local_loss_coefficient: np.ndarray,
    frequencies: Sequence[float],
) -> Tuple[Dict[str, Any] | None, List[ValidationIssue]]:
    raw_candidates = spec.options.get("pdn_candidate_ports", [])
    if not raw_candidates:
        return None, []
    issues: List[ValidationIssue] = []
    if not isinstance(raw_candidates, list):
        return None, [ValidationIssue(
            "SPIKE-BE-PI-E-0102", "error",
            "options.pdn_candidate_ports must be an array of explicit terminal objects.",
            path="options.pdn_candidate_ports",
        )]
    if inferred:
        return None, [ValidationIssue(
            "SPIKE-BE-PI-E-0102", "error",
            "PDN multiport extraction requires explicit source and observation terminals.",
            path="options.pdn_candidate_ports",
            suggestion="Place and review an AC source plus at least one load before extracting candidate ports.",
        )]
    try:
        configured_limit = int(spec.options.get("max_pdn_candidate_ports", 16))
    except (TypeError, ValueError):
        return None, [ValidationIssue(
            "SPIKE-BE-PI-P-0103", "error",
            "options.max_pdn_candidate_ports must be an integer from 1 through 64.",
            path="options.max_pdn_candidate_ports",
        )]
    if configured_limit < 1 or configured_limit > 64:
        return None, [ValidationIssue(
            "SPIKE-BE-PI-P-0103", "error",
            "options.max_pdn_candidate_ports must be from 1 through the hard limit of 64.",
            path="options.max_pdn_candidate_ports",
        )]
    invalid_candidate_index = next(
        (index for index, item in enumerate(raw_candidates) if not isinstance(item, dict)),
        None,
    )
    if invalid_candidate_index is not None:
        return None, [ValidationIssue(
            "SPIKE-BE-PI-E-0102", "error",
            "Every PDN candidate port must be an explicit terminal object.",
            path=f"options.pdn_candidate_ports[{invalid_candidate_index}]",
        )]
    candidates_for_net = [
        item for item in raw_candidates
        if isinstance(item, dict) and (not item.get("net") or str(item.get("net")) == net)
    ]
    if not candidates_for_net:
        return None, []
    if len(candidates_for_net) > configured_limit:
        return None, [ValidationIssue(
            "SPIKE-BE-PI-P-0103", "error",
            f"{len(candidates_for_net)} PDN candidate ports exceed the configured limit of {configured_limit}.",
            path="options.pdn_candidate_ports",
            suggestion="Run bounded candidate batches or raise max_pdn_candidate_ports up to the hard limit of 64.",
        )]

    observation_name, observation_node = observation
    descriptors: List[Dict[str, Any]] = [{
        "id": observation_name,
        "role": "observation",
        "node": observation_node,
        "endpoint_reviewed": True,
    }]
    used_nodes = {reference_node, observation_node}
    for index, candidate in enumerate(candidates_for_net):
        identifier = str(candidate.get("id") or candidate.get("name") or f"candidate-{index + 1}")
        node = nearest_mesh_node(mesh, candidate, net)
        if node is None or node not in node_ids:
            issues.append(ValidationIssue(
                "SPIKE-BE-PI-E-0102", "error",
                f"PDN candidate port {identifier} did not map to the source-connected conductor on {net}.",
                path=f"options.pdn_candidate_ports[{index}]",
            ))
            continue
        if node in used_nodes:
            issues.append(ValidationIssue(
                "SPIKE-BE-PI-E-0102", "error",
                f"PDN candidate port {identifier} duplicates the reference or observation mesh node.",
                path=f"options.pdn_candidate_ports[{index}]",
            ))
            continue
        used_nodes.add(node)
        descriptors.append({
            "id": identifier,
            "role": "candidate",
            "node": int(node),
            "endpoint_reviewed": candidate.get("endpoint_reviewed") is True,
            "source_terminal": {
                key: candidate[key]
                for key in ("position_mm", "at", "layer", "layer_scope", "geometry_anchor")
                if key in candidate
            },
        })
    if len(descriptors) < 2:
        return None, issues or [ValidationIssue(
            "SPIKE-BE-PI-E-0102", "error",
            f"No distinct PDN candidate port was resolved on {net}.",
            path="options.pdn_candidate_ports",
        )]

    z_matrices: List[np.ndarray] = []
    matrix_points: List[Dict[str, Any]] = []
    solve_quality: List[Dict[str, Any]] = []
    port_nodes = [int(item["node"]) for item in descriptors]
    for frequency_index, frequency in enumerate(frequencies):
        resistance = dense(solver.compute_resistance(float(frequency)))
        local_resistance = resistance[np.ix_(branch_indices, branch_indices)]
        branch_impedance = local_resistance + 1j * 2 * np.pi * float(frequency) * local_inductance
        omega = 2 * np.pi * float(frequency)
        node_admittance = omega * local_loss_coefficient + 1j * omega * local_capacitance
        try:
            matrix, quality = solve_shared_reference_port_matrix(
                mesh,
                node_ids,
                branch_indices,
                port_nodes,
                reference_node,
                branch_impedance,
                node_admittance,
                diagnostics=frequency_index in {0, len(frequencies) - 1},
            )
        except ValueError as exc:
            issues.append(ValidationIssue(
                "SPIKE-BE-PI-E-0102", "error",
                f"PDN multiport extraction failed on {net}: {exc}.",
                path="options.pdn_candidate_ports",
            ))
            return None, issues
        z_matrices.append(matrix)
        solve_quality.append(quality)
        matrix_points.append({
            "frequency_hz": float(frequency),
            "resistance_ohm": matrix.real.tolist(),
            "reactance_ohm": matrix.imag.tolist(),
        })

    reciprocity_errors = [
        float(np.linalg.norm(matrix - matrix.T) / max(np.linalg.norm(matrix), np.finfo(float).eps))
        for matrix in z_matrices
    ]
    passivity_samples = []
    for frequency, matrix in zip(frequencies, z_matrices):
        hermitian = (matrix + matrix.conjugate().T) / 2.0
        eigenvalues = np.linalg.eigvalsh(hermitian)
        minimum = float(eigenvalues[0])
        scale = max(float(np.max(np.abs(eigenvalues))), 1e-30)
        tolerance = max(1e-15, 1e-12 * scale)
        passivity_samples.append((float(frequency), minimum, tolerance))
    minimum_passivity_eigenvalue = min(item[1] for item in passivity_samples)
    failing_sample = next((item for item in passivity_samples if item[1] < -item[2]), None)
    if failing_sample is not None:
        frequency, minimum, tolerance = failing_sample
        issues.append(ValidationIssue(
            "PEEC_PDN_NONPASSIVE", "error",
            f"PDN impedance is nonpassive at {frequency:.9g} Hz: "
            f"minimum Hermitian eigenvalue {minimum:.9g} ohm is below "
            f"the {-tolerance:.9g} ohm tolerance. No projection was applied.",
            path="networks.pdn_multiports",
        ))
        return None, issues
    maximum_reciprocity_error = max(reciprocity_errors, default=0.0)
    reciprocal = maximum_reciprocity_error <= 1e-8
    source_result_id = spec.analysis_id or "peec-local"
    mesh_nodes = {node.id: node for node in mesh.nodes}
    candidates: List[Dict[str, Any]] = []
    for candidate_index, descriptor in enumerate(descriptors[1:], start=1):
        node = mesh_nodes[int(descriptor["node"])]
        candidates.append({
            "id": descriptor["id"],
            "location": {
                "position_mm": [node.x_mm, node.y_mm],
                "layer": node.layer,
                "mesh_node": node.id,
            },
            "source_result_id": source_result_id,
            "endpoint_reviewed": descriptor["endpoint_reviewed"],
            "reciprocal": reciprocal,
            "model_status": "approximate",
            "local_impedance": [
                impedance_point(frequency, matrix[candidate_index, candidate_index])
                for frequency, matrix in zip(frequencies, z_matrices)
            ],
            "transfer_impedance": [
                impedance_point(frequency, matrix[0, candidate_index])
                for frequency, matrix in zip(frequencies, z_matrices)
            ],
            "reverse_transfer_impedance": [
                impedance_point(frequency, matrix[candidate_index, 0])
                for frequency, matrix in zip(frequencies, z_matrices)
            ],
        })

    issues.append(ValidationIssue(
        "SPIKE-BE-PI-W-0101", "warning",
        "PDN candidate ports use the explicit source terminal as an ideal common reference; return-path impedance and multiconductor capacitance are not included.",
        path="networks.pdn_multiports",
        suggestion="Use this matrix for screening only until an explicit power/return extraction is independently correlated.",
        status="approximate",
    ))
    return {
        "contract": "spike/pdn-multiport/v1",
        "model_status": "approximate",
        "net": net,
        "source_result_id": source_result_id,
        "reference": {
            "kind": "ideal_common_reference_at_source_terminal",
            "mesh_node": reference_node,
        },
        "ports": descriptors,
        "observation_impedance": [
            impedance_point(frequency, matrix[0, 0])
            for frequency, matrix in zip(frequencies, z_matrices)
        ],
        "candidates": candidates,
        "z_parameters": matrix_points,
        "quality": {
            "maximum_reciprocity_error": maximum_reciprocity_error,
            "minimum_passivity_eigenvalue_ohm": minimum_passivity_eigenvalue,
            "maximum_relative_residual": max(
                float(item.get("relative_residual", 0.0)) for item in solve_quality
            ),
            "maximum_sampled_condition_number": max(
                (float(item["condition_number"]) for item in solve_quality if item.get("condition_number") is not None),
                default=None,
            ),
        },
        "validity": {
            "scope": "Shared-reference conductor-network Z-parameter extraction for PDN candidate screening.",
            "limits": [
                "The source terminal is an ideal common reference, not an extracted ground-return port.",
                "Capacitance and dielectric loss retain the single-reference quasi-static approximation.",
                "Candidate endpoint_reviewed records user review but does not promote extraction validity.",
            ],
        },
    }, issues
