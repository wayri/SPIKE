# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original experimental 3D P1 tetrahedral steady solid-thermal reference.

Independent derivation: test -div(k grad T)=q with affine shape functions,
integrate by parts, and use exact constant volume and triangular surface
moments. K_e=V B k B^T, f_e=V q/4. The face mass is A*(I+11^T)/12;
convection adds h*M and contact adds h*[[M,-M],[-M,M]]. Positive heat_flux
is INTO the solid; returned Fourier heat flux is -k grad T (W/m^2).

This implementation and tests are original, not adapted from vendor code or
examples. The weak-form identity and analytical slab/manufactured fields are
the method derivation and independent oracles. Constant cell conductivity,
fixed-temperature/flux/convection/ambient-radiation boundaries, exact matching contacts,
and a conforming straight-sided mesh only. Ambient Stefan-Boltzmann radiation is nonlinear. No transient, fluid,
EM, mechanical, automatic meshing, or production-qualification claims.
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import cg

from .assembly_tetra_radiation import solve_radiation
from .assembly_tetra_thermal_validation import (
    AssemblyTetraThermalError, MAX_CELLS, MAX_COMPARISONS, MAX_NODES,
    MAX_MATRIX_ENTRIES, MAX_WORKSPACE_BYTES, MAX_HIERARCHY_VISITS,
    require, validate_request,
)

REQUEST_CONTRACT = "spike/assembly-tetra-thermal-request/v1"
RESULT_CONTRACT = "spike/assembly-tetra-thermal-result/v1"


def run_assembly_tetra_thermal(request):
    """Validate completely before allocating/assembling the sparse system.

    Raises AssemblyTetraThermalError on unsupported input, unanchored thermal
    components, bounded iterative nonconvergence or nonfinite numerical output.
    No mutation of the request, mesh welding, or implicit thermal contact.
    """
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _run(request)
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        raise AssemblyTetraThermalError("Thermal input or operator is numerically unrepresentable.") from exc


def _run(request):
    data = validate_request(request)
    n = len(data["xyz"])
    capacity = data["matrix_entry_budget"]
    rows = np.empty(capacity, dtype=np.int32)
    columns = np.empty(capacity, dtype=np.int32)
    values = np.empty(capacity, dtype=float)
    used = 0
    load = np.zeros(n)
    source_power = 0.0

    def block(nodes, matrix):
        nonlocal used
        require(np.isfinite(matrix).all(), "Nonfinite assembled thermal coefficient.")
        count = len(nodes) ** 2
        require(used + count <= capacity, "Sparse matrix entry budget exceeded.")
        rows[used:used + count] = np.repeat(nodes, len(nodes))
        columns[used:used + count] = np.tile(nodes, len(nodes))
        values[used:used + count] = matrix.ravel()
        used += count

    for cell, (volume, gradients) in zip(data["cells"], data["geometry"]):
        nodes = cell["vertices"]
        block(nodes, volume * gradients @ data["tensors"][cell["material_id"]] @ gradients.T)
        power = volume * data["sources"].get(cell["id"], 0.0)
        source_power += power
        load[nodes] += power / 4
    face_template = (np.eye(3) + np.ones((3, 3))) / 12
    anchors = set(data["fixed"])
    for face, area, h, ambient in data["convection"]:
        block(face, h * area * face_template)
        load[list(face)] += h * area * ambient / 3
        anchors.update(face)
    for face, _, emissivity, _ in data["radiation"]:
        if emissivity > 0:
            anchors.update(face)
    prescribed_inward = 0.0
    for face, area, flux in data["fluxes"]:
        load[list(face)] += area * flux / 3
        prescribed_inward += area * flux
    for _, left, right, area, h in data["contacts"]:
        mass = area * h * face_template
        block(left + right, np.block([[mass, -mass], [-mass, mass]]))
    require(np.isfinite(load).all(), "Nonfinite assembled thermal load.")
    graph = coo_matrix((np.ones(used, dtype=bool),
                        (rows[:used], columns[:used])), shape=(n, n)).tocsr()
    component_count, labels = connected_components(graph, directed=False)
    require({int(labels[i]) for i in anchors} == set(range(component_count)),
            "Unanchored thermal component: supply temperature/convection/radiation or an explicit contact to an anchor.")
    del graph
    matrix = coo_matrix((values[:used], (rows[:used], columns[:used])), shape=(n, n)).tocsr()
    del rows, columns, values
    difference = matrix - matrix.T
    reciprocity_error = float(np.max(np.abs(difference.data), initial=0))
    matrix_scale = float(np.max(np.abs(matrix.data), initial=0))
    require(reciprocity_error <= 1e-12 * matrix_scale, "Thermal operator reciprocity failure.")
    fixed = np.array(sorted(data["fixed"]), dtype=int)
    free = np.array([i for i in range(n) if i not in data["fixed"]], dtype=int)
    temperatures = np.zeros(n)
    if len(fixed):
        temperatures[fixed] = [data["fixed"][int(i)] for i in fixed]
    iterations = 0
    positive_energy = True
    relative_residual = 0.0
    newton_iterations = 0
    radiation_power = np.zeros(n)
    if data["radiation"]:
        temperatures, radiation_power, newton_iterations, iterations, relative_residual = solve_radiation(
            matrix, load, fixed, free, temperatures, data["radiation"])
    elif len(free):
        operator = matrix[free][:, free]
        rhs = load[free] - matrix[free][:, fixed] @ temperatures[fixed]
        diagonal = operator.diagonal()
        require(np.isfinite(diagonal).all() and np.all(diagonal > 0), "Nonpositive thermal diagonal.")
        scaling = 1 / np.sqrt(diagonal)
        scaled = diags(scaling) @ operator @ diags(scaling)
        # SPD follows from positive material energies and anchored components;
        # these probes independently catch assembly defects, not an eigenproof.
        for probe in (np.ones(len(free)), np.linspace(-1, 1, len(free)),
                      np.where(np.arange(len(free)) % 2, -1., 1.)):
            if np.dot(probe, probe) > 0:
                positive_energy &= float(probe @ (scaled @ probe)) > 0
        require(positive_energy, "Positive-energy probe failed.")

        def count_iteration(_):
            nonlocal iterations
            iterations += 1

        solution, info = cg(scaled, scaling * rhs, rtol=1e-12, atol=0,
                            maxiter=min(100000, max(1000, 20 * len(free))), callback=count_iteration)
        require(info == 0 and np.isfinite(solution).all(), "Bounded thermal iteration did not converge.")
        temperatures[free] = scaling * solution
        residual = operator @ temperatures[free] - rhs
        relative_residual = float(np.linalg.norm(residual) / max(np.linalg.norm(rhs), 1e-300))
        require(relative_residual <= 1e-8, "Thermal free-node residual tolerance exceeded.")
    require(np.isfinite(temperatures).all() and np.min(temperatures) >= -1e-8,
            "Nonfinite or below-absolute-zero temperature result.")
    reactions = matrix @ temperatures + radiation_power - load
    reaction_inward = float(np.sum(reactions[fixed]))
    convection_outward = sum(area * h * (float(np.mean(temperatures[list(face)])) - ambient)
                             for face, area, h, ambient in data["convection"])
    radiation_outward = float(np.sum(radiation_power))
    balance = source_power + prescribed_inward + reaction_inward - convection_outward - radiation_outward
    power_scale = max(abs(source_power), abs(prescribed_inward), abs(reaction_inward),
                      abs(convection_outward), abs(radiation_outward), float(np.sum(np.abs(load))),
                      float(np.sum(np.abs(reactions[fixed]))), 1e-30)
    roundoff_w = 100 * np.finfo(float).eps * n * matrix_scale * float(np.max(np.abs(temperatures)))
    balance_tolerance = 1e-8 * power_scale + roundoff_w
    require(abs(balance) <= balance_tolerance, "Thermal global heat-balance tolerance exceeded.")
    cell_fluxes, volume_energy = [], 0.0
    for cell, (volume, gradients) in zip(data["cells"], data["geometry"]):
        gradient = gradients.T @ temperatures[cell["vertices"]]
        tensor = data["tensors"][cell["material_id"]]
        flux = -tensor @ gradient
        cell_fluxes.append({"cell_id": cell["id"], "heat_flux_w_m2": flux.tolist(), "volume_m3": volume})
        volume_energy += float(volume * gradient @ tensor @ gradient)
    contacts = []
    contact_energy = 0.0
    for sid, left, right, area, h in data["contacts"]:
        jump = temperatures[list(left)] - temperatures[list(right)]
        flow = float(area * h * np.mean(jump))
        contacts.append({"id": sid, "left_to_right_heat_w": flow,
                         "mean_temperature_jump_k": float(np.mean(jump))})
        contact_energy += float(area * h * jump @ face_template @ jump)
    require(np.isfinite(volume_energy + contact_energy) and volume_energy >= -1e-12 and contact_energy >= -1e-12,
            "Thermal dissipation is invalid.")
    return {"contract": RESULT_CONTRACT, "status": "experimental", "model_status": "experimental",
            "production_qualified": False, "mode": "steady_state", "temperature_units": "K",
            "node_temperatures_k": temperatures.tolist(), "cell_heat_flux_w_m2": cell_fluxes,
            "contacts": contacts, "reactions_w": {str(i): float(reactions[i]) for i in fixed},
            "heat_balance": {"source_w": float(source_power), "prescribed_flux_inward_w": float(prescribed_inward),
                             "temperature_reaction_inward_w": reaction_inward,
                             "radiation_outward_w": radiation_outward,
                             "convection_outward_w": float(convection_outward), "imbalance_w": float(balance),
                             "acceptance_tolerance_w": float(balance_tolerance)},
            "diagnostics": {"newton_iterations": newton_iterations, "free_relative_residual": relative_residual,
                            "free_max_residual_w": float(np.max(np.abs(reactions[free]), initial=0)),
                            "reciprocity_max_error_w_k": reciprocity_error,
                            "positive_energy_check": bool(positive_energy), "volume_gradient_energy_w_k": volume_energy,
                            "contact_jump_energy_w_k": contact_energy, "cg_iterations": iterations,
                            "max_element_jacobian_condition": data["max_condition"]},
            "boundary_evidence": {"omitted_faces_are_adiabatic": True,
                                  "omitted_adiabatic_faces": [list(f) for f in data["omitted"]],
                                  "heat_flux_sign": "positive_inward"},
            "resources": {"nodes": n, "tetrahedra": len(data["cells"]), "matrix_nonzeros": int(matrix.nnz),
                          "thermal_components": int(component_count), "geometry_comparisons": data["comparisons"],
                          "hanging_node_comparisons": data["hanging_comparisons"],
                          "matrix_assembly_entries": used,
                          "estimated_workspace_bytes": data["estimated_workspace_bytes"],
                          "limits": {"nodes": MAX_NODES, "tetrahedra": MAX_CELLS, "comparisons": MAX_COMPARISONS,
                                     "hierarchy_visits": MAX_HIERARCHY_VISITS,
                                     "matrix_entries": MAX_MATRIX_ENTRIES,
                                     "workspace_estimate_bytes": MAX_WORKSPACE_BYTES}},
            "limitations": ["experimental steady P1 solid conduction with prescribed ambient heat exchange", "constant cell conductivity",
                            "exact matched contacts with user-supplied h only", "omitted exterior faces are adiabatic",
                            "conforming straight-sided mesh required; no curved or nonmatching interfaces",
                            "no transient, enclosure radiosity, airflow, full-field EM, or production qualification"]}
