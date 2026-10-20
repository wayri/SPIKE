# SPDX-License-Identifier: Apache-2.0
"""Independent continuum manufactured inertia around a re-entrant obstacle.

The fluid is [0,1]^3 minus x>=1/2,y>=1/2. A polynomial streamfunction
vanishes with its first derivatives on every wall, including the obstacle.
Forcing uses continuous polynomial derivatives, not the discrete assembler.
The n=8,12,16 order>=0.8 and finest error<0.12 gates were fixed before the
n=16 result was observed. A preceding rho=1,n=4 coarse probe had order~0.49
to n=8 and is retained as pre-asymptotic evidence, not a passed order test.
"""
import unittest

import numpy as np
from numpy.polynomial import Polynomial

from python.spike_core.enclosure_rectilinear_momentum import (
    CONTRACT, solve_enclosure_rectilinear_momentum,
)
from python.spike_core.enclosure_refinement import build_enclosure_grid


_T = Polynomial([0., 1.])
_A = _T**2 * (1-_T)**2 * (_T-.5)**2
_C = _T**2 * (1-_T)**2
_AMPLITUDE = 1e4
_DENSITY = 100.


def exact_fields(points):
    """Return velocity, full force and inertial force in SI (mu=1 Pa s)."""
    x, y, z = points
    a = [_A.deriv(i)(x) for i in range(4)]
    b = [_A.deriv(i)(y) for i in range(4)]
    c = [_C.deriv(i)(z) for i in range(3)]
    u = _AMPLITUDE*a[0]*b[1]*c[0]
    v = -_AMPLITUDE*a[1]*b[0]*c[0]
    ux, uy = _AMPLITUDE*a[1]*b[1]*c[0], _AMPLITUDE*a[0]*b[2]*c[0]
    vx, vy = -_AMPLITUDE*a[2]*b[0]*c[0], -_AMPLITUDE*a[1]*b[1]*c[0]
    inertia = _DENSITY*np.stack((u*ux+v*uy, u*vx+v*vy, np.zeros_like(u)), axis=-1)
    laplacian = _AMPLITUDE*np.stack((
        a[2]*b[1]*c[0]+a[0]*b[3]*c[0]+a[0]*b[1]*c[2],
        -(a[3]*b[0]*c[0]+a[1]*b[2]*c[0]+a[1]*b[0]*c[2]),
        np.zeros_like(u)), axis=-1)
    return np.stack((u, v, np.zeros_like(u)), axis=-1), inertia-laplacian, inertia


def continuum_run(n):
    grid = build_enclosure_grid({
        "shape": [n]*3, "spacing_m": [1/n]*3,
        "origin_m": [0.]*3, "local_refinement": [],
    })
    xyz = np.meshgrid(*grid["cell_centers_m"], indexing="ij")
    mask = ~((xyz[0] >= .5) & (xyz[1] >= .5))
    _, force, inertia = exact_fields(xyz)
    force[~mask] = 0.
    result = solve_enclosure_rectilinear_momentum({
        "contract": CONTRACT, "grid": grid, "fluid_mask": mask,
        "body_force_n_m3": force, "density_kg_m3": _DENSITY,
        "dynamic_viscosity_pa_s": 1.,
        "nonlinear_controls": {
            "max_iterations": 100, "relaxation": 1.,
            "relative_tolerance": 1e-10,
        },
    })
    if result["status"] != "completed":
        raise AssertionError(result)
    error, norm = 0., 0.
    for axis in range(3):
        coordinates = list(grid["cell_centers_m"])
        coordinates[axis] = grid["axes_m"][axis]
        reference = exact_fields(np.meshgrid(*coordinates, indexing="ij"))[0][..., axis]
        actual = np.asarray(result["fields"]["face_velocity_m_s"][axis])
        allowed = np.zeros_like(actual, dtype=bool)
        lower, upper, inside = [[slice(None)]*3 for _ in range(3)]
        lower[axis], upper[axis], inside[axis] = slice(None, -1), slice(1, None), slice(1, -1)
        allowed[tuple(inside)] = mask[tuple(lower)] & mask[tuple(upper)]
        reference[~allowed] = 0.
        np.testing.assert_array_equal(actual[~allowed], 0.)
        # Independent normal trapezoidal/tangential cell-width quadrature.
        weights = list(grid["cell_widths_m"])
        weights[axis] = np.r_[weights[axis][0]/2,
                              (weights[axis][:-1]+weights[axis][1:])/2,
                              weights[axis][-1]/2]
        volume = weights[0][:, None, None]*weights[1][None, :, None]*weights[2][None, None, :]
        error += np.sum(volume*(actual-reference)**2)
        norm += np.sum(volume*reference**2)
    inertia_norm = float(np.linalg.norm(inertia[mask]))
    viscous_norm = float(np.linalg.norm((force-inertia)[mask]))
    return float(np.sqrt(error/norm)), result["diagnostics"], inertia_norm/viscous_norm


class ObstacleContinuumTests(unittest.TestCase):
    def test_reentrant_obstacle_continuum_inertia_refinement(self):
        levels = (8, 12, 16)
        runs = [continuum_run(n) for n in levels]
        errors = [run[0] for run in runs]
        for i in range(2):
            order = np.log(errors[i]/errors[i+1])/np.log(levels[i+1]/levels[i])
            self.assertGreaterEqual(order, .8, (errors, order))
        self.assertLess(errors[-1], .12, errors)
        for _, diagnostics, inertia_ratio in runs:
            self.assertGreater(inertia_ratio, 0.)
            self.assertGreater(diagnostics["reynolds_upper_bound"], 1.)
            self.assertLessEqual(diagnostics["reynolds_upper_bound"], 20.)
            self.assertLess(diagnostics["momentum_relative_residual"], 1e-10)
            self.assertLess(diagnostics["relative_energy_defect"], 1e-9)
            self.assertEqual(diagnostics["fluid_components"], 1)


if __name__ == "__main__":
    unittest.main()
