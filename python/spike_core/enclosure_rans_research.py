# SPDX-License-Identifier: Apache-2.0
"""Internal equation-verification-only coupled mean flow and SA-noft2.

Full closed rectilinear box, stationary walls and constant molecular nu/rho.
No engineering turbulence admission; original molecular Reynolds bound remains.
"""
from collections.abc import Mapping
import json
import math

import numpy as np

from .enclosure_rectilinear_momentum import (
    CONTRACT as MOMENTUM_CONTRACT, _inputs as _momentum_inputs,
    _assemble, _iteration, _advection, _norm, _power,
)
from .enclosure_refinement import _as_numeric_array, _validate_built_grid
from .enclosure_sa_transport import (
    CONTRACT as SA_CONTRACT, CB1, CB2, CW1, SIGMA, _matvec, _maximum,
    _operators, sa_noft2_coefficients, solve_enclosure_sa_transport,
    _inputs as _sa_inputs,
)
from .enclosure_symmetric_stress import _stress_operator

CONTRACT = "spike/enclosure-rans-research/v1"
RESULT_CONTRACT = "spike/enclosure-rans-research-result/v1"
MAX_FIELD_BYTES = 2 * 1024 * 1024


def _eddy(q, nu):
    chi3 = (q / (7.1 * nu))**3
    return q * (chi3 / (1. + chi3))


def _face_fields(shape, faces, velocity):
    fields = []
    for axis in range(3):
        face_shape = list(shape)
        face_shape[axis] += 1
        fields.append(np.zeros(face_shape))
    for (axis, cell, _), value in zip(faces, velocity):
        index = list(cell)
        index[axis] += 1
        fields[axis][tuple(index)] = value
    return fields


def _inputs(request):
    keys = {"contract", "grid", "density_kg_m3", "molecular_kinematic_viscosity_m2_s",
            "initial_nu_tilde_m2_s", "manufactured_momentum_source_n_m3",
            "manufactured_sa_source_m2_s2", "outer_controls", "momentum_controls", "sa_controls"}
    if not isinstance(request, Mapping) or set(request) != keys or request["contract"] != CONTRACT:
        raise ValueError("Invalid coupled research contract or fields")
    nu, rho = request["molecular_kinematic_viscosity_m2_s"], request["density_kg_m3"]
    for name, value in (("molecular nu", nu), ("density", rho)):
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0.:
            raise ValueError(f"{name} must be finite and positive")
    # Inherited parser owns built-grid, resource, force, density and mean controls.
    raw_grid = request["grid"]
    shape, coarse_shape, axes, coarse_axes, parents, widths, areas = _validate_built_grid(raw_grid)
    if math.prod(shape) > 4096 or min(shape) < 2:
        raise ValueError("Coupled research requires 2+ cells per axis and at most 4096 cells")
    # Validation accepts JSON numeric lists, while private kernels require
    # tuple indexing. Convert only AFTER exact geometry consistency checks;
    # never repair forged metrics by silently recomputing them.
    canonical_grid = {"shape": shape, "coarse_shape": coarse_shape,
                      "axes_m": axes, "coarse_axes_m": coarse_axes,
                      "parent_indices": parents, "cell_widths_m": widths,
                      "face_areas_m2": areas,
                      "cell_centers_m": tuple(np.asarray(v, dtype=float) for v in raw_grid["cell_centers_m"]),
                      "cell_volumes_m3": np.asarray(raw_grid["cell_volumes_m3"], dtype=float)}
    mean = {"contract": MOMENTUM_CONTRACT, "grid": canonical_grid,
            "fluid_mask": np.ones(shape, bool),
            "body_force_n_m3": request["manufactured_momentum_source_n_m3"],
            "dynamic_viscosity_pa_s": float(np.multiply(rho, nu)), "density_kg_m3": rho,
            "nonlinear_controls": request["momentum_controls"]}
    grid, mask, force, molecular_mu, rho, mean_controls = _momentum_inputs(mean)
    outer = request["outer_controls"]
    if not isinstance(outer, Mapping) or set(outer) != {
            "max_iterations", "relative_tolerance", "relaxation"}:
        raise ValueError("Invalid outer_controls")
    if type(outer["max_iterations"]) is not int or not 1 <= outer["max_iterations"] <= 100:
        raise ValueError("Outer max_iterations must be from 1 through 100")
    for key, low, high in (("relative_tolerance", 1e-11, 1e-9), ("relaxation", .1, 1.)):
        val = outer[key]
        if type(val) not in (int, float) or not math.isfinite(val) or not low <= val <= high:
            raise ValueError(f"Outer {key} must be within [{low},{high}]")
    sa = {"contract": SA_CONTRACT, "grid": grid,
          "face_velocity_m_s": _face_fields(shape, [], []),
          "molecular_kinematic_viscosity_m2_s": nu,
          "initial_nu_tilde_m2_s": request["initial_nu_tilde_m2_s"],
          "manufactured_source_m2_s2": request["manufactured_sa_source_m2_s2"],
          "nonlinear_controls": request["sa_controls"]}
    _, _, _, _, _, _, q, source, sa_controls = _sa_inputs(sa)
    for controls in (mean_controls, sa_controls):
        if controls["relative_tolerance"] > outer["relative_tolerance"] / 10.:
            raise ValueError("Inner residual tolerances must be <= one tenth outer tolerance")
    return grid, mask, force, molecular_mu, rho, nu, q.reshape(shape), source, outer, mean_controls, sa


def _sa_residual(grid, fields, nu, q, source, cancel_check):
    """Reassemble the transported equation at the same accepted joint state."""
    lap, adv, gradients, volume, distance, vort, divergence = _operators(grid, fields, cancel_check)
    flat = q.ravel()
    aux = sa_noft2_coefficients(flat, nu, distance, vort)
    local = CB1 * aux["modified_vorticity_s_inv"] * flat - CW1 * aux["fw"] * (flat / distance)**2
    gradient = sum(_matvec(g, flat)**2 for g in gradients)
    convection = _matvec(adv, flat)
    diffusion = _matvec(lap, nu*flat+.5*flat**2)/SIGMA
    rhs = volume * (local + CB2*gradient/SIGMA + source)
    residual = convection + diffusion - rhs
    scale = max(_maximum(convection), _maximum(diffusion), _maximum(rhs), _maximum(residual))
    return residual, divergence, scale


def solve_enclosure_rans_research(request, *, cancel_check=None):
    """Block Gauss-Seidel coupling; final checks use NEW q and SAME u,p."""
    result = {"contract": RESULT_CONTRACT, "research_only": True,
              "production_qualified": False, "model_status": "equation_verification_only",
              "scope": "closed_full_box_coupled_positive_sa_noft2_mean_flow"}
    history = []
    try:
        if cancel_check and cancel_check():
            raise InterruptedError()
        with np.errstate(all="raise"):
            (grid, mask, force, molecular_mu, rho, nu, q, source,
             outer, mean_controls, sa_request) = _inputs(request)
            system = _assemble(grid, mask, force, molecular_mu, cancel_check)
            length = min(float(h.min()) for h in grid["cell_widths_m"])
            extent = max(float(a[-1]-a[0]) for a in grid["axes_m"])
            rhs_norm = _norm(system["F"] / np.sqrt(system["dual_volumes"]))
            sa_reference = None
            for iteration in range(1, outer["max_iterations"]+1):
                if cancel_check and cancel_check():
                    raise InterruptedError()
                previous_q = q.copy()
                viscosity = rho * (nu + _eddy(q, nu))
                system["K"] = _stress_operator(grid, system, viscosity, cancel_check)[0]
                # Deliberately pass ORIGINAL molecular mu to the inherited gate.
                velocity, pressure, convection, mean_diag = _iteration(
                    system, rho, mean_controls, length, extent, molecular_mu, cancel_check)
                molecular_re = math.sqrt(3.) * _maximum(velocity) * extent / nu
                if not math.isfinite(molecular_re) or molecular_re > 20.:
                    raise ValueError("Original molecular Reynolds upper bound exceeds 20")
                fields = _face_fields(grid["shape"], system["faces"], velocity)
                if sa_reference is None:
                    sa_reference = _maximum(grid["cell_volumes_m3"].ravel()*source)
                    if not sa_reference:
                        sa_reference = _sa_residual(grid, fields, nu, q, source, cancel_check)[2]
                sa_request.update(face_velocity_m_s=fields, initial_nu_tilde_m2_s=q)
                sa_result = solve_enclosure_sa_transport(sa_request, cancel_check=cancel_check)
                if sa_result["status"] == "cancelled":
                    raise InterruptedError()
                if sa_result["status"] != "completed":
                    raise ValueError("SA subsolve rejected: " + str(sa_result.get("issues")))
                solved_q = _as_numeric_array(
                    sa_result["fields"]["nu_tilde_m2_s"], "solved SA state", grid["shape"])
                if np.any(solved_q < 0.):
                    raise ValueError("SA subsolve returned a negative state")
                q = (1.-outer["relaxation"])*q + outer["relaxation"]*solved_q
                if not np.isfinite(q).all() or np.any(q < 0.):
                    raise ValueError("Nonfinite or negative coupled q")
                eddy = _eddy(q, nu)
                viscosity = rho * (nu+eddy)
                # Mandatory refreshed coefficient: old system K is not accepted.
                stiffness, strain, weights, _ = _stress_operator(grid, system, viscosity, cancel_check)
                convection, _ = _advection(system, velocity, rho)
                mean_residual = (_matvec(stiffness+convection, velocity)
                                 - _matvec(system["B"].T, pressure) - system["F"])
                mean_norm = _norm(mean_residual/np.sqrt(system["dual_volumes"]))
                mean_relative = mean_norm/rhs_norm if rhs_norm else (0. if mean_norm == 0. else math.inf)
                sa_residual, divergence, _ = _sa_residual(grid, fields, nu, q, source, cancel_check)
                sa_norm = _maximum(sa_residual)
                sa_relative = sa_norm/sa_reference if sa_reference else (0. if sa_norm == 0. else math.inf)
                joint = max(mean_relative, sa_relative)
                if not all(math.isfinite(v) for v in (joint, divergence)):
                    raise ValueError("Nonfinite joint residual")
                q_scale = max(_maximum(previous_q), _maximum(q))
                change = _maximum(q-previous_q)/q_scale if q_scale else 0.
                history.append({"momentum_relative_residual": mean_relative,
                                "sa_relative_residual": sa_relative,
                                "q_change_diagnostic": change,
                                "molecular_reynolds_upper_bound": molecular_re,
                                "mean_inner_iterations": mean_diag["iterations"],
                                "mean_inner_relative_residual": mean_diag["momentum_relative_residual"],
                                "mean_inner_scaled_condition_estimate": mean_diag["scaled_condition_estimate"],
                                "sa_inner_iterations": sa_result["diagnostics"]["iterations"]})
                if joint <= outer["relative_tolerance"]:
                    break
            else:
                raise ValueError("Coupled mean/SA outer iteration did not converge")
            work = _power(system["F"], velocity)
            dissipation = _power(velocity, _matvec(stiffness, velocity))
            rate = _matvec(strain, velocity)
            strain_power = _power(weights, rate**2)
            pressure_power = -_power(velocity, _matvec(system["B"].T, pressure))
            advective = _power(velocity, _matvec(convection, velocity))
            scale = max(abs(work), abs(dissipation), float(np.multiply(_norm(system["F"]), _norm(velocity))))
            energy_error = abs(work-dissipation-advective-pressure_power)/scale if scale else 0.
            strain_error = abs(dissipation-strain_power)/scale if scale else 0.
            if (not all(math.isfinite(v) for v in (energy_error, strain_error))
                    or max(energy_error, strain_error) > min(1e-9, 10.*outer["relative_tolerance"])):
                raise ValueError("Updated-stress joint energy identity failed")
            if cancel_check and cancel_check():
                raise InterruptedError()
            published_fields = {
                "face_velocity_m_s": [v.tolist() for v in fields],
                "pressure_pa": pressure.reshape(grid["shape"]).tolist(),
                "nu_tilde_m2_s": q.tolist(), "eddy_kinematic_viscosity_m2_s": eddy.tolist()}
            field_bytes = len(json.dumps(published_fields, allow_nan=False, separators=(",", ":")).encode("utf-8"))
            if field_bytes > MAX_FIELD_BYTES:
                raise ValueError("Coupled research result fields exceed 2 MiB")
            result.update(status="completed", fields=published_fields,
                diagnostics={"outer_iterations": iteration, "joint_relative_residual": joint,
                             "momentum_relative_residual": mean_relative, "sa_relative_residual": sa_relative,
                             "sa_residual_reference_m5_s2": sa_reference,
                             "last_mean_inner_relative_residual": mean_diag["momentum_relative_residual"],
                             "last_mean_inner_scaled_condition_estimate": mean_diag["scaled_condition_estimate"],
                             "conditioning_state": "last_mean_subsolve_before_closure_update",
                             "maximum_divergence_s_inv": divergence,
                             "molecular_reynolds_upper_bound": molecular_re,
                             "reynolds_viscosity_basis": "original_molecular_only",
                             "maximum_eddy_to_molecular_ratio": float(np.max(eddy/nu)),
                             "minimum_nu_tilde_m2_s": float(q.min()),
                             "relative_energy_defect": energy_error,
                             "relative_strain_energy_defect": strain_error,
                             "residual_state": "same_u_p_updated_q_reassembled",
                             "field_payload_bytes": field_bytes,
                             "manufactured_sources_only": True})
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "CANCELLED", "message": "Coupled research solve cancelled"}])
    except (ValueError, TypeError, ArithmeticError, RuntimeError, KeyError) as exc:
        result.update(status="blocked", issues=[{"code": "RANS_RESEARCH_REJECTED", "message": str(exc)}])
    result.setdefault("diagnostics", {})["outer_residual_history"] = history
    return result
