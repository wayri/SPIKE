# SPDX-License-Identifier: Apache-2.0
"""Bounded 3-D enclosure flow and conjugate sensible-energy composition.

Coarse uniform MAC momentum and nested rectilinear thermal refinement are
distinct discretizations. No turbulence, rotor model, CAD fit or local momentum
AMR is inferred from the thermal mesh or a converged algebraic residual.
"""
import hashlib
import json
import math
import re

import numpy as np

from .enclosure_energy import FACES, solve_enclosure_energy
from .enclosure_refinement import build_enclosure_grid, prolong_mac_fluxes

REQUEST = "spike/enclosure-cht-request/v1"
RESULT = "spike/enclosure-cht-result/v1"
MAX_BYTES = 8*1024**2


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("Enclosure fields do not match the declared contract")


def _number(value, name, low, high):
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError(f"{name} outside [{low},{high}]")
    return float(value)


def _snapshot(value, *, label="request"):
    count, chunks = 0, []
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(value):
        count += len(chunk.encode("utf-8"))
        if count > MAX_BYTES:
            raise ValueError(f"Enclosure {label} exceeds 8 MiB")
        chunks.append(chunk)
    encoded = "".join(chunks)
    return json.loads(encoded), hashlib.sha256(encoded.encode()).hexdigest()


def _array(value, shape, name):
    _nested(value, shape, lambda item: type(item) in (int, float), name)
    raw = np.asarray(value)
    if raw.shape != tuple(shape) or raw.dtype.kind not in "iuf":
        raise ValueError(f"{name} requires numeric shape {shape}")
    result = raw.astype(float)
    if not np.isfinite(result).all() or np.max(np.abs(result), initial=0.) > 1e12:
        raise ValueError(f"{name} must be finite within +/-1e12")
    return result


def _nested(value, shape, predicate, name):
    if not shape:
        if not predicate(value):
            raise ValueError(f"Invalid {name} element type")
        return
    if not isinstance(value, list) or len(value) != shape[0]:
        raise ValueError(f"Invalid {name} array shape")
    for item in value:
        _nested(item, shape[1:], predicate, name)


def _admit(request):
    _keys(request, ("contract", "grid", "materials", "material_ids", "flow", "boundaries",
                    "heat_sources_w_m3", "study"))
    if request["contract"] != REQUEST:
        raise ValueError(f"Expected {REQUEST}")
    request, identity = _snapshot(request)
    grid = build_enclosure_grid(request["grid"])
    coarse_shape = grid["coarse_shape"]
    _nested(request["material_ids"], coarse_shape, lambda item: isinstance(item, str), "material IDs")
    raw_ids = np.asarray(request["material_ids"])
    if raw_ids.shape != coarse_shape or raw_ids.dtype.kind not in "US":
        raise ValueError("material_ids must name each coarse cell")
    materials = request["materials"]
    if not isinstance(materials, list) or not 1 <= len(materials) <= 64:
        raise ValueError("Expected 1..64 constant materials")
    by_id, fluid_ids = {}, []
    for material in materials:
        if not isinstance(material, dict):
            raise ValueError("Material must be an object")
        phase = material.get("phase")
        base = {"id", "phase", "density_kg_m3", "specific_heat_j_kgk", "conductivity_w_mk"}
        _keys(material, base | ({"dynamic_viscosity_pa_s"} if phase == "fluid" else set()))
        mid = material["id"]
        if not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", mid) or mid in by_id:
            raise ValueError("Invalid or duplicate material ID")
        if phase not in ("fluid", "solid"):
            raise ValueError("Material phase must be fluid or solid")
        for key, low, high in (("density_kg_m3", 1e-6, 1e6), ("specific_heat_j_kgk", 1e-6, 1e7),
                              ("conductivity_w_mk", 1e-9, 1e5)):
            _number(material[key], key, low, high)
        if phase == "fluid":
            fluid_ids.append(mid)
            _number(material["dynamic_viscosity_pa_s"], "viscosity", 1e-12, 1e4)
        by_id[mid] = material
    if len(fluid_ids) != 1 or set(raw_ids.ravel()) != set(by_id):
        raise ValueError("Exactly one fluid material and exact used material coverage required")
    fluid_id = fluid_ids[0]
    mask = raw_ids == fluid_id
    flow = request["flow"]
    if not isinstance(flow, dict) or flow.get("model") not in ("creeping", "laminar_inertial"):
        raise ValueError("Explicit creeping or laminar_inertial flow model required")
    _keys(flow, {"model", "body_force_n_m3"} |
          ({"nonlinear_controls"} if flow["model"] == "laminar_inertial" else set()))
    force = _array(flow["body_force_n_m3"], (*coarse_shape, 3), "body force")
    if np.any(force[~mask] != 0.):
        raise ValueError("Body force on solid cells is not an admitted fluid drive")
    heat = _array(request["heat_sources_w_m3"], coarse_shape, "heat generation")
    boundaries = request["boundaries"]
    _keys(boundaries, FACES)
    anchored = False
    for bc in boundaries.values():
        if not isinstance(bc, dict):
            raise ValueError("Boundary must be an object")
        kind = bc.get("type")
        options = {"adiabatic": {"type"}, "temperature": {"type", "temperature_k"},
            "heat_flux": {"type", "inward_heat_flux_w_m2"},
            "convection": {"type", "ambient_temperature_k", "heat_transfer_coefficient_w_m2k"}}
        if kind not in options:
            raise ValueError("Unsupported enclosure thermal boundary")
        _keys(bc, options[kind])
        for key, value in bc.items():
            if key != "type":
                _number(value, key, -1e12 if key == "inward_heat_flux_w_m2" else 1e-12,
                        1e12 if key == "inward_heat_flux_w_m2" else 10000 if "temperature" in key else 1e9)
        anchored |= kind in ("temperature", "convection")
    study = request["study"]
    if not isinstance(study, dict) or study.get("type") not in ("steady", "transient"):
        raise ValueError("Study requires steady or transient")
    if study["type"] == "steady":
        _keys(study, {"type"})
        if not anchored:
            raise ValueError("Steady closed energy needs a supplied temperature/convection anchor")
    else:
        _keys(study, {"type", "time_step_s", "steps", "initial_temperature_k", "output_stride"})
        _number(study["time_step_s"], "time_step_s", 1e-9, 1e9)
        _number(study["initial_temperature_k"], "initial_temperature_k", 1., 10000.)
        for key in ("steps", "output_stride"):
            if type(study[key]) is not int or not 1 <= study[key] <= 256:
                raise ValueError("steps/output_stride must be integers in [1,256]")
        count = math.prod(grid["shape"])
        frames = study["steps"]//study["output_stride"] + bool(study["steps"] % study["output_stride"])
        if count*study["steps"] > 1_000_000 or count*frames > 200_000:
            raise ValueError("Thermal cell-step or saved-value budget exceeded")
    return request, identity, grid, raw_ids, mask, force, heat, by_id, by_id[fluid_id]


def _flow(request, grid, mask, force, fluid, cancel_check):
    shape = grid["coarse_shape"]
    args = {"shape": list(shape), "spacing_m": request["grid"]["spacing_m"],
        "fluid_mask": mask.tolist(), "body_force_n_m3": force.tolist(),
        "dynamic_viscosity_pa_s": fluid["dynamic_viscosity_pa_s"], "density_kg_m3": fluid["density_kg_m3"]}
    if request["flow"]["model"] == "creeping":
        from .enclosure_stokes import solve_enclosure_stokes, CONTRACT
        return solve_enclosure_stokes({"contract": CONTRACT, **args}, cancel_check=cancel_check)
    from .enclosure_laminar import solve_enclosure_laminar, CONTRACT
    # A full rectangular fluid region may have conducting walls outside it.
    # Extract exactly that region; never fill an obstacle or drop a fluid cell.
    indices = np.argwhere(mask)
    lower, upper = indices.min(axis=0), indices.max(axis=0)+1
    bounds = tuple(slice(int(lo), int(hi)) for lo, hi in zip(lower, upper))
    inside = mask[bounds]
    if not inside.all() or int(inside.sum()) != int(mask.sum()):
        raise ValueError("Inertial momentum currently requires one complete rectangular fluid region")
    args.update(shape=list(inside.shape), fluid_mask=inside.tolist(), body_force_n_m3=force[bounds].tolist())
    result = solve_enclosure_laminar({"contract": CONTRACT, **args,
        "nonlinear_controls": request["flow"]["nonlinear_controls"]}, cancel_check=cancel_check)
    if result["status"] == "completed":
        expanded = []
        for axis, field in enumerate(result["fields"]["face_velocity_m_s"]):
            full_shape = list(shape)
            full_shape[axis] += 1
            full = np.zeros(full_shape)
            selection = list(bounds)
            selection[axis] = slice(int(lower[axis]), int(upper[axis])+1)
            full[tuple(selection)] = np.asarray(field)
            expanded.append(full.tolist())
        pressure = np.zeros(shape)
        pressure[bounds] = result["fields"]["pressure_pa"]
        result["fields"] = {"face_velocity_m_s": expanded, "pressure_pa": pressure.tolist()}
        result["diagnostics"]["thermal_grid_fluid_box_indices"] = [lower.tolist(), upper.tolist()]
    return result


def solve_enclosure_cht(request, *, cancel_check=None):
    """Solve and publish only complete, admitted coupled results."""
    result = {"contract": RESULT, "production_qualified": False, "model_status": "experimental"}
    try:
        if cancel_check is not None and cancel_check():
            raise InterruptedError()
        request, identity, grid, raw_ids, mask, force, heat, materials, fluid = _admit(request)
        flow = _flow(request, grid, mask, force, fluid, cancel_check)
        if flow["status"] != "completed":
            result.update(status=flow["status"], issues=flow.get("issues", []), flow_diagnostics=flow.get("diagnostics"))
            return result
        prolongation = prolong_mac_fluxes(grid, flow["fields"]["face_velocity_m_s"], cancel_check=cancel_check)
        minimum_h = min(request["grid"]["spacing_m"])
        maximum_speed = max(float(np.max(np.abs(v), initial=0.))
                            for v in flow["fields"]["face_velocity_m_s"])
        force_scale = float(np.max(np.abs(force), initial=0.))
        velocity_scale = max(maximum_speed,
            force_scale/(fluid["dynamic_viscosity_pa_s"]/minimum_h**2), 1e-30)
        divergence_budget = 1e-8*velocity_scale/minimum_h
        coarse_divergence = flow["diagnostics"]["maximum_divergence_s_inv"]
        transferred = prolongation["diagnostics"]
        if (transferred["maximum_fine_divergence_s_inv"] > divergence_budget
                or abs(transferred["maximum_coarse_divergence_s_inv"]-coarse_divergence) > divergence_budget):
            raise ValueError("Transferred face field fails the original momentum mass/metric budget")
        parents = np.ix_(*grid["parent_indices"])
        fine_ids = raw_ids[parents]
        fine_mask = mask[parents]
        fine_heat = heat[parents]
        conductivity, capacity = np.empty(grid["shape"]), np.empty(grid["shape"])
        for mid, material in materials.items():
            chosen = fine_ids == mid
            conductivity[chosen] = material["conductivity_w_mk"]
            capacity[chosen] = material["density_kg_m3"]*material["specific_heat_j_kgk"]
        thermal = solve_enclosure_energy(grid, conductivity, capacity, fine_mask, fine_heat,
            prolongation["face_velocity_m_s"], fluid["density_kg_m3"]*fluid["specific_heat_j_kgk"],
            request["boundaries"], request["study"], cancel_check=cancel_check)
        if cancel_check is not None and cancel_check():
            raise InterruptedError()
        result.update(status="completed", request_sha256=identity,
            grid={"axes_m": [axis.tolist() for axis in grid["axes_m"]],
                  "shape": list(grid["shape"]), "coarse_shape": list(grid["coarse_shape"]),
                  "momentum_locally_refined": False, "thermal_refinement": "nested_tensor_planes"},
            fields={"temperature_k": thermal["temperature_k"], "material_ids": fine_ids.tolist(),
                "face_velocity_m_s": [v.tolist() for v in prolongation["face_velocity_m_s"]],
                "coarse_gauge_pressure_pa": flow["fields"]["pressure_pa"]},
            flow_diagnostics=flow["diagnostics"], transfer_diagnostics=prolongation["diagnostics"],
            energy_diagnostics=thermal["diagnostics"], history=thermal["history"],
            temperature_frames=thermal["frames"], interfaces=thermal["interfaces"],
            limitations=["Supplied voxel/tensor geometry, not arbitrary curved CAD",
                "Local refinement is thermal/flux transfer; momentum remains coarse uniform MAC",
                "Creeping obstacles or admitted rectangular inertial fluid region, not general obstacle inertia",
                "Constant properties; no buoyancy, turbulence, rotor, phase change, radiation or FSI",
                "Sensible thermal energy only; viscous/drive work is not automatically deposited as heat",
                "Sparse-direct reference; factorization is only cancellable at process boundary",
                "No measured or human numerical release qualification"])
        # Bound publication as well as input; no oversized or nonfinite field
        # payload escapes as an accepted result.
        _snapshot(result, label="result")
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "ENCLOSURE_CHT_CANCELLED", "message": "Cancelled without accepted fields"}])
    except (ValueError, TypeError, KeyError, ArithmeticError, RuntimeError, RecursionError) as exc:
        result = {"contract": RESULT, "production_qualified": False,
            "model_status": "experimental", "status": "blocked",
            "issues": [{"code": "ENCLOSURE_CHT_REJECTED", "message": str(exc)}]}
    return result
