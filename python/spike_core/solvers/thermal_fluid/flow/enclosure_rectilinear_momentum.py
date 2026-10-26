# SPDX-License-Identifier: Apache-2.0
"""Experimental stationary-wall, obstacle-bearing rectilinear MAC momentum.

Integrated primal/dual finite volumes; no prolongation, turbulence or rotors.
See docs/validation/ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md.
"""
from collections.abc import Mapping
import math

import numpy as np
from scipy.sparse import bmat, coo_matrix, diags, issparse, lil_matrix
from scipy.sparse.linalg import LinearOperator, onenormest, splu

from .enclosure_refinement import _validate_built_grid
from .enclosure_stokes import EnclosureFlowError, _number

CONTRACT = "spike/enclosure-rectilinear-momentum/v1"
RESULT_CONTRACT = "spike/enclosure-rectilinear-momentum-result/v1"
MAX_CELLS = 4096
MAX_REYNOLDS_BOUND = 20.
MAX_METRIC_RATIO = 64.
MAX_CONDITION_ESTIMATE = 1e10


def _norm(values):
    """Euclidean norm without squaring a dimensional tiny/huge scale."""
    scale = float(np.max(np.abs(values), initial=0.))
    return scale * float(np.linalg.norm(values / scale)) if scale else 0.


def _power(left, right):
    # BLAS dot does not obey numpy.errstate; explicit products fail on underflow.
    return float(np.sum(np.multiply(left, right)))


def _shift(cell, axis, step):
    result = list(cell)
    result[axis] += step
    return tuple(result)


def _inputs(request):
    keys = {"contract", "grid", "fluid_mask", "body_force_n_m3",
            "dynamic_viscosity_pa_s", "density_kg_m3", "nonlinear_controls"}
    if not isinstance(request, Mapping) or set(request) != keys or request["contract"] != CONTRACT:
        raise EnclosureFlowError("Invalid rectilinear momentum contract or fields")
    grid = request["grid"]
    shape, _, _, _, _, widths, _ = _validate_built_grid(grid)
    if math.prod(shape) > MAX_CELLS:
        raise EnclosureFlowError("Momentum grid exceeds 4096 cells")
    smallest = min(float(h.min()) for h in widths)
    largest = max(float(h.max()) for h in widths)
    if largest / smallest > MAX_METRIC_RATIO:
        raise EnclosureFlowError("Momentum metric ratio exceeds 64")
    mask = np.asarray(request["fluid_mask"])
    if mask.shape != shape or mask.dtype.kind != "b" or not mask.any():
        raise EnclosureFlowError("fluid_mask must be a nonempty fine-grid Boolean array")
    raw = np.asarray(request["body_force_n_m3"])
    if raw.shape != shape + (3,) or raw.dtype.kind not in "iuf":
        raise EnclosureFlowError("body_force_n_m3 requires a fine-grid real three-vector")
    force = raw.astype(float)
    if not np.isfinite(force).all():
        raise EnclosureFlowError("Body force must be finite")
    mu = _number(request["dynamic_viscosity_pa_s"], "viscosity")
    rho = _number(request["density_kg_m3"], "density")
    controls = request["nonlinear_controls"]
    if not isinstance(controls, Mapping) or set(controls) != {
            "max_iterations", "relaxation", "relative_tolerance"}:
        raise EnclosureFlowError("Invalid nonlinear_controls")
    iterations = controls["max_iterations"]
    if type(iterations) is not int or not 1 <= iterations <= 100:
        raise EnclosureFlowError("max_iterations must be an integer from 1 to 100")
    for name, low, high in (("relaxation", .1, 1.), ("relative_tolerance", 1e-12, 1e-7)):
        value = controls[name]
        if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
            raise EnclosureFlowError(f"{name} must be finite in [{low}, {high}]")
    return grid, mask, force, mu, rho, controls


def _assemble(grid, mask, force, mu, cancel_check=None):
    """Integrated diffusion K, signed flux B and dual-volume force F."""
    widths = grid["cell_widths_m"]
    cells = [tuple(c) for c in np.argwhere(mask)]
    ids = {cell: i for i, cell in enumerate(cells)}
    faces = [(a, c, _shift(c, a, 1)) for c in cells for a in range(3)
             if _shift(c, a, 1) in ids]
    face_ids = {(a, c): i for i, (a, c, _) in enumerate(faces)}
    size = len(faces)
    k = lil_matrix((size, size))
    b = lil_matrix((len(cells), size))
    force_integral, dual_volumes = np.zeros(size), np.zeros(size)
    cell_volumes = np.array([grid["cell_volumes_m3"][c] for c in cells])
    adjacency = [[] for _ in cells]
    areas = np.array([math.prod(widths[d][c[d]] for d in range(3) if d != a)
                      for a, c, _ in faces])
    interfaces = []

    def flux_terms(axis, lower):
        j = face_ids.get((axis, lower))
        return [] if j is None else [(j, .5 * areas[j])]

    for i, (axis, c, other) in enumerate(faces):
        if cancel_check and cancel_check():
            raise InterruptedError()
        area = areas[i]
        dual_volumes[i] = .5 * (cell_volumes[ids[c]] + cell_volumes[ids[other]])
        force_integral[i] = .5 * (cell_volumes[ids[c]] * force[c][axis]
                                   + cell_volumes[ids[other]] * force[other][axis])
        b[ids[c], i], b[ids[other], i] = area, -area
        adjacency[ids[c]].append(ids[other])
        adjacency[ids[other]].append(ids[c])
        for direction in range(3):
            for sign in (-1, 1):
                neighbor = _shift(c, direction, sign)
                j = face_ids.get((axis, neighbor))
                if direction == axis:
                    shared_cell = other if sign > 0 else c
                    coefficient = mu * area / widths[axis][shared_cell[axis]]
                    terms = (flux_terms(axis, _shift(shared_cell, axis, -1))
                             + flux_terms(axis, shared_cell))
                else:
                    # Split each dual side into its two adjacent primal halves.
                    remaining = 3 - axis - direction
                    coefficient = 0.
                    for half_cell in (c, other):
                        half_area = .5 * widths[axis][half_cell[axis]] * widths[remaining][c[remaining]]
                        next_cell = _shift(half_cell, direction, sign)
                        distance = .5 * widths[direction][c[direction]]
                        if next_cell in ids:
                            distance += .5 * widths[direction][next_cell[direction]]
                        coefficient += mu * half_area / distance
                    base = c if sign > 0 else neighbor
                    terms = flux_terms(direction, base) + flux_terms(direction, _shift(base, axis, 1))
                k[i, i] += coefficient
                if j is not None:
                    k[i, j] -= coefficient
                if j is None or sign > 0:
                    interfaces.append((i, j, sign, terms))
    gauges, seen = [], set()
    for i in range(len(cells)):
        if i in seen:
            continue
        gauges.append(i)
        todo = [i]
        seen.add(i)
        while todo:
            for j in adjacency[todo.pop()]:
                if j not in seen:
                    seen.add(j)
                    todo.append(j)
    return {"cells": cells, "faces": faces, "K": k.tocsr(), "B": b.tocsr(),
            "F": force_integral, "dual_volumes": dual_volumes,
            "cell_volumes": cell_volumes, "gauges": gauges, "interfaces": interfaces}


def _advection(system, velocity, rho):
    """Conservative central dual flux; C+C.T = rho diag(dual imbalance)."""
    rows, cols, data = [], [], []
    imbalance = np.zeros(len(velocity))
    for i, j, sign, terms in system["interfaces"]:
        flux = sign * sum(weight * velocity[index] for index, weight in terms)
        imbalance[i] += flux
        if j is not None:
            imbalance[j] -= flux
            rows.extend((i, j))
            cols.extend((j, i))
            data.extend((.5 * rho * flux, -.5 * rho * flux))
    rows.extend(range(len(velocity)))
    cols.extend(range(len(velocity)))
    data.extend(.5 * rho * imbalance)
    return (coo_matrix((data, (rows, cols)), shape=(len(velocity), len(velocity))).tocsr(),
            imbalance)


def _iteration(system, rho, controls, length, extent, mu, cancel_check, *, linear_skew=None):
    """Iterate momentum with an optional integrated, work-free linear term.

    ``linear_skew`` is already volume-integrated. Its pointwise counterpart
    M^-1*linear_skew is skew-adjoint in the dual-volume M inner product.
    """
    k, b, force = system["K"], system["B"], system["F"]
    if linear_skew is not None:
        if (not issparse(linear_skew) or linear_skew.shape != k.shape
                or linear_skew.dtype.kind not in "iuf"):
            raise EnclosureFlowError("linear_skew must be a real sparse matrix matching momentum")
        linear_skew = linear_skew.astype(float).tocsr(copy=True)
        if not np.isfinite(linear_skew.data).all():
            raise EnclosureFlowError("linear_skew must be finite")
        scale = float(np.max(np.abs(linear_skew.data), initial=0.))
        symmetry = (linear_skew + linear_skew.T).data
        if scale and np.max(np.abs(symmetry / scale), initial=0.) > 32*np.finfo(float).eps:
            raise EnclosureFlowError("linear_skew is not skew-adjoint in the dual-volume inner product")
    active = [i for i in range(b.shape[0]) if i not in set(system["gauges"])]
    br = b[active]
    velocity, pressure = np.zeros(k.shape[0]), np.zeros(b.shape[0])
    rhs_norm = _norm(force / np.sqrt(system["dual_volumes"]))
    history, condition = [], 1.
    if k.shape[0] == 0:
        return velocity, pressure, _advection(system, velocity, rho)[0], {
            "iterations": 0, "momentum_residual_history": [0.],
            "momentum_relative_residual": 0., "maximum_divergence_s_inv": 0.,
            "reynolds_upper_bound": 0., "scaled_condition_estimate": 1.}
    velocity_scale = 1 / np.sqrt(k.diagonal())
    s = diags(velocity_scale)
    bs = br @ s
    pressure_scale = 1 / np.sqrt(np.asarray(bs.multiply(bs).sum(axis=1)).ravel())
    t = diags(pressure_scale)
    coupling = t @ bs
    for iteration in range(1, controls["max_iterations"] + 1):
        if cancel_check and cancel_check():
            raise InterruptedError()
        convection, _ = _advection(system, velocity, rho)
        if linear_skew is not None:
            convection = convection + linear_skew
        matrix = bmat([[s @ (k + convection) @ s, -coupling.T],
                       [-coupling, None]], format="csc")
        lu = splu(matrix)
        solution = lu.solve(np.r_[velocity_scale * force, np.zeros(len(active))])
        if not np.isfinite(solution).all():
            raise EnclosureFlowError("Nonfinite Oseen solution")
        omega = controls["relaxation"]
        velocity = (1 - omega) * velocity + omega * velocity_scale * solution[:len(velocity)]
        pressure[active] = ((1 - omega) * pressure[active]
                            + omega * pressure_scale * solution[len(velocity):])
        convection, imbalance = _advection(system, velocity, rho)
        if linear_skew is not None:
            convection = convection + linear_skew
        residual_norm = _norm(((k + convection) @ velocity - b.T @ pressure - force)
                              / np.sqrt(system["dual_volumes"]))
        residual = residual_norm / rhs_norm if rhs_norm else (0. if residual_norm == 0. else math.inf)
        divergence = float(np.max(np.abs(b @ velocity / system["cell_volumes"]), initial=0))
        speed = float(np.max(np.abs(velocity), initial=0))
        reynolds = rho * math.sqrt(3) * speed * extent / mu
        if not all(math.isfinite(v) for v in (residual, divergence, reynolds)):
            raise EnclosureFlowError("Nonfinite momentum diagnostics")
        history.append(residual)
        scale = max(speed, float(np.max(np.abs(force / k.diagonal()), initial=0)))
        if residual <= controls["relative_tolerance"] and divergence <= 1e-9 * scale / length:
            inverse = LinearOperator(matrix.shape, matvec=lu.solve,
                                     rmatvec=lambda x: lu.solve(x, trans="T"),
                                     matmat=lu.solve, dtype=float)
            condition = float(np.max(np.asarray(abs(matrix).sum(axis=0)))) * float(onenormest(inverse, t=1))
            if not math.isfinite(condition) or condition > MAX_CONDITION_ESTIMATE:
                raise EnclosureFlowError("Scaled saddle system condition estimate exceeds 1e10")
            if np.max(np.abs(imbalance / system["dual_volumes"]), initial=0) > 1e-9 * scale / length:
                raise EnclosureFlowError("Dual mass-flux consistency check failed")
            break
    else:
        raise EnclosureFlowError("Steady nonlinear iteration did not converge")
    if reynolds > MAX_REYNOLDS_BOUND:
        raise EnclosureFlowError("Reynolds upper bound exceeds experimental admission of 20")
    return velocity, pressure, convection, {
        "iterations": iteration, "momentum_residual_history": history,
        "momentum_relative_residual": residual, "maximum_divergence_s_inv": divergence,
        "reynolds_upper_bound": reynolds, "scaled_condition_estimate": condition}


def solve_enclosure_rectilinear_momentum(request, *, cancel_check=None):
    """Solve actual refined momentum unknowns; blocked results contain no fields.

    The in-process grid is the validated result of build_enclosure_grid.
    Sparse LU and norm estimation cannot be cancelled inside their calls.
    """
    result = {"contract": RESULT_CONTRACT, "production_qualified": False,
              "scope": "closed_rectilinear_voxel_constant_property_steady_inertial_flow"}
    try:
        if cancel_check and cancel_check():
            raise InterruptedError()
        with np.errstate(over="raise", divide="raise", invalid="raise", under="raise"):
            grid, mask, force, mu, rho, controls = _inputs(request)
            system = _assemble(grid, mask, force, mu, cancel_check)
            length = min(float(h.min()) for h in grid["cell_widths_m"])
            extent = max(float(axis[-1] - axis[0]) for axis in grid["axes_m"])
            velocity, pressure, convection, diagnostics = _iteration(
                system, rho, controls, length, extent, mu, cancel_check)
            work = _power(system["F"], velocity)
            dissipation = _power(velocity, system["K"] @ velocity)
            advective = _power(velocity, convection @ velocity)
            pressure_power = -_power(velocity, system["B"].T @ pressure)
            scale = max(abs(work), abs(dissipation),
                        float(np.multiply(_norm(system["F"]), _norm(velocity))))
            defect = abs(work - dissipation - advective - pressure_power) / scale if scale else 0.
            if (not all(math.isfinite(x) for x in (work, dissipation, advective, pressure_power, defect))
                    or defect > max(10 * controls["relative_tolerance"], 1e-9)):
                raise EnclosureFlowError("Weighted kinetic-energy identity failed")
            fields = []
            for axis in range(3):
                face_shape = list(grid["shape"])
                face_shape[axis] += 1
                fields.append(np.zeros(face_shape))
            for value, (axis, c, _) in zip(velocity, system["faces"]):
                fields[axis][_shift(c, axis, 1)] = value
            p = np.zeros(grid["shape"])
            for cell, value in zip(system["cells"], pressure):
                p[cell] = value
            diagnostics.update(force_work_w=work, viscous_dissipation_w=dissipation,
                               advective_power_w=advective, pressure_power_w=pressure_power,
                               relative_energy_defect=defect, fluid_cells=len(system["cells"]),
                               velocity_unknowns=len(velocity), fluid_components=len(system["gauges"]),
                               momentum_grid_shape=list(grid["shape"]),
                               momentum_grid_kind="tensor_plane_rectilinear_not_octree")
        if cancel_check and cancel_check():
            raise InterruptedError()
        result.update(status="completed", fields={"face_velocity_m_s": [f.tolist() for f in fields],
                                                 "pressure_pa": p.tolist()}, diagnostics=diagnostics)
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "CANCELLED", "message": "Momentum solve cancelled"}])
    except (ValueError, TypeError, ArithmeticError, RuntimeError) as exc:
        result.update(status="blocked", issues=[{"code": "ENCLOSURE_RECTILINEAR_MOMENTUM_REJECTED",
                                                "message": str(exc)}])
    return result
