# SPDX-License-Identifier: Apache-2.0
"""Conservative orthogonal 3-D conjugate sensible-energy reference operator.

Flow is supplied as shared MAC face velocities. Positive heat is generated in
cells or enters through a prescribed exterior flux. All reported boundary heat
is outward. No viscous heating, radiation, phase change or buoyancy is inferred.
"""
import math
import warnings

import numpy as np
from scipy.sparse import lil_matrix, diags
from scipy.sparse.linalg import splu, MatrixRankWarning


FACES = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")


def solve_enclosure_energy(grid, conductivity, capacity, fluid, heat, velocities,
                           fluid_rho_cp, boundaries, study, *, cancel_check=None):
    shape = grid["shape"]
    count = math.prod(shape)
    widths, areas = grid["cell_widths_m"], grid["face_areas_m2"]
    volume = grid["cell_volumes_m3"]
    index = np.arange(count).reshape(shape)
    matrix = lil_matrix((count, count))
    rhs = (heat*volume).ravel().copy()
    pairs, surface = [], []
    transient = study["type"] == "transient"
    references = [bc["temperature_k"] if bc["type"] == "temperature" else bc["ambient_temperature_k"]
                  for bc in boundaries.values() if bc["type"] in ("temperature", "convection")]
    reference_k = study["initial_temperature_k"] if transient else min(references)

    def poll():
        if cancel_check is not None and cancel_check():
            raise InterruptedError("Enclosure energy cancelled")

    for axis in range(3):
        poll()
        for cell in np.ndindex(shape):
            if cell[axis]+1 >= shape[axis]:
                continue
            other = list(cell)
            other[axis] += 1
            other = tuple(other)
            face = other
            area = float(areas[axis][face])
            distance_p, distance_n = widths[axis][cell[axis]]/2, widths[axis][other[axis]]/2
            conductance = area/(distance_p/conductivity[cell]+distance_n/conductivity[other])
            p, n = int(index[cell]), int(index[other])
            matrix[p, p] += conductance
            matrix[n, n] += conductance
            matrix[p, n] -= conductance
            matrix[n, p] -= conductance
            speed = float(velocities[axis][face])
            if not (fluid[cell] and fluid[other]) and speed != 0.:
                raise ValueError("Advection crosses a supplied solid/fluid or solid/solid face")
            transport = fluid_rho_cp*speed*area if fluid[cell] and fluid[other] else 0.
            if transport >= 0:
                matrix[p, p] += transport
                matrix[n, p] -= transport
            else:
                matrix[p, n] += transport
                matrix[n, n] -= transport
            if not all(math.isfinite(x) for x in (conductance, transport)) or conductance <= 0:
                raise ValueError("Unrepresentable thermal face coefficient")
            pairs.append((p, n, conductance, transport, bool(fluid[cell] != fluid[other]),
                          distance_p/conductivity[cell], distance_n/conductivity[other], area))
        for side in (0, 1):
            name = FACES[2*axis+side]
            bc = boundaries[name]
            for cell in np.ndindex(shape):
                if cell[axis] != (0 if side == 0 else shape[axis]-1):
                    continue
                face = list(cell)
                face[axis] += side
                area = float(areas[axis][tuple(face)])
                if velocities[axis][tuple(face)] != 0.:
                    raise ValueError("Closed enclosure has an exterior mass flux")
                p = int(index[cell])
                if bc["type"] in ("temperature", "convection"):
                    half_resistance = widths[axis][cell[axis]]/(2*conductivity[cell])
                    external = (0. if bc["type"] == "temperature" else
                                1/bc["heat_transfer_coefficient_w_m2k"])
                    g = area/(half_resistance+external)
                    reference = (bc["temperature_k"] if bc["type"] == "temperature" else bc["ambient_temperature_k"])-reference_k
                    matrix[p, p] += g
                    rhs[p] += g*reference
                    surface.append((name, p, g, reference, 0.))
                elif bc["type"] == "heat_flux":
                    inward = area*bc["inward_heat_flux_w_m2"]
                    rhs[p] += inward
                    surface.append((name, p, 0., 0., -inward))
                else:
                    surface.append((name, p, 0., 0., 0.))
    matrix = matrix.tocsc()
    if not np.isfinite(matrix.data).all() or not np.isfinite(rhs).all():
        raise ValueError("Nonfinite thermal assembly")
    dt, steps = (study["time_step_s"], study["steps"]) if transient else (1., 1)
    mass = (capacity*volume).ravel()
    system = matrix+diags(mass/dt, format="csc") if transient else matrix
    diagonal = np.asarray(abs(system).sum(axis=1)).ravel()
    if not np.isfinite(diagonal).all() or np.any(diagonal <= 0):
        raise ValueError("Unanchored or invalid thermal system")
    poll()
    with warnings.catch_warnings():
        warnings.simplefilter("error", MatrixRankWarning)
        factor = splu(system)
    # For the admitted Z-matrix, a positive x with A*x=1 establishes the
    # nonsingular M-matrix property in exact arithmetic. Then A^-1>=0 and
    # ||A^-1||_infinity=max(A^-1*1). This checks the constant/weak-anchor mode
    # that a residual normalized only by large diffusion terms can miss.
    inverse_constant = factor.solve(np.ones(count))
    constant_residual = float(np.max(np.abs(system@inverse_constant-1)))
    if (not np.isfinite(inverse_constant).all() or np.min(inverse_constant) <= 0
            or constant_residual > 1e-6):
        raise ValueError("Unresolved thermal anchoring or constant-mode conditioning")
    condition_indicator = float(np.max(diagonal)*np.max(inverse_constant)/(1-constant_residual))
    if not math.isfinite(condition_indicator) or condition_indicator > 1e10:
        raise ValueError("Thermal conditioning indicator exceeds 1e10; anchor or refine the model")
    prior = np.zeros(count) if transient else None
    frames, history = [], []
    temperature = None
    generated = float(np.sum(heat*volume))
    initial_energy = 0. if transient else None
    integrated_boundary, integrated_generated = 0., 0.
    maximum_residual = 0.
    for step in range(1, steps+1):
        poll()
        load = rhs+mass*prior/dt if transient else rhs
        temperature = np.asarray(factor.solve(load))
        if not np.isfinite(temperature).all() or np.min(temperature)+reference_k <= 0:
            raise ValueError("Nonfinite or nonpositive absolute temperature")
        residual = system@temperature-load
        normalized = float(np.max(np.abs(residual)/np.maximum(diagonal, 1e-30)))
        maximum_residual = max(maximum_residual, normalized)
        # Kelvin-scaled row residual, separate from global W conservation.
        if normalized > 1e-8*max(1., float(np.max(np.abs(temperature)))):
            raise ValueError("Thermal linear residual failed")
        outward = {name: math.fsum(g*(temperature[p]-reference)+constant
                    for face, p, g, reference, constant in surface if face == name) for name in FACES}
        total_outward = math.fsum(outward.values())
        stored_rate = float(np.dot(mass, temperature-prior)/dt) if transient else 0.
        balance = generated-total_outward-stored_rate
        scale = max(abs(generated), sum(abs(q) for q in outward.values()), abs(stored_rate), 1e-300)
        if not math.isfinite(balance) or abs(balance) > 1e-7*scale:
            raise ValueError("Conjugate energy conservation failed")
        interface_heat, interface_abs, interface_jump = 0., 0., 0.
        interface_records = []
        for p, n, g, transport, interface, rp, rn, area in pairs:
            if not interface:
                continue
            q = g*(temperature[p]-temperature[n])
            left_t, right_t = temperature[p]-q*rp/area, temperature[n]+q*rn/area
            interface_heat += q
            interface_abs += abs(q)
            interface_jump = max(interface_jump, abs(left_t-right_t))
            interface_records.append({"cell_p": p, "cell_n": n, "area_m2": area,
                "heat_p_to_n_w": float(q), "temperature_k": float((left_t+right_t)/2+reference_k)})
        item = {"time_s": step*dt if transient else None, "generated_heat_w": generated,
            "outward_heat_w": outward, "stored_energy_rate_w": stored_rate,
            "raw_energy_balance_w": balance, "relative_energy_balance": abs(balance)/scale,
            "row_scaled_residual_k": normalized, "minimum_temperature_k": float(temperature.min()+reference_k),
            "maximum_temperature_k": float(temperature.max()+reference_k),
            "interface_signed_heat_w": interface_heat, "interface_absolute_heat_w": interface_abs,
            "maximum_interface_temperature_jump_k": interface_jump}
        history.append(item)
        if transient:
            integrated_boundary += total_outward*dt
            integrated_generated += generated*dt
            if step % study["output_stride"] == 0 or step == steps:
                frames.append({"time_s": step*dt, "temperature_k": (temperature.reshape(shape)+reference_k).tolist()})
            prior = temperature
    poll()
    data = {"temperature_k": (temperature.reshape(shape)+reference_k).tolist(), "history": history,
        "frames": frames, "diagnostics": {**history[-1], "maximum_row_scaled_residual_k": maximum_residual,
            "solid_fluid_faces": len(interface_records), "factorizations": 1,
            "constant_mode_condition_indicator": condition_indicator,
            "constant_mode_solve_residual": constant_residual},
        "interfaces": interface_records}
    if transient:
        change = float(np.dot(mass, temperature))-initial_energy
        data["diagnostics"].update({"stored_energy_change_j": change,
            "integrated_generated_heat_j": integrated_generated,
            "integrated_outward_heat_j": integrated_boundary,
            "raw_integrated_energy_balance_j": integrated_generated-integrated_boundary-change})
    return data
