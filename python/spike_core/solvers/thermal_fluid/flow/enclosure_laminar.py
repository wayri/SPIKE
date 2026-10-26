# SPDX-License-Identifier: Apache-2.0
"""Experimental steady inertial incompressible flow in a closed 3-D box.

Uniform Cartesian MAC grid, stationary no-slip walls, constant rho and mu.
This separate opt-in API does not change creeping-flow or obstacle admission.
See docs/validation/ENCLOSURE_LAMINAR_METHOD_20261020.md for the derivation.
"""
from collections.abc import Mapping
import math
import warnings

import numpy as np
from scipy.sparse import bmat, coo_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from .enclosure_stokes import CONTRACT as STOKES_CONTRACT, EnclosureFlowError, _assemble, _parse

CONTRACT = "spike/enclosure-laminar/v1"
RESULT_CONTRACT = "spike/enclosure-laminar-result/v1"
MAX_REYNOLDS_BOUND = 20.


def _advection(faces, h, velocity, rho):
    """Central dual-face transport, restricted to unconstrained face unknowns.

    Each edge is added once with equal and opposite coefficients. On the
    admitted full box, dual divergence is the average of the two adjacent
    primal divergences. Zero wall values eliminate boundary neighbor terms.
    """
    ids = {(axis, c): i for i, (axis, c, _) in enumerate(faces)}
    rows, cols, data = [], [], []
    for i, (axis, c, other) in enumerate(faces):
        for direction in range(3):
            neighbor = list(c)
            neighbor[direction] += 1
            j = ids.get((axis, tuple(neighbor)))
            if j is None:
                continue
            if direction == axis:
                transport = .5 * (velocity[i] + velocity[j])
            else:
                transport = .5 * (velocity[ids[(direction, c)]]
                                  + velocity[ids[(direction, other)]])
            coefficient = rho * transport / (2 * h[direction])
            rows.extend((i, j))
            cols.extend((j, i))
            data.extend((coefficient, -coefficient))
    return coo_matrix((data, (rows, cols)), shape=(len(faces), len(faces))).tocsr()


def _inputs(request):
    if not isinstance(request, Mapping) or request.get("contract") != CONTRACT:
        raise EnclosureFlowError("Invalid enclosure laminar contract")
    original = dict(request)
    controls = original.pop("nonlinear_controls", None)
    original["contract"] = STOKES_CONTRACT
    parsed = _parse(original)
    shape, _, mask, _, _, _ = parsed
    if min(shape) < 2 or not mask.all():
        raise EnclosureFlowError("Inertial flow requires a full fluid box with at least two cells per axis; obstacles unsupported")
    if not isinstance(controls, Mapping) or set(controls) != {"max_iterations", "relaxation", "relative_tolerance"}:
        raise EnclosureFlowError("Invalid nonlinear_controls fields")
    iterations = controls["max_iterations"]
    if type(iterations) is not int or not 1 <= iterations <= 100:
        raise EnclosureFlowError("max_iterations must be an integer from 1 to 100")
    for name, low, high in (("relaxation", .1, 1.), ("relative_tolerance", 1e-12, 1e-7)):
        value = controls[name]
        if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
            raise EnclosureFlowError(f"{name} must be finite in [{low}, {high}]")
    return parsed, controls


def solve_enclosure_laminar(request, *, cancel_check=None):
    """Solve by damped Oseen/Picard iteration; never publish unconverged fields.

    Reynolds bound <=20 is an intentionally bounded numerical admission, not
    a physical transition criterion or proof of steady-flow stability.
    Sparse LU cannot be cancelled inside one factorization.
    """
    result = {"contract": RESULT_CONTRACT, "production_qualified": False,
              "scope": "closed_uniform_box_constant_property_steady_inertial_flow"}
    try:
        if cancel_check and cancel_check():
            raise InterruptedError()
        (shape, h, mask, force, mu, rho), controls = _inputs(request)
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            cells, faces, a, d, rhs, gauges = _assemble(shape, h, mask, force, mu, cancel_check)
            alpha = mu / float(h.min()) ** 2
            length = float(h.min())
            active = np.arange(1, len(cells))  # Full box has one component.
            dr = d[active] * length
            velocity = np.zeros(len(faces))
            pressure = np.zeros(len(cells))
            volume = float(np.prod(h))
            rhs_norm = max(float(np.linalg.norm(rhs)), 1e-30)
            history = []
            for iteration in range(1, controls["max_iterations"] + 1):
                if cancel_check and cancel_check():
                    raise InterruptedError()
                convection = _advection(faces, h, velocity, rho)
                matrix = bmat([[(a + convection) / alpha, -dr.T], [-dr, None]], format="csc")
                with warnings.catch_warnings():
                    warnings.simplefilter("error", MatrixRankWarning)
                    solution = spsolve(matrix, np.r_[rhs / alpha, np.zeros(len(active))])
                if not np.isfinite(solution).all():
                    raise EnclosureFlowError("Nonfinite Oseen solution")
                omega = controls["relaxation"]
                velocity = (1 - omega) * velocity + omega * solution[:len(faces)]
                pressure[active] = ((1 - omega) * pressure[active]
                                    + omega * solution[len(faces):] * alpha * length)
                convection = _advection(faces, h, velocity, rho)
                momentum = (a + convection) @ velocity - d.T @ pressure - rhs
                residual = float(np.linalg.norm(momentum)) / rhs_norm
                divergence = float(np.max(np.abs(d @ velocity), initial=0))
                speed = float(np.max(np.abs(velocity), initial=0))
                reynolds = rho * math.sqrt(3) * speed * float(np.max(np.array(shape) * h)) / mu
                if not all(math.isfinite(x) for x in (residual, divergence, reynolds)):
                    raise EnclosureFlowError("Nonfinite nonlinear diagnostics")
                history.append(residual)
                scale = max(speed, float(np.max(np.abs(rhs), initial=0)) / alpha, 1e-30)
                if residual <= controls["relative_tolerance"] and divergence <= 1e-9 * scale / length:
                    break
            else:
                raise EnclosureFlowError("Steady nonlinear iteration did not converge")
            if reynolds > MAX_REYNOLDS_BOUND:
                raise EnclosureFlowError("Reynolds upper bound exceeds experimental admission of 20")
            work = float(rhs @ velocity * volume)
            dissipation = float(velocity @ (a @ velocity) * volume)
            convection_power = float(velocity @ (convection @ velocity) * volume)
            pressure_power = float(-velocity @ (d.T @ pressure) * volume)
            energy_scale = max(abs(work), abs(dissipation), rhs_norm * float(np.linalg.norm(velocity)) * volume, 1e-30)
            energy_defect = abs(work - dissipation - convection_power - pressure_power) / energy_scale
            if (not all(math.isfinite(x) for x in (work, dissipation, convection_power, pressure_power, energy_defect))
                    or energy_defect > max(10 * controls["relative_tolerance"], 1e-9)):
                raise EnclosureFlowError("Kinetic energy identity failed")
            fields = []
            for axis in range(3):
                face_shape = list(shape)
                face_shape[axis] += 1
                fields.append(np.zeros(face_shape))
            for value, (axis, c, _) in zip(velocity, faces):
                index = list(c)
                index[axis] += 1
                fields[axis][tuple(index)] = value
            pressure_field = pressure.reshape(shape)
            if cancel_check and cancel_check():
                raise InterruptedError()
            result.update(status="completed", fields={
                "face_velocity_m_s": [field.tolist() for field in fields],
                "pressure_pa": pressure_field.tolist()}, diagnostics={
                "momentum_relative_residual": residual,
                "maximum_divergence_s_inv": divergence, "reynolds_upper_bound": reynolds,
                "force_work_w": work, "viscous_dissipation_w": dissipation,
                "advective_power_w": convection_power, "pressure_power_w": pressure_power,
                "relative_energy_defect": energy_defect, "iterations": iteration,
                "momentum_residual_history": history, "fluid_cells": len(cells),
                "velocity_unknowns": len(faces), "fluid_components": len(gauges)})
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "CANCELLED", "message": "Enclosure inertial flow cancelled"}])
    except (EnclosureFlowError, ValueError, TypeError, ArithmeticError, MatrixRankWarning) as exc:
        result.update(status="blocked", issues=[{"code": "ENCLOSURE_LAMINAR_REJECTED", "message": str(exc)}])
    return result
