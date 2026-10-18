# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original P1 ambient radiation weak form and bounded Newton iteration.

For affine T on a triangle, integrate N_i*epsilon*sigma*(T^4-Tr^4)
and its derivative 4*N_i*N_j*epsilon*sigma*T^3 exactly (degree five).
The Duffy map (u,v)->(u,(1-u)*v) and four-point Gauss rules integrate
these polynomials exactly, including the Jacobian. Positive weights and
positive Kelvin imply a positive semidefinite boundary Jacobian. This is
prescribed infinite isothermal surroundings, not enclosure radiosity or CFD.
"""
import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import cg

from .assembly_tetra_thermal_validation import require

SIGMA = 5.670374419e-8  # W/(m^2 K^4), rounded SI Stefan-Boltzmann constant
MAX_NEWTON_ITERATIONS = 80
MAX_TEMPERATURE_K = 10000.0  # bounded numerical envelope, not material validity
_x, _w = np.polynomial.legendre.leggauss(4)
_x, _w = (_x + 1) / 2, _w / 2
SHAPES = np.array([[1-u-(1-u)*v, u, (1-u)*v] for u in _x for v in _x])
WEIGHTS = np.array([2*wu*wv*(1-u) for u, wu in zip(_x, _w) for wv in _w])


def radiation_operator(temperatures, faces):
    """Return outward nodal heat (W) and consistent tangent (W/K)."""
    n = len(temperatures)
    power = np.zeros(n)
    rows, columns, values = [], [], []
    for nodes, area, emissivity, ambient in faces:
        local = temperatures[list(nodes)]
        t = SHAPES @ local
        factor = area * emissivity * SIGMA * WEIGHTS
        # Factored difference avoids catastrophic subtraction near equilibrium.
        net = (t-ambient)*(t+ambient)*(t*t+ambient*ambient)
        power[list(nodes)] += SHAPES.T @ (factor * net)
        tangent = SHAPES.T @ ((4*factor*t**3)[:, None] * SHAPES)
        for i, row in enumerate(nodes):
            for j, column in enumerate(nodes):
                rows.append(row)
                columns.append(column)
                values.append(tangent[i, j])
    return power, coo_matrix((values, (rows, columns)), shape=(n, n)).tocsr()


def solve_radiation(matrix, load, fixed, free, temperatures, faces):
    """Damped Newton with 80 steps and 30 backtracks; accept true residual."""
    temperatures[free] = np.mean([entry[3] for entry in faces])
    require(np.all(temperatures > 0) and np.all(temperatures <= MAX_TEMPERATURE_K),
            "Radiation temperature range must be (0, 10000] K.")
    scale = max(float(np.linalg.norm(load[free])),
                float(np.linalg.norm(matrix[free][:, fixed] @ temperatures[fixed])), 1e-30)
    scale = max(scale, sum(area*emissivity*SIGMA*ambient**4 for _, area, emissivity, ambient in faces),
                float(np.linalg.norm(matrix @ temperatures)), 1e-30)
    cg_iterations = 0
    for iteration in range(MAX_NEWTON_ITERATIONS + 1):
        power, tangent = radiation_operator(temperatures, faces)
        residual = matrix @ temperatures + power - load
        norm = float(np.linalg.norm(residual[free]))
        if norm / scale <= 1e-10:
            return temperatures, power, iteration, cg_iterations, norm / scale
        require(iteration < MAX_NEWTON_ITERATIONS, "Bounded radiation Newton iteration did not converge.")
        operator = (matrix + tangent)[free][:, free]
        diagonal = operator.diagonal()
        require(np.isfinite(diagonal).all() and np.all(diagonal > 0), "Nonpositive radiation tangent.")
        scaling = 1 / np.sqrt(diagonal)
        def count(_):
            nonlocal cg_iterations
            cg_iterations += 1
        step, info = cg(diags(scaling) @ operator @ diags(scaling),
                        -scaling * residual[free], rtol=1e-12, atol=0,
                        maxiter=min(100000, max(1000, 20*len(free))), callback=count)
        require(info == 0 and np.isfinite(step).all(), "Bounded radiation tangent iteration did not converge.")
        step *= scaling
        accepted = False
        for backtrack in range(30):
            alpha = 0.5 ** backtrack
            candidate = temperatures.copy()
            candidate[free] += alpha * step
            if np.any(candidate <= 0) or np.any(candidate > MAX_TEMPERATURE_K):
                continue
            candidate_power, _ = radiation_operator(candidate, faces)
            candidate_norm = float(np.linalg.norm((matrix @ candidate + candidate_power-load)[free]))
            if candidate_norm <= (1-1e-4*alpha)*norm:
                temperatures = candidate
                accepted = True
                break
        require(accepted, "Radiation Newton line search failed or temperature range exceeded.")
