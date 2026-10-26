# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original experimental scalar DC P1 solve on a supplied retained tetra mesh.

Independent derivation: testing -div(sigma grad(phi))=0 with affine basis
functions and integrating by parts gives K_e=volume*sigma*B*B^T (siemens).
J=-sigma*grad(phi) (A/m2); q=sigma*|grad(phi)|^2 (W/m3). On matching
contact triangles M=area*(I+11^T)/12, and the conductance stamp is
g*[[M,-M],[-M,M]]. Thus contact power is g*jump^T*M*jump, not area*g
times the squared mean jump. The exact surface loss is split equally between
the two adjacent cells, returned separately from bulk Joule power. Consumers
must add allocation/volume to bulk q exactly once for thermal coupling.

No external implementation, examples or meshes were consulted. Analytical
resistors and independently generated variable-conductivity slabs are test
oracles. Only constant-per-cell nonnegative scalar DC conductivity, prescribed
triangle potentials, and exact matching contacts are admitted. Zero-sigma
cells contribute no operator or heat; exclusively insulating nodes have null
potential. Node identities never weld distinct retained bodies implicitly.

Numerical bounds: 5000 tets/10000 nodes, bounded geometry audits, diagonally
scaled CG and eigenvalue conditioning checks. The scaled free operator must
have estimated condition <=1e12. This is a numerical screening diagnostic,
not a rigorous forward-error certificate or product validation. Knowledgeable
human numerical review is required before release.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import ArpackNoConvergence, cg, eigsh

from .assembly_tetra_electrical_validation import AssemblyTetraElectricalError, REQUEST_CONTRACT, validate_request
from ...thermal_fluid.heat.assembly_tetra_thermal_validation import AssemblyTetraThermalError, require

RESULT_CONTRACT = "spike/assembly-tetra-electrical-result/v1"
FACE_TEMPLATE = (np.eye(3) + np.ones((3, 3))) / 12


def solve_assembly_tetra_electrical(request):
    """Return a conservative experimental result, or reject without mutation.

Terminal current is positive INTO the domain. At a node shared by several
same-voltage terminal triangles its reaction is split equally between their
IDs, avoiding duplicate counting. Individual triangle currents therefore
depend on this documented discrete partition; their sum is authoritative.
"""
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _solve(request)
    except AssemblyTetraThermalError as exc:
        raise AssemblyTetraElectricalError(str(exc)) from exc
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError, ArpackNoConvergence) as exc:
        raise AssemblyTetraElectricalError("Electrical arithmetic or conditioning check failed.") from exc


def _condition(operator):
    if operator.shape[0] <= 128:
        spectrum = np.linalg.eigvalsh(operator.toarray())
        smallest, largest = float(spectrum[0]), float(spectrum[-1])
    else:
        probe = np.random.default_rng(173).normal(size=operator.shape[0])
        smallest = float(eigsh(operator, k=1, which="SA", v0=probe, return_eigenvectors=False,
                               tol=1e-7, maxiter=2000)[0])
        largest = float(eigsh(operator, k=1, which="LA", v0=probe, return_eigenvectors=False,
                              tol=1e-7, maxiter=2000)[0])
    require(math.isfinite(smallest) and math.isfinite(largest) and smallest > 0 and
            largest > 0 and smallest >= largest * 1e-12,
            "Electrical operator is singular or exceeds conditioning budget.")
    return largest / smallest


def _solve(request):
    data = validate_request(request)
    n = len(data["xyz"])
    rows, columns, coefficients = [], [], []
    graph_rows, graph_columns, active = [], [], set()

    def block(nodes, matrix):
        require(np.isfinite(matrix).all(), "Nonfinite electrical operator.")
        active.update(nodes)
        for i, row in enumerate(nodes):
            for j, column in enumerate(nodes):
                rows.append(row)
                columns.append(column)
                coefficients.append(float(matrix[i, j]))
                graph_rows.append(row)
                graph_columns.append(column)

    for cell, (volume, gradients) in zip(data["cells"], data["geometry"]):
        sigma = data["conductivities"][cell["id"]]
        if sigma > 0:
            block(cell["vertices"], volume * sigma * (gradients @ gradients.T))
    for _, left, right, area, conductance in data["contacts"]:
        mass = area * conductance * FACE_TEMPLATE
        block(left + right, np.block([[mass, -mass], [-mass, mass]]))
    matrix = coo_matrix((coefficients, (rows, columns)), shape=(n, n)).tocsr()
    require(np.isfinite(matrix.data).all(), "Nonfinite electrical sparse accumulation.")
    active_nodes = np.array(sorted(active), dtype=int)
    graph = coo_matrix((np.ones(len(graph_rows)), (graph_rows, graph_columns)), shape=(n, n)).tocsr()
    component_count, local_labels = connected_components(graph[active_nodes][:, active_nodes], directed=False)
    labels = {int(node): int(label) for node, label in zip(active_nodes, local_labels)}
    require({labels[node] for node in data["fixed"]} == set(range(component_count)),
            "Unanchored conductive component: provide a terminal or explicit contact to one.")
    fixed = np.array(sorted(data["fixed"]), dtype=int)
    free = np.array([int(i) for i in active_nodes if i not in data["fixed"]], dtype=int)
    # Independent gauge origins remove large common-mode offsets from every
    # component's operator, gradients and source-work calculation.
    origins = {}
    for node in fixed:
        origins.setdefault(labels[int(node)], data["fixed"][int(node)])
    potential = np.zeros(n)
    for node in fixed:
        potential[node] = data["fixed"][int(node)] - origins[labels[int(node)]]
    iterations, relative_residual, condition = 0, 0., 1.
    if len(free):
        operator = matrix[free][:, free]
        rhs = -(matrix[free][:, fixed] @ potential[fixed])
        diagonal = operator.diagonal()
        require(np.isfinite(diagonal).all() and np.all(diagonal > 0), "Nonpositive electrical diagonal.")
        scaling = 1 / np.sqrt(diagonal)
        scaled = (diags(scaling) @ operator @ diags(scaling)).tocsr()
        require(np.isfinite(scaled.data).all() and np.isfinite(rhs).all(), "Nonfinite scaled electrical system.")
        condition = _condition(scaled)

        def count(_):
            nonlocal iterations
            iterations += 1

        solution, info = cg(scaled, scaling * rhs, rtol=1e-12, atol=0,
                            maxiter=min(100000, max(1000, 20 * len(free))), callback=count)
        require(info == 0 and np.isfinite(solution).all(), "Bounded electrical CG did not converge.")
        potential[free] = scaling * solution
        residual = operator @ potential[free] - rhs
        relative_residual = float(np.linalg.norm(residual) / max(np.linalg.norm(rhs), 1e-300))
        require(relative_residual <= 1e-8, "Electrical free-node residual tolerance exceeded.")
    require(np.isfinite(potential).all(), "Nonfinite electrical potential.")
    reactions = matrix @ potential
    require(np.isfinite(reactions).all(), "Nonfinite electrical reaction.")
    currents = {tid: 0. for tid, _, _ in data["terminals"]}
    for node, terminals in data["node_terminals"].items():
        for tid in terminals:
            currents[tid] += float(reactions[node]) / len(terminals)
    cell_q, cell_power, allocations, fields = {}, {}, {}, []
    for cell, (volume, gradients) in zip(data["cells"], data["geometry"]):
        cid, nodes = cell["id"], cell["vertices"]
        sigma = data["conductivities"][cid]
        gradient = gradients.T @ (potential[nodes] - potential[nodes[0]]) if sigma > 0 else np.zeros(3)
        q = float(sigma * np.dot(gradient, gradient))
        power = volume * q
        require(math.isfinite(q) and math.isfinite(power) and q >= 0, "Invalid bulk Joule heat.")
        cell_q[cid], cell_power[cid], allocations[cid] = q, power, 0.
        fields.append({"cell_id": cid, "volume_m3": volume, "current_density_a_m2": (-sigma * gradient).tolist()})
    contacts = []
    for sid, left, right, area, conductance in data["contacts"]:
        jump = potential[list(left)] - potential[list(right)]
        power = float(area * conductance * (jump @ FACE_TEMPLATE @ jump))
        current = float(area * conductance * np.mean(jump))
        require(math.isfinite(power) and math.isfinite(current) and power >= 0, "Invalid contact Joule heat.")
        lc, rc = data["face_cells"][tuple(sorted(left))], data["face_cells"][tuple(sorted(right))]
        allocations[lc] += power / 2
        allocations[rc] += power / 2
        origin = origins[labels[left[0]]]
        contacts.append({"id": sid, "power_w": power, "current_a": current,
                         "left_mean_voltage_v": float(np.mean(potential[list(left)])) + origin,
                         "right_mean_voltage_v": float(np.mean(potential[list(right)])) + origin,
                         "mean_voltage_jump_v": float(np.mean(jump)),
                         "loss_allocations_w": {lc: power / 2, rc: power / 2}})
    bulk_power = math.fsum(cell_power.values())
    contact_power = math.fsum(c["power_w"] for c in contacts)
    source_power = math.fsum(float(potential[i] * reactions[i]) for i in fixed)
    balance = source_power - bulk_power - contact_power
    power_scale = max(abs(source_power), bulk_power + contact_power, 1e-300)
    balance_tolerance = 1e-8 * power_scale
    require(math.isfinite(balance) and abs(balance) <= balance_tolerance,
            "Electrical power conservation tolerance exceeded.")
    terminal_current_scale = max(math.fsum(abs(v) for v in currents.values()), 1e-300)
    current_residual = math.fsum(currents.values())
    require(abs(current_residual) <= 1e-8 * terminal_current_scale, "Terminal current conservation failed.")
    absolute_potential = [float(potential[i]) + origins[labels[i]] if i in active else None for i in range(n)]
    require(all(v is None or math.isfinite(v) for v in absolute_potential), "Nonfinite restored electrical potential.")
    return {"contract": RESULT_CONTRACT, "status": "experimental", "model_status": "experimental",
            "production_qualified": False, "mode": "steady_dc", "node_potential_v": absolute_potential,
            "cell_joule_heat_w_m3": cell_q, "cell_power_w": cell_power,
            "cell_current_density_a_m2": fields, "terminal_currents_a": currents, "contacts": contacts,
            "contact_loss_allocations_w": allocations, "source_power_w": source_power,
            "joule_power_w": bulk_power, "contact_power_w": contact_power,
            "conservation_residual_w": balance,
            "diagnostics": {"free_relative_residual": relative_residual,
                            "free_max_residual_a": float(np.max(np.abs(reactions[free]), initial=0)),
                            "terminal_current_residual_a": current_residual, "cg_iterations": iterations,
                            "scaled_condition_estimate": condition, "power_acceptance_tolerance_w": balance_tolerance,
                            "max_element_jacobian_condition": data["max_condition"]},
            "resources": {"nodes": n, "active_nodes": len(active), "tetrahedra": len(data["cells"]),
                          "conductive_components": int(component_count), "matrix_nonzeros": int(matrix.nnz),
                          "geometry_comparisons": data["comparisons"], "hanging_node_comparisons": data["hanging_comparisons"]},
            "conventions": {"terminal_current": "positive_into_domain",
                            "contact_current": "positive_left_to_right",
                            "shared_terminal_nodes": "equal_reaction_partition_among_same_voltage_terminal_ids",
                            "contact_heat": "exact_surface_loss_half_to_each_adjacent_cell_separate_from_bulk",
                            "omitted_surfaces": "electrically_insulating"},
            "limitations": ["experimental scalar steady DC P1 conduction on supplied conforming tetrahedra",
                            "no tensor/AC/capacitance/inductance/automatic mesh or production qualification",
                            "constant conductivity per solve; nonlinear coupling belongs to the caller",
                            "exact matching coincident contacts only; supplied conductance is not inferred"]}
