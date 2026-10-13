# SPDX-License-Identifier: Apache-2.0
"""Experimental 3D P1 electrostatics on a retained finite dielectric mesh.

Original derivation (no external implementation consulted): for affine basis N,
weak -div(epsilon grad(phi))=0 gives K_e=volume*B*epsilon*B.T in farads.
Dirichlet electrode reactions are free conductor charges in coulombs. Unit
electrode solutions P yield the Maxwell matrix C = P.T K P; therefore
V.T C V / 2 equals integrated epsilon-weighted field energy for every V.
Unassigned outer surfaces have exactly zero normal displacement, not an open
or infinite boundary. No conductor, material, ground, or mesh is inferred.

The existing retained-tetra validator supplies SI gradients and audits for
orientation, intersections, ownership and hanging nodes. Its scalar/tensor
coefficient validator is reused by an internal property-name translation;
no temperature values, heat sources, thermal solve or thermal boundary enters
the electrostatic model. Mesh limits are stricter here: 10000 nodes/5000 cells,
16 electrodes including the explicit reference, 8 MiB JSON input.

P1 field accuracy depends on geometry and mesh refinement. Ideal parallel
plates are an exact affine witness, not arbitrary-PCB/fringing qualification.
Conductor sheets are zero-thickness equipotential mesh-face vertex groups.
Human numerical review remains necessary before release.
"""
from __future__ import annotations

from hashlib import sha256
import itertools
import json

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import ArpackNoConvergence, cg

from .assembly_tetra_electrical import _condition
from .assembly_tetra_thermal_validation import (
    AssemblyTetraThermalError, _hanging_node_audit, validate_request as validate_tetra_geometry,
)

REQUEST_CONTRACT = "spike/pdn-electrostatic-request/v1"
RESULT_CONTRACT = "spike/pdn-electrostatic-result/v1"


class PdnElectrostaticError(ValueError):
    """Malformed, unsupported or numerically inadmissible finite-volume model."""


def _require(condition, message):
    if not condition:
        raise PdnElectrostaticError(message)


def _keys(value, fields):
    _require(isinstance(value, dict) and set(value) == set(fields), "Unknown or missing electrostatic fields")


def _name(value):
    _require(isinstance(value, str) and 0 < len(value) <= 80 and value.strip()
             and not any(ord(c) < 32 or ord(c) == 127 for c in value), "Invalid electrode or material identity")
    return value


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(request):
            size += len(chunk.encode())
            _require(size <= 8 * 1024 * 1024, "Electrostatic input exceeds 8 MiB")
            chunks.append(chunk)
        return json.loads("".join(chunks))
    except (ValueError, TypeError, RecursionError, OverflowError) as error:
        raise PdnElectrostaticError(f"Invalid bounded electrostatic JSON: {error}") from error


def _admit(request):
    _keys(request, {"contract", "mesh", "materials", "electrodes", "reference_electrode",
                    "outer_boundary", "context_digest"})
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported electrostatic contract")
    _require(request["outer_boundary"] == "insulating", "Explicit finite insulating outer boundary required")
    context = request["context_digest"]
    _require(isinstance(context, str) and len(context) == 64 and all(c in "0123456789abcdef" for c in context),
             "Context digest must be a lowercase SHA-256")
    mesh = request["mesh"]
    _require(isinstance(mesh, dict) and isinstance(mesh.get("vertices"), list)
             and isinstance(mesh.get("cells"), list), "Retained dielectric mesh required")
    _require(4 <= len(mesh["vertices"]) <= 10000 and 1 <= len(mesh["cells"]) <= 5000,
             "Electrostatic mesh exceeds 10000 nodes/5000 cells")
    materials = request["materials"]
    _require(isinstance(materials, list) and 1 <= len(materials) <= 5000, "Invalid material count")
    translated = []
    for material in materials:
        _keys(material, {"id", "permittivity_f_m"})
        _name(material["id"])
        translated.append({"id": material["id"], "thermal_conductivity_w_mk": material["permittivity_f_m"]})
    # Geometry and positive scalar/tensor coefficient validation only. No
    # thermal boundary is used to encode an electrical constraint.
    data = validate_tetra_geometry({"contract": "spike/assembly-tetra-thermal-request/v1",
                                   "mesh": mesh, "materials": translated, "boundaries": []})
    _require(len({tuple(point) for point in mesh["vertices"]}) == len(mesh["vertices"]),
             "Coincident separately indexed dielectric vertices require a conforming interface")
    # Thermal ownership permits distinct bodies. Electrostatics here has no
    # contact/interpolation law, so audit interfaces across every source owner.
    _hanging_node_audit(data["xyz"], data["cells"], data["geometry"],
                        [{"dielectric-domain"} for _ in data["cells"]],
                        [{"dielectric-domain"} for _ in data["xyz"]])
    face_owners = {}
    for index, cell in enumerate(data["cells"]):
        for face in itertools.combinations(cell["vertices"], 3):
            face_owners.setdefault(tuple(sorted(face)), []).append(index)
    adjacent = [(owners[0], owners[1]) for owners in face_owners.values() if len(owners) == 2]
    cell_graph = coo_matrix((np.ones(len(adjacent)),
                            ([a for a, _ in adjacent], [b for _, b in adjacent])),
                           shape=(len(data["cells"]), len(data["cells"]))).tocsr()
    _require(connected_components(cell_graph, directed=False, return_labels=False) == 1,
             "Dielectric volume must be face-connected, not touching only at points or edges")
    electrodes = request["electrodes"]
    _require(isinstance(electrodes, list) and 2 <= len(electrodes) <= 16,
             "Provide 2..16 explicit electrodes including reference")
    used, ids, names = set(), set(), set()
    faces = {tuple(sorted(face)) for cell in data["cells"] for face in itertools.combinations(cell["vertices"], 3)}
    for electrode in electrodes:
        _keys(electrode, {"id", "node", "vertices"})
        identity, node = _name(electrode["id"]), _name(electrode["node"])
        _require(identity not in ids and node not in names, "Duplicate electrode or circuit node")
        ids.add(identity)
        names.add(node)
        vertices = electrode["vertices"]
        _require(isinstance(vertices, list) and 3 <= len(vertices) <= len(data["xyz"])
                 and all(type(v) is int and 0 <= v < len(data["xyz"]) for v in vertices),
                 "Electrode requires explicit retained vertex indices")
        selection = set(vertices)
        _require(len(selection) == len(vertices) and not selection & used, "Overlapping or repeated electrode vertices")
        electrode_faces = [face for face in faces if set(face) <= selection]
        _require(electrode_faces and set().union(*(set(f) for f in electrode_faces)) == selection,
                 "Electrode vertex group must cover complete retained mesh faces")
        _require(not any(set(cell["vertices"]) <= selection for cell in data["cells"]),
                 "Electrodes must be sheets, not an entire dielectric cell")
        used.update(selection)
    _require(isinstance(request["reference_electrode"], str) and request["reference_electrode"] in ids,
             "Explicit reference electrode is missing")
    return data


def _electrode_reactions(matrix, potentials, electrodes):
    """Sum each disjoint electrode's nodal reaction exactly once."""
    reactions = matrix @ potentials
    return np.array([np.sum(reactions[e["vertices"], :], axis=0) for e in electrodes]), reactions


def extract_pdn_electrostatic(request):
    """Compute reduced Maxwell C in SI farads for explicitly selected terminals.

    Result node order excludes the reference. Each basis column sets its
    signal electrode to 1 V and every other electrode to 0 V. Charge is
    positive into the dielectric; all electrode reactions, including ground,
    are retained. No symmetry repair, negative-energy clipping or diagonal
    replacement is performed. The result is experimental, never production
    qualified merely because solver/energy gates pass.
    """
    frozen = _snapshot(request)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _extract(frozen)
    except PdnElectrostaticError:
        raise
    except (AssemblyTetraThermalError, FloatingPointError, OverflowError,
            np.linalg.LinAlgError, ArpackNoConvergence) as error:
        raise PdnElectrostaticError(f"Electrostatic geometry or numerical admission failed: {error}") from error


def _extract(request):
    data = _admit(request)
    n = len(data["xyz"])
    electrodes = request["electrodes"]
    reference = next(e for e in electrodes if e["id"] == request["reference_electrode"])
    signals = [e for e in electrodes if e is not reference]
    rows, columns, coefficients = [], [], []
    for cell, (volume, gradients) in zip(data["cells"], data["geometry"]):
        local = volume * gradients @ data["tensors"][cell["material_id"]] @ gradients.T
        for i, row in enumerate(cell["vertices"]):
            for j, column in enumerate(cell["vertices"]):
                rows.append(row)
                columns.append(column)
                coefficients.append(float(local[i, j]))
    matrix = coo_matrix((coefficients, (rows, columns)), shape=(n, n)).tocsr()
    graph = coo_matrix((np.ones(len(rows)), (rows, columns)), shape=(n, n)).tocsr()
    _require(connected_components(graph, directed=False, return_labels=False) == 1,
             "Dielectric mesh must be one connected conforming domain")
    _require(np.isfinite(matrix.data).all(), "Nonfinite permittivity operator")
    fixed = np.array(sorted({v for e in electrodes for v in e["vertices"]}), dtype=int)
    free = np.setdiff1d(np.arange(n), fixed)
    potentials = np.zeros((n, len(signals)))
    for index, electrode in enumerate(signals):
        potentials[electrode["vertices"], index] = 1.0
    condition, residuals, iterations = 1.0, [], []
    if len(free):
        operator = matrix[free][:, free]
        diagonal = operator.diagonal()
        _require(np.all(diagonal > 0), "Nonpositive free electrostatic diagonal")
        scaling = 1 / np.sqrt(diagonal)
        scaled = (diags(scaling) @ operator @ diags(scaling)).tocsr()
        condition = _condition(scaled)
        rhs = -(matrix[free][:, fixed] @ potentials[fixed])
        for index in range(len(signals)):
            count = [0]
            def record(_):
                count[0] += 1
            solution, status = cg(scaled, scaling * rhs[:, index], rtol=1e-12, atol=0,
                                  maxiter=min(100000, max(1000, 20 * len(free))), callback=record)
            _require(status == 0 and np.isfinite(solution).all(), "Electrostatic CG did not converge")
            potentials[free, index] = scaling * solution
            residual = float(np.linalg.norm(operator @ potentials[free, index] - rhs[:, index]) /
                             max(float(np.linalg.norm(rhs[:, index])), 1e-300))
            _require(residual <= 1e-8, "Electrostatic free-node residual exceeded tolerance")
            residuals.append(residual)
            iterations.append(count[0])
    charges, reactions = _electrode_reactions(matrix, potentials, electrodes)
    _require(np.isfinite(charges).all() and np.isfinite(reactions).all(), "Nonfinite electrode reaction")
    signal_rows = [electrodes.index(e) for e in signals]
    capacitance = charges[signal_rows, :]
    # Independently integrate field-energy bilinear form from per-cell fields,
    # not merely a repeat of electrode charge summation.
    energy_matrix = np.zeros_like(capacitance)
    for cell, (volume, gradients) in zip(data["cells"], data["geometry"]):
        fields = gradients.T @ potentials[cell["vertices"], :]
        energy_matrix += volume * fields.T @ data["tensors"][cell["material_id"]] @ fields
    scale = max(float(np.linalg.norm(energy_matrix)), 1e-300)
    energy_error = float(np.linalg.norm(capacitance - energy_matrix) / scale)
    reciprocity = float(np.linalg.norm(capacitance - capacitance.T) / scale)
    charge_error = float(np.max(np.abs(np.sum(charges, axis=0))) /
                         max(float(np.max(np.sum(np.abs(charges), axis=0))), 1e-300))
    _require(energy_error <= 1e-8, "Electrode charge and integrated field energy disagree")
    _require(reciprocity <= 1e-8, "Maxwell reciprocity check failed")
    _require(charge_error <= 1e-8, "Electrode charge conservation failed")
    eigenvalues = np.linalg.eigvalsh(capacitance / scale)
    _require(eigenvalues[0] > 0 and eigenvalues[0] >= eigenvalues[-1] * 1e-12,
             "Reduced Maxwell matrix has nonpositive or ill-conditioned energy")
    mesh_digest = _digest(request["mesh"])
    lineage = []
    for electrode in electrodes:
        selection = set(electrode["vertices"])
        sources = sorted({source for cell in data["cells"] if selection & set(cell["vertices"])
                          for source in cell["source_object_ids"]})
        lineage.append({"id": electrode["id"], "node": electrode["node"],
                        "vertices": electrode["vertices"], "dielectric_source_object_ids": sources})
    return {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
            "model": "retained_dielectric_p1_electrostatics", "nodes": [e["node"] for e in signals],
            "matrix_f": capacitance.tolist(), "reference_electrode": reference,
            "electrodes": electrodes, "outer_boundary": "insulating",
            "electrode_lineage": lineage,
            "context_digest": request["context_digest"], "mesh_digest": mesh_digest,
            "input_digest": _digest(request), "basis_node_potential_v": potentials.tolist(),
            "electrode_basis_charge_c": {e["id"]: charges[i].tolist() for i, e in enumerate(electrodes)},
            "field_energy_matrix_f": energy_matrix.tolist(),
            "mesh_lineage": request["mesh"]["object_map"],
            "diagnostics": {"max_free_relative_residual": max(residuals, default=0.),
                            "scaled_free_condition_estimate": condition, "cg_iterations": iterations,
                            "relative_charge_energy_error": energy_error, "relative_reciprocity_error": reciprocity,
                            "relative_charge_balance_error": charge_error,
                            "reduced_matrix_condition": float(eigenvalues[-1] / eigenvalues[0]),
                            "max_element_jacobian_condition": data["max_condition"],
                            "nodes": n, "cells": len(data["cells"]), "free_nodes": len(free)},
            "limitations": ["Finite explicitly meshed dielectric only; unassigned surfaces have zero normal displacement",
                            "P1 fields require geometry-specific refinement evidence; no infinite/open boundary",
                            "No automatic PCB geometry, conductor identification, fringing qualification or material dispersion",
                            "Zero-thickness equipotential electrode sheets; no conductor thickness or resistive electrode model",
                            "Analytical plate witnesses do not establish arbitrary-PCB accuracy or release qualification"]}
