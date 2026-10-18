# SPDX-License-Identifier: Apache-2.0
"""Original bounded small-strain isotropic P1 tetrahedral thermoelasticity.

Engineering-strain order is xx,yy,zz,xy,yz,xz. Virtual work gives
K_e=V B.T C B and f_thermal=V B.T C epsilon_thermal. The latter is
alpha*(mean nodal T - Tref)*[1,1,1,0,0,0], constant within each cell.
Elastic energy is V/2*(B*u-epsilon_thermal).T C*(B*u-epsilon_thermal).
It is not equated to external work in the presence of thermal eigenstrain.
Shared retained-mesh validation supplies SI geometry and conforming ownership;
no welding, automatic constraints, contact, or mesh transfer is introduced.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

import numpy as np
from scipy.sparse import coo_matrix

from . import assembly_tetra_thermal_validation as mesh_validation

REQUEST_CONTRACT = "spike/assembly-tetra-structural-request/v1"
RESULT_CONTRACT = "spike/assembly-tetra-structural-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024


class AssemblyTetraStructuralError(ValueError):
    """Structured admission or numerical failure, without a partial result."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "ASSEMBLY_TETRA_STRUCTURAL_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise AssemblyTetraStructuralError(code, message)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _snapshot(request):
    size, chunks = 0, []
    for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(request):
        size += len(chunk.encode("utf-8"))
        _require(size <= 8*1024*1024, "Request exceeds 8 MiB", "resource_limit")
        chunks.append(chunk)
    return json.loads("".join(chunks)), size


def _norm(value):
    scale = float(np.max(np.abs(value), initial=0))
    result = scale*float(np.linalg.norm(value/scale)) if scale else 0.
    _require(math.isfinite(result), "Unrepresentable norm", "numerical_failure")
    return result


def _admit(request, size, poll):
    v = mesh_validation
    v.keys(request, ("contract", "mesh", "materials", "nodal_temperatures_k", "dirichlet", "nodal_forces_n", "context_digest"))
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported structural contract")
    _require(isinstance(request["context_digest"], str) and re.fullmatch(r"[0-9a-f]{64}", request["context_digest"]) is not None, "Context digest must be lowercase SHA256")
    mesh = request["mesh"]
    _require(isinstance(mesh, dict) and isinstance(mesh.get("vertices"), list) and isinstance(mesh.get("cells"), list), "Invalid retained mesh")
    n, cells = len(mesh["vertices"]), len(mesh["cells"])
    _require(4 <= n <= 256 and 1 <= cells <= 1024, "Structural limit is 256 nodes and 1024 tetrahedra", "resource_limit")
    materials = request["materials"]
    _require(isinstance(materials, list) and 1 <= len(materials) <= cells, "Invalid material count")
    properties = {}
    for material in materials:
        v.keys(material, ("id", "young_modulus_pa", "poisson_ratio", "thermal_expansion_per_k", "reference_temperature_k"))
        mid = v.identifier(material["id"])
        _require(mid not in properties, "Duplicate material ID")
        young = v.number(material["young_modulus_pa"], "Young modulus", positive=True)
        poisson = v.number(material["poisson_ratio"], "Poisson ratio")
        _require(-1 < poisson <= .49, "Poisson ratio must be in (-1, .49]; near-incompressible response unsupported")
        alpha = v.number(material["thermal_expansion_per_k"], "thermal expansion")
        reference = v.number(material["reference_temperature_k"], "reference temperature", positive=True)
        mu = young/(2*(1+poisson)); lam = young*poisson/((1+poisson)*(1-2*poisson))
        tensor = np.diag([2*mu]*3+[mu]*3); tensor[:3, :3] += lam
        eigen = np.linalg.eigvalsh(tensor)
        _require(np.isfinite(tensor).all() and eigen[0] > 0 and eigen[-1]/eigen[0] <= 1e12, "Unresolved isotropic material stiffness", "ill_conditioned")
        properties[mid] = tensor, alpha, reference
    _require(all(isinstance(c, dict) and isinstance(c.get("material_id"), str) for c in mesh["cells"]), "Invalid material assignment")
    _require(set(properties) == {c["material_id"] for c in mesh["cells"]}, "Materials must exactly cover used cell material IDs")
    constraints = request["dirichlet"]
    _require(isinstance(constraints, list) and len(constraints) <= 3*n, "Invalid displacement constraints")
    fixed = {}
    for item in constraints:
        v.keys(item, ("node_id", "component", "displacement_m"))
        node, component = item["node_id"], item["component"]
        _require(type(node) is int and 0 <= node < n and component in ("x", "y", "z"), "Invalid displacement degree of freedom")
        dof = 3*node+("x", "y", "z").index(component)
        _require(dof not in fixed, "Duplicate displacement constraint")
        fixed[dof] = v.number(item["displacement_m"], "displacement")
    free = 3*n-len(fixed)
    _require(free <= 192, "At most 192 free displacement degrees of freedom supported", "resource_limit")
    work = free**3+cells*12*12*6
    _require(work <= _MAX_WORK, "Structural assembly/solve work exceeds 100 million", "resource_limit")
    _require(3*size+cells*4096+n*2048+131072 <= _MAX_RESULT_BYTES, "Estimated structural result exceeds 16 MiB", "resource_limit")
    names = {str(i) for i in range(n)}
    temperature = request["nodal_temperatures_k"]
    if temperature is not None:
        _require(isinstance(temperature, dict) and set(temperature) == names, "Temperatures must cover every canonical node index")
        temperature = np.array([v.number(temperature[str(i)], "temperature", positive=True) for i in range(n)])
    forces = request["nodal_forces_n"]
    _require(isinstance(forces, dict) and set(forces) <= names, "Forces must map canonical node indices")
    load = np.zeros(3*n)
    for node, force in forces.items():
        _require(isinstance(force, list) and len(force) == 3, "Nodal force must have three components")
        load[3*int(node):3*int(node)+3] = [v.number(f, "force") for f in force]
    poll()
    data = v.validate_request({"contract": "spike/assembly-tetra-thermal-request/v1", "mesh": mesh,
                               "materials": [{"id": mid, "thermal_conductivity_w_mk": 1.} for mid in properties], "boundaries": []})
    poll()
    return data, properties, fixed, temperature, load, work


def _strain_matrix(gradients):
    matrix = np.zeros((6, 12))
    for i, (gx, gy, gz) in enumerate(gradients):
        matrix[:, 3*i:3*i+3] = [[gx, 0, 0], [0, gy, 0], [0, 0, gz],
                               [gy, gx, 0], [0, gz, gy], [gz, 0, gx]]
    return matrix


def run_assembly_tetra_structural(request, *, cancel_check=None):
    """Solve the bounded retained-mesh static displacement/eigenstrain problem."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise AssemblyTetraStructuralError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Structural solve cancelled", "cancelled")

    try:
        poll()
        frozen, size = _snapshot(request)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            data, properties, constraints, temperature, forces, work = _admit(frozen, size, poll)
            ndof = len(forces)
            rows, columns, values, elements = [], [], [], []
            thermal_load = np.zeros(ndof)
            for cell, (volume, gradients) in zip(data["cells"], data["geometry"]):
                poll()
                constitutive, alpha, reference = properties[cell["material_id"]]
                bmat = _strain_matrix(gradients)
                eigenstrain = np.zeros(6)
                if temperature is not None:
                    eigenstrain[:3] = alpha*(float(np.mean(temperature[cell["vertices"]]))-reference)
                dofs = np.array([3*node+c for node in cell["vertices"] for c in range(3)])
                stiffness = volume*(bmat.T@constitutive@bmat)
                thermal_load[dofs] += volume*(bmat.T@constitutive@eigenstrain)
                _require(np.isfinite(stiffness).all() and np.isfinite(thermal_load).all(), "Nonfinite structural assembly", "numerical_failure")
                rows.extend(np.repeat(dofs, 12)); columns.extend(np.tile(dofs, 12)); values.extend(stiffness.ravel())
                elements.append((cell, volume, bmat, constitutive, eigenstrain, dofs))
            matrix = coo_matrix((values, (rows, columns)), shape=(ndof, ndof)).tocsr()
            fixed = np.array(sorted(constraints), dtype=int)
            free = np.array([i for i in range(ndof) if i not in constraints], dtype=int)
            displacement = np.zeros(ndof)
            displacement[fixed] = [constraints[int(i)] for i in fixed]
            load = forces+thermal_load
            condition = 1.
            if len(free):
                operator = matrix[free][:, free].toarray()
                diagonal = np.diag(operator)
                _require(np.all(diagonal > 0), "Unconstrained or degenerate displacement mode", "ill_conditioned")
                scaling = 1/np.sqrt(diagonal)
                scaled = scaling[:, None]*operator*scaling[None, :]
                _require(_norm(scaled-scaled.T) <= 1e-12*_norm(scaled), "Structural reciprocity failure", "numerical_failure")
                eigen = np.linalg.eigvalsh(scaled)
                _require(eigen[0] > 0 and eigen[-1]/eigen[0] <= 1e12, "Rigid modes or ill-conditioned constrained stiffness", "ill_conditioned")
                condition = float(eigen[-1]/eigen[0])
                rhs = load[free]-matrix[free][:, fixed]@displacement[fixed]
                poll()
                displacement[free] = scaling*np.linalg.solve(scaled, scaling*rhs)
            poll()
            reactions = matrix@displacement-load
            scale = _norm(matrix.data)*_norm(displacement)+_norm(load)
            _require(math.isfinite(scale), "Unrepresentable equilibrium scale", "numerical_failure")
            residual = _norm(reactions[free])/scale if scale else _norm(reactions[free])
            _require(np.isfinite(displacement).all() and math.isfinite(residual) and residual <= 1e-10, "Free equilibrium residual exceeds tolerance", "numerical_failure")
            results, total_energy = [], 0.
            for cell, volume, bmat, constitutive, eigenstrain, dofs in elements:
                poll()
                strain = bmat@displacement[dofs]
                elastic = strain-eigenstrain
                stress = constitutive@elastic
                normal = stress[:3]
                vm = math.sqrt(.5*((normal[0]-normal[1])**2+(normal[1]-normal[2])**2+(normal[2]-normal[0])**2)+3*float(stress[3:]@stress[3:]))
                energy = float(.5*volume*(elastic@stress))
                _require(math.isfinite(energy) and energy >= 0 and np.isfinite(stress).all(), "Invalid elastic cell energy/stress", "numerical_failure")
                total_energy += energy
                results.append({"cell_id": cell["id"], "material_id": cell["material_id"], "source_object_ids": cell["source_object_ids"],
                                "volume_m3": volume, "total_strain": strain.tolist(), "thermal_strain": eigenstrain.tolist(),
                                "stress_pa": stress.tolist(), "von_mises_pa": vm, "elastic_energy_j": energy})
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": _digest(frozen), "mesh_digest": _digest(frozen["mesh"]), "context_digest": frozen["context_digest"],
                      **{key: frozen[key] for key in ("mesh", "materials", "nodal_temperatures_k", "dirichlet", "nodal_forces_n")},
                      "units": {"displacement": "m", "force": "N", "stress": "Pa", "temperature": "K"},
                      "node_displacements_m": displacement.reshape(-1, 3).tolist(),
                      "reactions_n": [{"node_id": int(i)//3, "component": ("x", "y", "z")[int(i)%3], "force_n": float(reactions[i])} for i in fixed],
                      "cells": results, "elastic_energy_j": total_energy,
                      "diagnostics": {"free_dofs": len(free), "equilibrated_condition": condition, "free_relative_residual": residual,
                                      "free_max_residual_n": float(np.max(np.abs(reactions[free]), initial=0)),
                                      "max_element_jacobian_condition": data["max_condition"], "estimated_work": work},
                      "limitations": ["Experimental static isotropic linear small-strain P1 tetrahedra; knowledgeable numerical review required before release",
                                      "Voigt order xx,yy,zz,xy,yz,xz; strain shear components are engineering shear, stress shear components are physical shear",
                                      "Thermal eigenstrain is constant per cell at mean supplied nodal temperature; null temperatures mean zero eigenstrain per material",
                                      "Elastic energy includes thermal eigenstrain and is not generally one half of external mechanical work",
                                      "Prescribed nodal forces/displacements only; omitted exterior faces are traction free; shared nodes imply perfect displacement continuity",
                                      "No inferred contact, mesh transfer, geometric nonlinearity, plasticity, fatigue, dynamics or near-incompressible formulation",
                                      "Conditioned bounded solve and synthetic references do not establish measured or production qualification",
                                      "Cancellation polls around mesh validation and linear algebra; those bounded calls have no internal cancellation callback"]}
            _require(len(_json(result)) <= _MAX_RESULT_BYTES, "Structural result exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except AssemblyTetraStructuralError:
        raise
    except mesh_validation.AssemblyTetraThermalError as error:
        raise AssemblyTetraStructuralError("invalid_request", str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError, RecursionError) as error:
        raise AssemblyTetraStructuralError("numerical_failure", f"Structural numerical failure: {error}") from error
