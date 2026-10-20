# SPDX-License-Identifier: Apache-2.0
"""Experimental full-box rectilinear MAC flow with prescribed variable viscosity.

The integrated operator is E.T W E for normal strains at cells and symmetric
shears at edges. Cross-component terms are retained. No turbulence state is
modeled, and obstacles are rejected. See the symmetric-stress method record.
"""
from collections.abc import Mapping
from itertools import combinations, product
import math

import numpy as np
from scipy.sparse import coo_matrix, diags

from .enclosure_rectilinear_momentum import (
    CONTRACT as BASE_CONTRACT, _assemble, _inputs, _iteration, _norm, _power,
)
from .enclosure_stokes import EnclosureFlowError

CONTRACT = "spike/enclosure-symmetric-stress/v1"
RESULT_CONTRACT = "spike/enclosure-symmetric-stress-result/v1"


def _stress_operator(grid, system, viscosity, cancel_check=None):
    """Return integrated stress K and independently inspectable strain factors.

    Internal helper: callers first admit a complete full-box topology and
    positive cell viscosity. No obstacle/cut-cell strain stencil is inferred.
    """
    shape, widths = grid["shape"], grid["cell_widths_m"]
    face_ids = {(axis, cell): i for i, (axis, cell, _) in enumerate(system["faces"])}
    rows, columns, values, weights = [], [], [], []

    def add_strain(terms, weight):
        if not terms:
            return
        row = len(weights)
        for column, value in terms:
            rows.append(row)
            columns.append(column)
            values.append(value)
        weights.append(weight)

    def face_term(component, lower_cell, coefficient):
        index = face_ids.get((component, tuple(lower_cell)))
        return [] if index is None else [(index, coefficient)]

    # The normal velocity difference spans its primal cell, including exact
    # zero normal velocities at exterior walls.
    for cell in system["cells"]:
        if cancel_check and cancel_check():
            raise InterruptedError()
        for axis in range(3):
            lower = list(cell)
            lower[axis] -= 1
            terms = face_term(axis, lower, -1/widths[axis][cell[axis]])
            terms += face_term(axis, cell, 1/widths[axis][cell[axis]])
            add_strain(terms, 2*viscosity[cell]*grid["cell_volumes_m3"][cell])
    normal_rows = len(weights)

    # For pair (a,b), edge coordinates are primal cuts in a,b and a cell center
    # in c. The dual edge volume comprises adjacent quarter-cell pieces.
    for a, b in combinations(range(3), 2):
        c = 3-a-b
        for ia, ib, ic in product(range(shape[a]+1), range(shape[b]+1), range(shape[c])):
            if cancel_check and cancel_check():
                raise InterruptedError()
            neighbors_a = [j for j in (ia-1, ia) if 0 <= j < shape[a]]
            neighbors_b = [j for j in (ib-1, ib) if 0 <= j < shape[b]]
            da = .5*sum(widths[a][j] for j in neighbors_a)
            db = .5*sum(widths[b][j] for j in neighbors_b)
            terms = []
            # d(u_a)/dx_b + d(u_b)/dx_a. Half-width wall distances encode
            # odd no-slip tangential ghost values without unknown ghosts.
            for jb, sign in ((ib-1, -1.), (ib, 1.)):
                cell = [0]*3
                cell[a], cell[b], cell[c] = ia-1, jb, ic
                terms += face_term(a, cell, sign/db)
            for ja, sign in ((ia-1, -1.), (ia, 1.)):
                cell = [0]*3
                cell[a], cell[b], cell[c] = ja, ib-1, ic
                terms += face_term(b, cell, sign/da)
            weight = 0.
            for ja, jb in product(neighbors_a, neighbors_b):
                cell = [0]*3
                cell[a], cell[b], cell[c] = ja, jb, ic
                weight += (viscosity[tuple(cell)]*.25
                           * widths[a][ja]*widths[b][jb]*widths[c][ic])
            add_strain(terms, weight)
    strain = coo_matrix((values, (rows, columns)),
                       shape=(len(weights), len(system["faces"]))).tocsr()
    weights = np.asarray(weights)
    if (not np.isfinite(strain.data).all() or not np.isfinite(weights).all()
            or np.any(weights <= 0.)):
        raise EnclosureFlowError("Unrepresentable symmetric-stress strain weights")
    stiffness = (strain.T @ diags(weights) @ strain).tocsr()
    if not np.isfinite(stiffness.data).all() or np.any(stiffness.diagonal() <= 0.):
        raise EnclosureFlowError("Invalid symmetric-stress stiffness")
    return stiffness, strain, weights, normal_rows


def solve_enclosure_symmetric_stress(request, *, cancel_check=None):
    """Execute a coupled pressure/velocity solve; not a closure postprocessor."""
    result = {"contract": RESULT_CONTRACT, "production_qualified": False,
              "model_status": "experimental",
              "scope": "closed_full_box_prescribed_variable_viscosity_inertial_flow"}
    try:
        if cancel_check and cancel_check():
            raise InterruptedError()
        if not isinstance(request, Mapping) or request.get("contract") != CONTRACT:
            raise EnclosureFlowError("Invalid symmetric-stress contract")
        with np.errstate(over="raise", divide="raise", invalid="raise", under="raise"):
            viscosity = np.asarray(request.get("dynamic_viscosity_pa_s"))
            if (viscosity.dtype.kind not in "iuf" or viscosity.ndim != 3
                    or not np.isfinite(viscosity).all() or np.any(viscosity <= 0.)):
                raise EnclosureFlowError("Viscosity must be a finite positive cell field")
            viscosity = viscosity.astype(float)
            minimum_mu = float(viscosity.min())
            base = {**request, "contract": BASE_CONTRACT,
                    "dynamic_viscosity_pa_s": minimum_mu}
            grid, mask, force, _, rho, controls = _inputs(base)
            if viscosity.shape != grid["shape"]:
                raise EnclosureFlowError("Viscosity shape must match the actual grid")
            if not mask.all() or min(grid["shape"]) < 2:
                raise EnclosureFlowError("Symmetric stress requires a full box; obstacles unsupported")
            system = _assemble(grid, mask, force, minimum_mu, cancel_check)
            stiffness, strain, weights, normal_rows = _stress_operator(
                grid, system, viscosity, cancel_check)
            system["K"] = stiffness
            length = min(float(h.min()) for h in grid["cell_widths_m"])
            extent = max(float(axis[-1]-axis[0]) for axis in grid["axes_m"])
            velocity, pressure, convection, diagnostics = _iteration(
                system, rho, controls, length, extent, minimum_mu, cancel_check)
            work = _power(system["F"], velocity)
            dissipation = _power(velocity, stiffness @ velocity)
            shear_rate = strain @ velocity
            strain_dissipation = _power(weights, np.multiply(shear_rate, shear_rate))
            advective = _power(velocity, convection @ velocity)
            pressure_power = -_power(velocity, system["B"].T @ pressure)
            scale = max(abs(work), abs(dissipation),
                        float(np.multiply(_norm(system["F"]), _norm(velocity))))
            defect = abs(work-dissipation-advective-pressure_power)/scale if scale else 0.
            strain_defect = abs(dissipation-strain_dissipation)/scale if scale else 0.
            if (not all(math.isfinite(x) for x in (
                    work, dissipation, strain_dissipation, advective, pressure_power, defect, strain_defect))
                    or max(defect, strain_defect) > max(10*controls["relative_tolerance"], 1e-9)):
                raise EnclosureFlowError("Symmetric-stress energy identity failed")
            fields = []
            for axis in range(3):
                face_shape = list(grid["shape"])
                face_shape[axis] += 1
                fields.append(np.zeros(face_shape))
            for value, (axis, cell, _) in zip(velocity, system["faces"]):
                index = list(cell)
                index[axis] += 1
                fields[axis][tuple(index)] = value
            diagnostics.update(
                force_work_w=work, viscous_dissipation_w=dissipation,
                strain_quadrature_dissipation_w=strain_dissipation,
                advective_power_w=advective, pressure_power_w=pressure_power,
                relative_energy_defect=defect, relative_strain_energy_defect=strain_defect,
                minimum_dynamic_viscosity_pa_s=minimum_mu,
                maximum_dynamic_viscosity_pa_s=float(viscosity.max()),
                reynolds_viscosity_basis="minimum_prescribed_molecular_viscosity",
                normal_strain_rows=normal_rows, symmetric_shear_rows=len(weights)-normal_rows,
                fluid_cells=len(system["cells"]), velocity_unknowns=len(velocity),
                viscosity_source="prescribed_cell_field_not_turbulence_closure")
        if cancel_check and cancel_check():
            raise InterruptedError()
        result.update(status="completed", fields={
            "face_velocity_m_s": [field.tolist() for field in fields],
            "pressure_pa": pressure.reshape(grid["shape"]).tolist()}, diagnostics=diagnostics,
            limitations=["Full rectilinear box only; no obstacles or moving boundaries",
                         "Prescribed viscosity, not transported turbulence or temperature feedback",
                         "No discontinuous-viscosity interface accuracy or measured validation",
                         "Reynolds upper bound <=20; no widened flow-regime admission",
                         "Sparse factorization needs process-level cancellation",
                         "Knowledgeable human numerical review required before release"])
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "CANCELLED",
                      "message": "Symmetric-stress solve cancelled"}])
    except (ValueError, TypeError, ArithmeticError, RuntimeError) as exc:
        result.update(status="blocked", issues=[{"code": "ENCLOSURE_SYMMETRIC_STRESS_REJECTED",
                      "message": str(exc)}])
    return result
