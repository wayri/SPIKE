# SPDX-License-Identifier: Apache-2.0
"""Equation-verification-only positive-branch SA-noft2 on a closed fluid box.

Fixed incompressible MAC velocity, constant molecular nu, stationary q=0 walls.
This is not a coupled RANS solver and does not admit an engineering regime.
See docs/validation/ENCLOSURE_SA_TRANSPORT_20261020.md for method evidence.
"""
from collections.abc import Mapping
import math
import warnings

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from .enclosure_refinement import _as_numeric_array, _validate_built_grid

CONTRACT = "spike/enclosure-sa-noft2-transport/v1"
RESULT_CONTRACT = "spike/enclosure-sa-noft2-transport-result/v1"
CB1, CB2, SIGMA, KAPPA = .1355, .622, 2. / 3., .41
CW1 = CB1 / KAPPA**2 + (1. + CB2) / SIGMA
MAX_CELLS = 4096


def _maximum(values):
    return float(np.max(np.abs(values), initial=0.))


def _matvec(matrix, vector):
    """Sparse products must obey dimensional underflow checks, unlike BLAS."""
    matrix = matrix.tocsr()
    products = np.multiply(matrix.data, vector[matrix.indices])
    rows = np.repeat(np.arange(matrix.shape[0]), np.diff(matrix.indptr))
    value = np.bincount(rows, weights=products, minlength=matrix.shape[0])
    if not np.isfinite(value).all():
        raise ValueError("Nonfinite sparse accumulation")
    return value


def _row_scale(matrix, scale):
    result = matrix.tocsr(copy=True)
    result.data *= np.repeat(scale, np.diff(result.indptr))
    return result


def sa_noft2_coefficients(q, nu, distance, vorticity):
    """Exact nonnegative variant; TMR modified-S option (c), c2=.7/c3=.9.

    Singular S_hat=0 uses r=10 even at q=0. Multiplication by q makes the
    zero-state source exactly zero; this is not the SA-neg extension.
    """
    q, distance, vorticity = np.broadcast_arrays(
        np.asarray(q, dtype=float), np.asarray(distance, dtype=float),
        np.asarray(vorticity, dtype=float))
    if (not math.isfinite(nu) or nu <= 0 or not np.isfinite(q).all()
            or not np.isfinite(distance).all() or not np.isfinite(vorticity).all()
            or np.any(q < 0) or np.any(distance <= 0) or np.any(vorticity < 0)):
        raise ValueError("SA requires finite q>=0, nu>0, wall distance>0 and vorticity>=0")
    with np.errstate(all="raise"):
        chi = q / nu
        ratio = chi / 7.1
        cube = ratio**3
        fv1 = cube / (1. + cube)
        fv2 = 1. - chi / (1. + chi * fv1)
        length2 = (KAPPA * distance)**2
        sbar = (q / length2) * fv2
        shat = np.array(vorticity + sbar, copy=True)
        limited = sbar < -.7 * vorticity
        om, sb = vorticity[limited], sbar[limited]
        shat[limited] = om + om * (.49 * om + .9 * sb) / (-.5 * om - sb)
        r = np.full(q.shape, 10.)
        nonzero = shat > 0
        r[nonzero] = np.minimum(q[nonzero] / shat[nonzero] / length2[nonzero], 10.)
        g = .7 * r + .3 * r**6
        fw = g * (65. / (g**6 + 64.))**(1. / 6.)
        if not all(np.isfinite(x).all() for x in (fv1, fv2, shat, r, fw)):
            raise ValueError("Nonfinite SA coefficient")
        return {"fv1": fv1, "fv2": fv2, "modified_vorticity_s_inv": shat,
                "r": r, "fw": fw}


def _inputs(request):
    required = {"contract", "grid", "face_velocity_m_s",
                "molecular_kinematic_viscosity_m2_s", "initial_nu_tilde_m2_s",
                "nonlinear_controls"}
    if (not isinstance(request, Mapping) or not required <= set(request)
            or set(request) - required - {"manufactured_source_m2_s2"}
            or request["contract"] != CONTRACT):
        raise ValueError("Invalid SA transport contract or fields")
    grid = request["grid"]
    shape, _, axes, _, _, widths, _ = _validate_built_grid(grid)
    if min(shape) < 2 or math.prod(shape) > MAX_CELLS:
        raise ValueError("SA requires 2 or more cells per axis and at most 4096 cells")
    if max(float(h.max()) for h in widths) / min(float(h.min()) for h in widths) > 64.:
        raise ValueError("SA metric ratio exceeds 64")
    nu = request["molecular_kinematic_viscosity_m2_s"]
    if type(nu) not in (int, float) or not math.isfinite(nu) or nu <= 0:
        raise ValueError("Molecular kinematic viscosity must be finite and positive")
    q = _as_numeric_array(request["initial_nu_tilde_m2_s"], "initial q", shape).ravel().copy()
    if np.any(q < 0):
        raise ValueError("Negative q is unsupported; this is not SA-neg")
    controls = request["nonlinear_controls"]
    if not isinstance(controls, Mapping) or set(controls) != {
            "max_iterations", "relative_tolerance", "relaxation"}:
        raise ValueError("Invalid nonlinear_controls")
    if type(controls["max_iterations"]) is not int or not 1 <= controls["max_iterations"] <= 100:
        raise ValueError("max_iterations must be an integer from 1 to 100")
    for key, low, high in (("relative_tolerance", 1e-12, 1e-7), ("relaxation", .1, 1.)):
        val = controls[key]
        if type(val) not in (int, float) or not math.isfinite(val) or not low <= val <= high:
            raise ValueError(f"{key} outside [{low}, {high}]")
    raw = request["face_velocity_m_s"]
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise ValueError("Three normal-velocity arrays required")
    velocities = []
    for axis in range(3):
        face_shape = list(shape)
        face_shape[axis] += 1
        field = _as_numeric_array(raw[axis], "face velocity", tuple(face_shape))
        if np.any(np.take(field, [0, shape[axis]], axis=axis) != 0.):
            raise ValueError("Closed stationary walls require zero exterior normal velocity")
        velocities.append(field)
    source = (_as_numeric_array(request["manufactured_source_m2_s2"], "manufactured source", shape)
              if "manufactured_source_m2_s2" in request else np.zeros(shape))
    return grid, shape, axes, widths, velocities, float(nu), q, source.ravel(), controls


def _operators(grid, velocities, cancel_check):
    """Integrated -Laplacian L, shared upwind A and cell gradient matrices."""
    shape, axes = grid["shape"], grid["axes_m"]
    centers, widths = grid["cell_centers_m"], grid["cell_widths_m"]
    ids = np.arange(math.prod(shape)).reshape(shape)
    rows, cols, ld, ad = [], [], [], []
    gradients = []
    divergence = np.zeros(shape)
    for axis in range(3):
        if cancel_check and cancel_check():
            raise InterruptedError()
        divergence += np.diff(velocities[axis] * grid["face_areas_m2"][axis], axis=axis)
        gr, gc, gd = [], [], []
        for cell in np.ndindex(shape):
            p, i = int(ids[cell]), cell[axis]
            # Quadratic interpolation through adjacent centers or physical walls.
            xm = centers[axis][i-1] if i else axes[axis][0]
            xp = centers[axis][i+1] if i+1 < shape[axis] else axes[axis][-1]
            hm, hp = centers[axis][i]-xm, xp-centers[axis][i]
            for offset, coefficient in ((-1, -hp/(hm*(hm+hp))),
                                        (0, (hp-hm)/(hm*hp)), (1, hm/(hp*(hm+hp)))):
                other = list(cell)
                other[axis] += offset
                if 0 <= other[axis] < shape[axis]:
                    gr.append(p); gc.append(int(ids[tuple(other)])); gd.append(coefficient)
            if i+1 < shape[axis]:
                other = list(cell)
                other[axis] += 1
                other = tuple(other)
                n = int(ids[other])
                area = grid["face_areas_m2"][axis][other]
                conductance = area / (centers[axis][i+1]-centers[axis][i])
                transport = velocities[axis][other] * area
                rows.extend((p, p, n, n)); cols.extend((p, n, p, n))
                ld.extend((conductance, -conductance, -conductance, conductance))
                ad.extend((max(transport, 0), min(transport, 0),
                           -max(transport, 0), -min(transport, 0)))
            for side in (0, 1):
                if i == (shape[axis]-1 if side else 0):
                    face = list(cell); face[axis] += side
                    conductance = grid["face_areas_m2"][axis][tuple(face)] / (widths[axis][i]/2.)
                    rows.append(p); cols.append(p); ld.append(conductance); ad.append(0.)
        gradients.append(coo_matrix((gd, (gr, gc)), shape=(ids.size, ids.size)).tocsr())
    volume = grid["cell_volumes_m3"].ravel()
    speed = max(_maximum(v) for v in velocities)
    div = _maximum(divergence.ravel()/volume)
    if div > (1e-9 * speed / min(float(h.min()) for h in widths) if speed else 0.):
        raise ValueError("Supplied MAC velocity is not discretely incompressible")
    lap = coo_matrix((ld, (rows, cols)), shape=(ids.size, ids.size)).tocsr()
    adv = coo_matrix((ad, (rows, cols)), shape=(ids.size, ids.size)).tocsr()
    if not np.isfinite(lap.data).all() or not np.isfinite(adv.data).all():
        raise ValueError("Unrepresentable transport coefficients")
    cell_velocity = [(.5 * (np.take(v, range(shape[a]), axis=a)
                            + np.take(v, range(1, shape[a]+1), axis=a))).ravel()
                     for a, v in enumerate(velocities)]
    curl = [_matvec(gradients[b], cell_velocity[c]) - _matvec(gradients[c], cell_velocity[b])
            for b, c in ((1, 2), (2, 0), (0, 1))]
    vorticity = np.hypot(np.hypot(curl[0], curl[1]), curl[2])
    wall = np.minimum.reduce(np.broadcast_arrays(*[
        np.minimum(c-axes[a][0], axes[a][-1]-c).reshape(
            tuple(shape[a] if b == a else 1 for b in range(3)))
        for a, c in enumerate(centers)])).ravel()
    return lap, adv, gradients, volume, wall, vorticity, div


def solve_enclosure_sa_transport(request, *, cancel_check=None):
    """Damped sparse Newton solve; success requires the actual steady residual.

    Positive trial steps are backtracked, never clipped. A bounded failure
    publishes diagnostics but no fields. Sparse factorization is not interruptible.
    """
    result = {"contract": RESULT_CONTRACT, "production_qualified": False,
              "scope": "fixed_velocity_closed_box_sa_noft2_equation_verification",
              "research_only": True}
    history, rejected = [], 0
    try:
        if cancel_check and cancel_check():
            raise InterruptedError()
        with np.errstate(all="raise"):
            grid, shape, axes, widths, velocity, nu, q, source, controls = _inputs(request)
            lap, adv, gradients, volume, wall, vort, divergence = _operators(grid, velocity, cancel_check)
            load = volume * source

            def sources(state):
                aux = sa_noft2_coefficients(state, nu, wall, vort)
                production = CB1 * aux["modified_vorticity_s_inv"] * state
                destruction = CW1 * aux["fw"] * (state / wall)**2
                return production - destruction, aux

            def evaluate(state):
                local, aux = sources(state)
                grad = [_matvec(g, state) for g in gradients]
                diffusion = _matvec(lap, nu * state + .5 * state**2) / SIGMA
                convection = _matvec(adv, state)
                gradient_source = CB2 / SIGMA * sum(g**2 for g in grad)
                rhs = volume * (local + gradient_source) + load
                residual = convection + diffusion - rhs
                if not all(np.isfinite(x).all() for x in (residual, rhs, diffusion, convection)):
                    raise ValueError("Nonfinite transport residual")
                scale = max(_maximum(convection), _maximum(diffusion), _maximum(rhs), _maximum(load))
                return residual, scale, grad, aux

            # Nonzero forcing supplies a seed-independent physical reference.
            # Otherwise retain actual initial terms, so homogeneous decay does
            # not move its own convergence goal. No dimensional floor is used.
            residual, reference, _, _ = evaluate(q)
            reference = _maximum(load) or max(reference, _maximum(residual))
            for iteration in range(controls["max_iterations"]+1):
                if cancel_check and cancel_check():
                    raise InterruptedError()
                residual, _, grad, aux = evaluate(q)
                norm = _maximum(residual)
                relative = norm / reference if reference else (0. if norm == 0. else math.inf)
                history.append(relative)
                if relative <= controls["relative_tolerance"]:
                    break
                if iteration == controls["max_iterations"]:
                    raise ValueError("Steady SA nonlinear iteration did not converge")
                step = np.full(q.shape, max(nu, _maximum(q)) * 1e-7)
                if not np.all(q + step > q):
                    raise ValueError("Unrepresentable Newton perturbation")
                derivative = (sources(q+step)[0]-sources(q)[0])/step
                diffusion_jacobian = lap.copy()
                diffusion_jacobian.data *= (nu+q)[lap.indices] / SIGMA
                jacobian = adv + diffusion_jacobian - diags(volume * derivative)
                for g, dq in zip(gradients, grad):
                    jacobian -= _row_scale(g, volume * (2. * CB2 / SIGMA) * dq)
                row = np.asarray(abs(jacobian).sum(axis=1)).ravel()
                if not np.isfinite(row).all() or np.any(row <= 0.):
                    raise ValueError("Unresolved SA Jacobian")
                with warnings.catch_warnings():
                    warnings.simplefilter("error", MatrixRankWarning)
                    delta = spsolve(_row_scale(jacobian, 1./row), -residual/row)
                if not np.isfinite(delta).all():
                    raise ValueError("Nonfinite Newton update")
                alpha = controls["relaxation"]
                for attempt in range(32):
                    if cancel_check and cancel_check():
                        raise InterruptedError()
                    trial = q + alpha * delta
                    if np.all(trial >= 0.):
                        trial_norm = _maximum(evaluate(trial)[0])
                        if trial_norm < norm * (1. - 1e-4*alpha):
                            q = trial
                            break
                    rejected += 1
                    alpha *= .5
                else:
                    raise ValueError("Positive residual-decreasing Newton step unavailable")
            eddy = q * aux["fv1"]
            linear_diffusion = _matvec(lap, nu*q) / SIGMA
            nonlinear_diffusion = _matvec(lap, .5*q**2) / SIGMA
            diffusion_norm = _maximum(linear_diffusion+nonlinear_diffusion)
            nonlinear_fraction = (_maximum(nonlinear_diffusion)/diffusion_norm
                                  if diffusion_norm else 0.)
            gradient_source_norm = _maximum(volume * (CB2 / SIGMA) * sum(dq**2 for dq in grad))
            guarded = q/(KAPPA*wall)**2 * aux["fv2"] < -.7*vort
            if cancel_check and cancel_check():
                raise InterruptedError()
            result.update(status="completed", fields={
                "nu_tilde_m2_s": q.reshape(shape).tolist(),
                "eddy_kinematic_viscosity_m2_s": eddy.reshape(shape).tolist()},
                diagnostics={"iterations": iteration, "steady_relative_residual": relative,
                             "residual_reference_m5_s2": reference,
                             "residual_reference_kind": "manufactured_load" if _maximum(load) else "initial_terms",
                             "maximum_steady_residual_m5_s2": norm,
                             "maximum_divergence_s_inv": divergence,
                             "minimum_wall_distance_m": float(wall.min()),
                             "maximum_wall_distance_m": float(wall.max()),
                             "minimum_nu_tilde_m2_s": float(q.min()),
                             "maximum_eddy_kinematic_viscosity_m2_s": float(eddy.max()),
                             "maximum_chi": float(np.max(q/nu)),
                             "modified_vorticity_guarded_cells": int(np.count_nonzero(guarded)),
                             "nonlinear_diffusion_fraction": nonlinear_fraction,
                             "gradient_source_maximum_m5_s2": gradient_source_norm,
                             "manufactured_source_used": "manufactured_source_m2_s2" in request,
                             "modified_vorticity_guard": "TMR_option_c_c2_0.7_c3_0.9",
                             "positivity_clipping_count": 0})
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "CANCELLED", "message": "SA transport cancelled"}])
    except (ValueError, TypeError, ArithmeticError, MatrixRankWarning, RuntimeError) as exc:
        result.update(status="blocked", issues=[{"code": "SA_TRANSPORT_REJECTED", "message": str(exc)}])
    result.setdefault("diagnostics", {}).update(
        residual_history=history, rejected_trial_steps=rejected)
    return result
