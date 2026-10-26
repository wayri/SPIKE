# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Experimental obstacle-inertial CHT on the actual nested rectilinear grid.

Version one remains unchanged. Selected cuts re-solve momentum and energy on
the same grid; they propagate tensor planes, not confined octree AMR patches.
"""
import math

import numpy as np

from .enclosure_cht import REQUEST as LEGACY_REQUEST, _admit, _keys, _snapshot
from .enclosure_energy import solve_enclosure_energy

REQUEST = "spike/enclosure-cht-request/v2"
RESULT = "spike/enclosure-cht-result/v2"


def _empty(status="blocked", message="Request rejected"):
    return {"contract": RESULT, "status": status, "model_status": "experimental",
        "production_qualified": False,
        "issues": [{"code": "ENCLOSURE_CHT_V2_CANCELLED" if status == "cancelled"
                   else "ENCLOSURE_CHT_V2_REJECTED", "message": message}]}


def _verify_faces(grid, mask, force, viscosity, fields):
    """Recompute physical mass from emitted faces, independent of diagnostics."""
    _keys(fields, ("face_velocity_m_s", "pressure_pa"))
    shape = grid["shape"]
    values = fields["face_velocity_m_s"]
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError("Momentum must return three shared normal face fields")
    faces, divergence, speed = [], np.zeros(shape), 0.
    for axis, value in enumerate(values):
        expected = list(shape)
        expected[axis] += 1
        raw = np.asarray(value)
        if raw.shape != tuple(expected) or raw.dtype.kind not in "iuf" or not np.isfinite(raw).all():
            raise ValueError("Invalid momentum face field")
        field = raw.astype(float)
        allowed = np.zeros(expected, dtype=bool)
        lower, upper, interior = [[slice(None)]*3 for _ in range(3)]
        lower[axis], upper[axis], interior[axis] = slice(None, -1), slice(1, None), slice(1, -1)
        allowed[tuple(interior)] = mask[tuple(lower)] & mask[tuple(upper)]
        if np.any(field[~allowed] != 0.):
            raise ValueError("Momentum crosses a closed wall or a supplied solid")
        widths_shape = [1, 1, 1]
        widths_shape[axis] = shape[axis]
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            divergence += np.diff(field, axis=axis)/grid["cell_widths_m"][axis].reshape(widths_shape)
        speed = max(speed, float(np.max(np.abs(field), initial=0.)))
        faces.append(field)
    pressure = np.asarray(fields["pressure_pa"])
    if pressure.shape != shape or pressure.dtype.kind not in "iuf" or not np.isfinite(pressure).all():
        raise ValueError("Invalid momentum pressure field")
    hmin = min(float(np.min(width)) for width in grid["cell_widths_m"])
    force_scale = float(np.max(np.abs(force), initial=0.))
    velocity_scale = max(speed, force_scale/(viscosity/hmin**2))
    if force_scale > 0 and velocity_scale == 0:
        raise ValueError("Unrepresentable momentum velocity scale")
    maximum = float(np.max(np.abs(divergence), initial=0.))
    budget = 1e-9*velocity_scale/hmin
    if not math.isfinite(maximum) or not math.isfinite(budget) or maximum > budget:
        raise ValueError("Emitted fine-grid momentum faces fail physical mass balance")
    return faces, {"independent_maximum_divergence_s_inv": maximum,
                   "independent_divergence_budget_s_inv": budget}


def solve_enclosure_cht_v2(request, *, cancel_check=None):
    """Solve on the actual refined grid; never publish rejected partial fields."""
    try:
        if cancel_check is not None and cancel_check():
            raise InterruptedError()
        if not isinstance(request, dict) or request.get("contract") != REQUEST:
            raise ValueError(f"Expected {REQUEST}")
        public, identity = _snapshot(request)
        if not isinstance(public.get("flow"), dict) or public["flow"].get("model") != "rectilinear_laminar":
            raise ValueError("v2 requires explicit rectilinear_laminar flow")
        # Reuse the exact v1 material, source, boundary and resource admission,
        # not its flow solve or its publication/digest identity.
        base = {**public, "contract": LEGACY_REQUEST,
                "flow": {**public["flow"], "model": "laminar_inertial"}}
        admitted, _, grid, ids, _, force, heat, materials, fluid = _admit(base)
        parents = np.ix_(*grid["parent_indices"])
        fine_ids, fine_force, fine_heat = ids[parents], force[parents], heat[parents]
        mask = fine_ids == fluid["id"]
        from .enclosure_rectilinear_momentum import solve_enclosure_rectilinear_momentum, CONTRACT
        flow = solve_enclosure_rectilinear_momentum({"contract": CONTRACT,
            "grid": grid, "fluid_mask": mask.tolist(), "body_force_n_m3": fine_force.tolist(),
            "dynamic_viscosity_pa_s": fluid["dynamic_viscosity_pa_s"],
            "density_kg_m3": fluid["density_kg_m3"],
            "nonlinear_controls": admitted["flow"]["nonlinear_controls"]}, cancel_check=cancel_check)
        if flow.get("status") != "completed":
            return _empty("cancelled" if flow.get("status") == "cancelled" else "blocked",
                          str(flow.get("issues", "Momentum did not complete")))
        faces, independent_mass = _verify_faces(grid, mask, fine_force,
            fluid["dynamic_viscosity_pa_s"], flow["fields"])
        conductivity, capacity = np.empty(grid["shape"]), np.empty(grid["shape"])
        for mid, material in materials.items():
            chosen = fine_ids == mid
            conductivity[chosen] = material["conductivity_w_mk"]
            capacity[chosen] = material["density_kg_m3"]*material["specific_heat_j_kgk"]
        # Do not turn a supplied nonzero source/storage into exact zero through
        # dimensional underflow before the shared energy operator sees it.
        with np.errstate(over="raise", invalid="raise", under="raise"):
            np.multiply(fine_heat, grid["cell_volumes_m3"])
            np.multiply(capacity, grid["cell_volumes_m3"])
        thermal = solve_enclosure_energy(grid, conductivity, capacity, mask, fine_heat, faces,
            fluid["density_kg_m3"]*fluid["specific_heat_j_kgk"], admitted["boundaries"],
            admitted["study"], cancel_check=cancel_check)
        if cancel_check is not None and cancel_check():
            raise InterruptedError()
        result = {"contract": RESULT, "status": "completed", "model_status": "experimental",
            "production_qualified": False, "request_sha256": identity,
            "grid": {"axes_m": [a.tolist() for a in grid["axes_m"]],
                "shape": list(grid["shape"]), "coarse_shape": list(grid["coarse_shape"]),
                "momentum_grid": "resolved_nested_tensor_planes",
                "momentum_locally_refined": grid["shape"] != grid["coarse_shape"],
                "confined_patch_amr": False},
            "fields": {"temperature_k": thermal["temperature_k"], "material_ids": fine_ids.tolist(),
                "face_velocity_m_s": [a.tolist() for a in faces],
                "gauge_pressure_pa": flow["fields"]["pressure_pa"]},
            "flow_diagnostics": flow["diagnostics"], "independent_mass_diagnostics": independent_mass,
            "energy_diagnostics": thermal["diagnostics"], "history": thermal["history"],
            "temperature_frames": thermal["frames"], "interfaces": thermal["interfaces"],
            "limitations": ["Supplied staircase voxels; not curved CAD or conforming cut cells",
                "Selected cuts re-solve momentum but propagate whole tensor planes; not octree AMR",
                "Coarse material, force and heat samples are inherited piecewise constantly",
                "Steady constant-property laminar momentum; no transient momentum or buoyancy feedback",
                "No turbulence closure, rotating blade mesh, propeller qualification or FSI",
                "Sensible heat only; mechanical drive work is not automatically deposited as heat",
                "Sparse factorization requires process-level hard cancellation",
                "Experimental mathematical verification only; no measured or human release qualification"]}
        _snapshot(result, label="result")
        return result
    except InterruptedError:
        return _empty("cancelled", "Cancelled without accepted fields")
    except (ValueError, TypeError, KeyError, ArithmeticError, RuntimeError, RecursionError) as exc:
        return _empty(message=str(exc))
