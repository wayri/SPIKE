# SPDX-License-Identifier: Apache-2.0
"""Experimental constant-rotation closed enclosure in its co-rotating frame.

All walls and supplied fields are fixed in this frame. This is not a propeller,
moving-blade or rotating/stationary-interface solver. No worker route is added.
"""
from collections.abc import Mapping
import math

import numpy as np
from scipy.sparse import coo_matrix, diags, kron

from .enclosure_rectilinear_momentum import (
    CONTRACT as MOMENTUM_CONTRACT, _advection, _assemble, _inputs, _iteration,
    _norm, _power, _shift,
)
from .enclosure_stokes import EnclosureFlowError

CONTRACT = "spike/enclosure-rotating-frame/v1"
RESULT_CONTRACT = "spike/enclosure-rotating-frame-result/v1"
MAX_ROTATION_NUMBER = 20.


def _vector(value, name):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise EnclosureFlowError(f"{name} must contain three finite real scalars")
    return np.asarray(value, dtype=float)


def _parse(request):
    if not isinstance(request, Mapping) or request.get("contract") != CONTRACT:
        raise EnclosureFlowError("Invalid rotating-frame contract")
    original = dict(request)
    omega = _vector(original.pop("angular_velocity_rad_s", None), "angular_velocity_rad_s")
    origin = _vector(original.pop("rotation_origin_m", None), "rotation_origin_m")
    original["contract"] = MOMENTUM_CONTRACT
    return (*_inputs(original), omega, origin)


def _coriolis(system, omega, rho):
    """Return integrated 2*rho*E.T*V*cross(Omega)*E and cell interpolation E."""
    cells, faces = system["cells"], system["faces"]
    ids = {cell: i for i, cell in enumerate(cells)}
    rows, cols, data = [], [], []
    for j, (axis, c, other) in enumerate(faces):
        for cell in (c, other):
            rows.append(3*ids[cell]+axis)
            cols.append(j)
            data.append(.5)
    interpolation = coo_matrix((data, (rows, cols)), shape=(3*len(cells), len(faces))).tocsr()
    ox, oy, oz = omega
    cross = coo_matrix(np.array([[0., -oz, oy], [oz, 0., -ox], [-oy, ox, 0.]]))
    cell_operator = kron(diags(2*rho*system["cell_volumes"]), cross, format="csr")
    return (interpolation.T @ cell_operator @ interpolation).tocsr(), interpolation


def _physical_pressure(grid, system, reduced, omega, origin, rho):
    """Recover gauge p = Pi + rho*|Omega cross (x-origin)|^2/2 per component."""
    positions = np.array([[grid["cell_centers_m"][a][c[a]] for a in range(3)]
                          for c in system["cells"]])
    spin_velocity = np.cross(omega, positions-origin)
    potential = .5*rho*np.sum(np.multiply(spin_velocity, spin_velocity), axis=1)
    if not np.isfinite(potential).all():
        raise EnclosureFlowError("Centrifugal pressure potential is not representable")
    # Propagate the known gauge potential through each fluid component.
    ids = {c: i for i, c in enumerate(system["cells"])}
    adjacency = [[] for _ in system["cells"]]
    for _, c, other in system["faces"]:
        i, j = ids[c], ids[other]
        adjacency[i].append(j)
        adjacency[j].append(i)
    physical = np.zeros_like(reduced)
    seen = set()
    for gauge in system["gauges"]:
        seen.add(gauge)
        todo = [gauge]
        while todo:
            i = todo.pop()
            # Do not subtract huge, nearly equal absolute potentials.
            delta_spin = np.cross(omega, positions[i]-positions[gauge])
            delta_potential = rho*(_power(spin_velocity[gauge], delta_spin)
                                  + .5*_power(delta_spin, delta_spin))
            physical[i] = reduced[i] + delta_potential
            for j in adjacency[i]:
                if j not in seen:
                    seen.add(j)
                    todo.append(j)
    if not np.isfinite(physical).all():
        raise EnclosureFlowError("Physical rotating-frame pressure is not representable")
    return physical, potential


def solve_enclosure_rotating_frame(request, *, cancel_check=None):
    """Return relative velocities and physical/reduced gauge pressures.

    The entire enclosure, every obstacle and all loads co-rotate rigidly at
    the supplied constant Omega. Axes and force components use that frame.
    """
    result = {"contract": RESULT_CONTRACT, "production_qualified": False,
              "scope": "closed_corotating_rectilinear_constant_property_steady_laminar_flow"}
    try:
        if cancel_check and cancel_check():
            raise InterruptedError()
        with np.errstate(over="raise", under="raise", invalid="raise", divide="raise"):
            grid, mask, force, mu, rho, controls, omega, origin = _parse(request)
            extent = max(float(axis[-1]-axis[0]) for axis in grid["axes_m"])
            rotation_number = float(np.float64(rho)*_norm(omega)*2*extent*extent/mu)
            if not math.isfinite(rotation_number) or rotation_number > MAX_ROTATION_NUMBER:
                raise EnclosureFlowError("Rotation number exceeds experimental admission of 20")
            system = _assemble(grid, mask, force, mu, cancel_check)
            rotation, _ = _coriolis(system, omega, rho)
            # Admission of the potential happens before costly factorization.
            _, potential = _physical_pressure(grid, system, np.zeros(len(system["cells"])),
                                               omega, origin, rho)
            length = min(float(h.min()) for h in grid["cell_widths_m"])
            velocity, reduced, _, diagnostics = _iteration(
                system, rho, controls, length, extent, mu, cancel_check, linear_skew=rotation)
            physical, _ = _physical_pressure(grid, system, reduced, omega, origin, rho)
            advection, _ = _advection(system, velocity, rho)
            work = _power(system["F"], velocity)
            dissipation = _power(velocity, system["K"] @ velocity)
            advection_power = _power(velocity, advection @ velocity)
            coriolis_power = _power(velocity, rotation @ velocity)
            pressure_power = -_power(velocity, system["B"].T @ reduced)
            scale = max(abs(work), abs(dissipation),
                        float(np.multiply(_norm(system["F"]), _norm(velocity))))
            defect = abs(work-dissipation-advection_power-coriolis_power-pressure_power)/scale if scale else 0.
            if (not all(math.isfinite(x) for x in (
                    work, dissipation, advection_power, coriolis_power, pressure_power, defect))
                    or defect > max(10*controls["relative_tolerance"], 1e-9)
                    or (scale and abs(coriolis_power)/scale > 1e-10)):
                raise EnclosureFlowError("Rotating-frame kinetic-energy identity failed")
            fields = []
            for axis in range(3):
                shape = list(grid["shape"])
                shape[axis] += 1
                fields.append(np.zeros(shape))
            for value, (axis, c, _) in zip(velocity, system["faces"]):
                fields[axis][_shift(c, axis, 1)] = value
            p, pi = np.zeros(grid["shape"]), np.zeros(grid["shape"])
            for cell, actual, modified in zip(system["cells"], physical, reduced):
                p[cell], pi[cell] = actual, modified
            diagnostics.update(
                force_work_w=work, viscous_dissipation_w=dissipation,
                advective_power_w=advection_power, coriolis_power_w=coriolis_power,
                reduced_pressure_power_w=pressure_power, relative_energy_defect=defect,
                fluid_cells=len(system["cells"]), velocity_unknowns=len(velocity),
                fluid_components=len(system["gauges"]), momentum_grid_shape=list(grid["shape"]),
                momentum_grid_kind="tensor_plane_rectilinear_not_octree",
                velocity_reference_frame="co_rotating_relative",
                rotation_number=rotation_number,
                maximum_centrifugal_potential_pa=float(np.max(potential, initial=0.)))
        if cancel_check and cancel_check():
            raise InterruptedError()
        result.update(status="completed", fields={
            "face_velocity_m_s": [field.tolist() for field in fields],
            "pressure_pa": p.tolist(), "reduced_pressure_pa": pi.tolist()}, diagnostics=diagnostics)
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "CANCELLED", "message": "Rotating-frame solve cancelled"}])
    except (ValueError, TypeError, ArithmeticError, RuntimeError) as exc:
        result.update(status="blocked", issues=[{"code": "ENCLOSURE_ROTATING_FRAME_REJECTED",
                                                "message": str(exc)}])
    return result
