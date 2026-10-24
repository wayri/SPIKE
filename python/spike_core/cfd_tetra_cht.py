# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded one-way tetrahedral creeping-flow/conjugate-energy composition.

This module adds no governing equation.  It composes the separately verified
CR/P0 Stokes and RT0/P0 energy kernels on one retained numerical tetra mesh.
The fluid-only flow mesh is an exact subset of that mesh; stationary solid
interfaces are explicit zero-velocity boundaries.  Accepted face velocity is
converted to integrated mass flow with the retained full-mesh face geometry.
"""
from collections.abc import Mapping
import copy
import math
import numbers

import numpy as np

from .cfd_tetra_energy import CONTRACT as ENERGY_CONTRACT, solve_cfd_tetra_energy
from .cfd_tetra_mesh import _admit_with_reuse, _resolve_admission
from .cfd_tetra_stokes import CONTRACT as STOKES_CONTRACT, solve_cfd_tetra_stokes
from .multiboard_identity import canonical_json_digest


CONTRACT = "spike/cfd-tetra-cht/v1"
RESULT_CONTRACT = "spike/cfd-tetra-cht-result/v1"
_INTERFACE_PATCH = "__cht_stationary_solid_interface__"
_TOP_LEVEL_KEYS = {"contract", "mesh", "identity", "flow", "energy"}
_FLOW_KEYS = {"dynamic_viscosity_pa_s", "density_kg_m3", "body_force_n_m3",
              "boundary_conditions", "controls"}
_ENERGY_KEYS = {"cell_material_ids", "materials", "source_w_m3",
                "reference_temperature_k", "boundaries"}
_IDENTITY_KEYS = {"source_id", "source_sha256", "mesh_sha256"}


class CfdTetraChtError(ValueError):
    """The composed workflow is unsupported, inconsistent, or unresolved."""


def cfd_tetra_cht_capabilities():
    """Return truthful catalog data for an owning worker/service adapter."""
    return {
        "available": True,
        "request_contract": CONTRACT,
        "result_contract": RESULT_CONTRACT,
        "model_status": "experimental",
        "geometry": "explicit_retained_si_tetra_mesh_with_explicit_cell_phases",
        "flow": "constant_property_creeping_cr_p0_broken_vector_laplacian",
        "energy": "steady_rt0_p0_conduction_shared_face_upwind_enthalpy",
        "coupling": "one_way_flow_to_energy_face_mass_flux",
        "fluid_solid_interface": "stationary_no_slip_perfect_thermal_contact",
        "inertia": False,
        "turbulence": False,
        "buoyancy_feedback": False,
        "general_cad_import": False,
        "production_qualified": False,
    }


def _require(condition, message):
    if not condition:
        raise CfdTetraChtError(message)


def _identity(raw, mesh):
    _require(isinstance(raw, Mapping) and set(raw) == _IDENTITY_KEYS,
             "identity must contain exactly source_id, source_sha256 and mesh_sha256")
    source_id = raw["source_id"]
    source_digest = raw["source_sha256"]
    mesh_digest = raw["mesh_sha256"]
    _require(isinstance(source_id, str) and 0 < len(source_id) <= 512
             and not any(ord(char) < 32 for char in source_id), "invalid source_id")
    for value, name in ((source_digest, "source_sha256"), (mesh_digest, "mesh_sha256")):
        _require(isinstance(value, str) and len(value) == 64
                 and all(char in "0123456789abcdef" for char in value), f"invalid {name}")
    actual = canonical_json_digest(mesh)
    _require(mesh_digest == actual, "declared mesh_sha256 does not match the retained mesh")
    return {"source_id": source_id, "source_sha256": source_digest,
            "mesh_sha256": actual, "source_authenticity_verified": False}


def _phases(energy, cell_count):
    _require(isinstance(energy, Mapping) and set(energy) == _ENERGY_KEYS,
             "energy must contain the exact composed-energy option set")
    ids, materials = energy["cell_material_ids"], energy["materials"]
    _require(isinstance(ids, list) and len(ids) == cell_count
             and all(isinstance(value, str) and 0 < len(value) <= 128 for value in ids),
             "cell_material_ids must cover every retained cell")
    _require(isinstance(materials, Mapping) and set(materials) == set(ids),
             "materials must cover the retained material IDs exactly")
    phases = {}
    for name, material in materials.items():
        _require(isinstance(material, Mapping)
                 and set(material) == {"phase", "conductivity_w_mk", "specific_heat_j_kgk"}
                 and material["phase"] in ("fluid", "solid"),
                 f"material {name!r} has an invalid phase contract")
        phases[name] = material["phase"]
    fluid = np.array([phases[name] == "fluid" for name in ids], dtype=bool)
    _require(np.any(fluid), "composed CHT requires at least one explicitly marked fluid cell")
    return fluid


def _full_body_force(raw, count, solid):
    array = np.asarray(raw)
    _require(array.shape == (count, 3) and array.dtype.kind in "iuf"
             and np.isfinite(array).all(),
             f"body_force_n_m3 must be a finite real array with shape ({count}, 3)")
    result = array.astype(float, copy=True)
    _require(np.all(result[solid] == 0.),
             "solid cell body_force_n_m3 must be exactly zero; solid flow is masked")
    return result


def _fluid_submesh(raw_mesh, admitted, fluid, cancel_check=None):
    """Return an exact fluid-cell subset and its stable full-mesh maps."""
    _require(_INTERFACE_PATCH not in raw_mesh["boundary_patches"],
             f"boundary patch name {_INTERFACE_PATCH!r} is reserved")
    fluid_cells = np.flatnonzero(fluid)
    selected_vertices = sorted({int(vertex) for cell in fluid_cells
                                for vertex in admitted["cells"][cell]})
    vertex_to_sub = {vertex: index for index, vertex in enumerate(selected_vertices)}
    cells = [[vertex_to_sub[int(vertex)] for vertex in admitted["cells"][cell]]
             for cell in fluid_cells]
    face_by_key = {tuple(sorted(map(int, face))): index
                   for index, face in enumerate(admitted["face_vertices"])}
    patch_faces = {}
    # Preserve each retained patch's declared triangle order so caller-supplied
    # face-average boundary arrays keep their exact geometric association.
    for name, triangles in raw_mesh["boundary_patches"].items():
        selected = []
        for triangle in triangles:
            face = face_by_key[tuple(sorted(triangle))]
            left, right = admitted["face_owners"][face]
            if right < 0 and fluid[left]:
                selected.append([vertex_to_sub[int(vertex)] for vertex in triangle])
        if selected:
            patch_faces[name] = selected
    interface = []
    for face, (left, right) in enumerate(admitted["face_owners"]):
        left_fluid = bool(fluid[left])
        right_fluid = right >= 0 and bool(fluid[right])
        if left_fluid == right_fluid:
            continue
        if right >= 0:
            vertices = [vertex_to_sub[int(vertex)] for vertex in admitted["face_vertices"][face]]
            interface.append(vertices)
    if interface:
        patch_faces[_INTERFACE_PATCH] = interface
    submesh = {
        "contract": "spike/cfd-tetra-mesh/v1",
        "units": "m",
        "vertices": [copy.deepcopy(raw_mesh["vertices"][vertex]) for vertex in selected_vertices],
        "cells": cells,
        "boundary_patches": patch_faces,
    }
    sub, sub_reuse = _admit_with_reuse(submesh, cancel_check)
    sub_face_to_full = []
    for face in sub["face_vertices"]:
        original = tuple(sorted(selected_vertices[int(vertex)] for vertex in face))
        _require(original in face_by_key, "derived fluid face is absent from the retained mesh")
        sub_face_to_full.append(face_by_key[original])
    return (submesh, sub, sub_reuse, fluid_cells,
            np.asarray(sub_face_to_full, dtype=np.int64), selected_vertices)


def _flow_request(flow, submesh, sub, fluid_cells, body):
    _require(isinstance(flow, Mapping) and set(flow) == _FLOW_KEYS,
             "flow must contain the exact composed-flow option set")
    conditions = flow["boundary_conditions"]
    _require(isinstance(conditions, Mapping), "flow boundary_conditions must be a mapping")
    external = set(submesh["boundary_patches"])-{_INTERFACE_PATCH}
    _require(set(conditions) == external,
             "flow boundary_conditions must cover exactly the retained exterior fluid patches")
    mapped = copy.deepcopy(dict(conditions))
    if _INTERFACE_PATCH in submesh["boundary_patches"]:
        count = len(submesh["boundary_patches"][_INTERFACE_PATCH])
        mapped[_INTERFACE_PATCH] = {
            "kind": "velocity_dirichlet",
            "face_average_velocity_m_s": np.zeros((count, 3)).tolist(),
        }
    return {
        "contract": STOKES_CONTRACT,
        "mesh": submesh,
        "dynamic_viscosity_pa_s": flow["dynamic_viscosity_pa_s"],
        "density_kg_m3": flow["density_kg_m3"],
        "body_force_n_m3": body[fluid_cells].tolist(),
        "boundary_conditions": mapped,
        "controls": copy.deepcopy(flow["controls"]),
    }


def _number(value, name):
    _require(isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_)),
             f"{name} must be a positive finite real number")
    value = float(value)
    _require(math.isfinite(value) and value > 0., f"{name} must be a positive finite real number")
    return value


def _mass_flux(admitted, sub, sub_face_to_full, flow_fields, density, fluid):
    velocities = np.asarray(flow_fields["face_average_velocity_m_s"], dtype=float)
    _require(velocities.shape == (len(sub["face_vertices"]), 3) and np.isfinite(velocities).all(),
             "Stokes result has an invalid face velocity field")
    mass = np.zeros(len(admitted["face_vertices"]))
    for sub_face, full_face in enumerate(sub_face_to_full):
        left, right = admitted["face_owners"][full_face]
        if fluid[left] and (right < 0 or fluid[right]):
            volume_flow = admitted["face_areas"][full_face] * float(
                np.dot(velocities[sub_face], admitted["face_normals"][full_face]))
            mass[full_face] = density * volume_flow
    solid_incident = np.array([
        (not fluid[left]) or (right >= 0 and not fluid[right])
        for left, right in admitted["face_owners"]], dtype=bool)
    mass[solid_incident] = 0.
    balance = np.array([math.fsum(float(sign*mass[face]) for sign, face in zip(signs, faces))
                        for signs, faces in zip(admitted["cell_face_signs"], admitted["cell_faces"])])
    throughput = np.sum(abs(mass[admitted["cell_faces"]]), axis=1)
    relative = np.zeros_like(balance)
    nonzero = throughput > 0.
    relative[nonzero] = abs(balance[nonzero])/throughput[nonzero]
    _require(np.all(balance[~nonzero] == 0.)
             and float(np.max(relative[fluid], initial=0.)) <= 1e-10,
             "mapped flow-to-energy mass balance exceeds 1e-10")
    _require(np.all(mass[solid_incident] == 0.), "solid-incident mass flux is not exactly zero")
    exterior = admitted["face_owners"][:, 1] < 0
    return mass, {
        "maximum_fluid_cell_mass_relative_defect": float(np.max(relative[fluid], initial=0.)),
        "maximum_fluid_cell_mass_imbalance_kg_s": float(np.max(abs(balance[fluid]), initial=0.)),
        "global_exterior_mass_imbalance_kg_s": math.fsum(float(value) for value in mass[exterior]),
        "maximum_solid_incident_mass_flow_kg_s": float(np.max(abs(mass[solid_incident]), initial=0.)),
        "flux_orientation": "outward_from_first_retained_mesh_face_owner",
    }


def _stage_failure(stage, result):
    status = result.get("status")
    if status == "cancelled":
        raise InterruptedError()
    issues = result.get("issues", [])
    detail = issues[0].get("message") if issues and isinstance(issues[0], Mapping) else "unknown failure"
    raise CfdTetraChtError(f"{stage} stage did not complete: {detail}")


def solve_cfd_tetra_cht(request, *, cancel_check=None, _mesh_reuse=None):
    """Run admitted Stokes, conservative flux mapping, then admitted energy."""
    result = {
        "contract": RESULT_CONTRACT,
        "model_status": "experimental",
        "research_only": True,
        "production_qualified": False,
        "scope": "one_way_constant_property_creeping_flow_to_steady_conjugate_sensible_energy",
        "limitations": [
            "Explicit retained numerical tetrahedra and caller-declared source identity only.",
            "Steady creeping flow uses broken vector-Laplacian pseudo-traction, not physical symmetric stress.",
            "Stationary no-slip fluid-solid interfaces and perfect thermal contact; no contact resistance.",
            "One-way constant-property coupling; no inertia, turbulence, buoyancy feedback or radiation.",
            "No general CAD fluid-domain extraction, interface inference or production qualification.",
        ],
    }
    try:
        if cancel_check and cancel_check():
            raise InterruptedError()
        _require(isinstance(request, Mapping) and set(request) == _TOP_LEVEL_KEYS
                 and request["contract"] == CONTRACT, "invalid composed tetra CHT contract or fields")
        raw_mesh = request["mesh"]
        provenance = _identity(request["identity"], raw_mesh)
        if _mesh_reuse is None:
            admitted, retained_reuse = _admit_with_reuse(raw_mesh, cancel_check)
        else:
            admitted = _resolve_admission(raw_mesh, _mesh_reuse, cancel_check)
            retained_reuse = _mesh_reuse
        fluid = _phases(request["energy"], len(admitted["cells"]))
        solid = ~fluid
        flow = request["flow"]
        _require(isinstance(flow, Mapping), "flow must be a mapping")
        body = _full_body_force(flow.get("body_force_n_m3"), len(fluid), solid)
        submesh, sub, sub_reuse, fluid_cells, sub_face_to_full, selected_vertices = _fluid_submesh(
            raw_mesh, admitted, fluid, cancel_check)
        flow_request = _flow_request(flow, submesh, sub, fluid_cells, body)
        flow_result = solve_cfd_tetra_stokes(
            flow_request, cancel_check=cancel_check,
            _mesh_reuse=sub_reuse)
        if flow_result.get("status") != "completed":
            _stage_failure("flow", flow_result)
        density = _number(flow["density_kg_m3"], "density_kg_m3")
        mass, coupling = _mass_flux(admitted, sub, sub_face_to_full,
                                    flow_result["fields"], density, fluid)
        energy_request = {"contract": ENERGY_CONTRACT, "mesh": raw_mesh,
                          "face_mass_flow_kg_s": mass.tolist(), **copy.deepcopy(dict(request["energy"]))}
        energy_result = solve_cfd_tetra_energy(
            energy_request, cancel_check=cancel_check,
            _mesh_reuse=retained_reuse)
        if energy_result.get("status") != "completed":
            _stage_failure("energy", energy_result)
        if cancel_check and cancel_check():
            raise InterruptedError()
        provenance.update({
            "request_sha256": canonical_json_digest(request),
            "fluid_submesh_sha256": canonical_json_digest(submesh),
            "fluid_submesh_is_exact_retained_cell_subset": True,
        })
        result.update(status="completed", provenance=provenance, diagnostics={
            "flow": flow_result["diagnostics"],
            "energy": energy_result["diagnostics"],
            "coupling": {**coupling, "retained_cells": len(fluid),
                         "fluid_cells": int(np.count_nonzero(fluid)),
                         "solid_cells": int(np.count_nonzero(solid)),
                         "retained_faces": len(admitted["face_vertices"]),
                         "fluid_submesh_faces": len(sub["face_vertices"])},
        }, fields={
            "flow": flow_result["fields"],
            "energy": energy_result["fields"],
            "face_mass_flow_kg_s": mass.tolist(),
            "fluid_cell_mask": fluid.tolist(),
            "fluid_submesh_cell_to_retained_cell": fluid_cells.tolist(),
            "fluid_submesh_face_to_retained_face": sub_face_to_full.tolist(),
            "fluid_submesh_vertex_to_retained_vertex": selected_vertices,
        })
    except InterruptedError:
        result.update(status="cancelled", issues=[{
            "code": "CANCELLED", "message": "Composed tetra CHT cancelled"}])
    except (ValueError, TypeError, ArithmeticError, RuntimeError, KeyError) as exc:
        result.update(status="blocked", issues=[{
            "code": "CFD_TETRA_CHT_REJECTED", "message": str(exc)}])
    return result


__all__ = ["CONTRACT", "RESULT_CONTRACT", "CfdTetraChtError",
           "cfd_tetra_cht_capabilities", "solve_cfd_tetra_cht"]
