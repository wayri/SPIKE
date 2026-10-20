# SPDX-License-Identifier: Apache-2.0
"""Continuous 3-D advective thermal MMS with an independently authored oracle.

On the unit cube, rho=cp=k=mu=1 in SI units and T=300+theta with
theta=sin(pi*x)^2*sin(pi*y)*sin(pi*z). Every wall is held at 300 K.
Use the separate analytical curl-velocity/continuum-force oracle from the
laminar verification; it does not call the discrete momentum assembler.
Writing sx=sin(pi*x), cx=cos(pi*x), etc., differentiation gives

  grad(theta) = (2*pi*sx*cx*sy*sz, pi*sx^2*cy*sz, pi*sx^2*sy*cz)
  -lap(theta) = 2*pi^2*(sx^2-cos(2*pi*x))*sy*sz.

Steady incompressible sensible energy is -lap(T)+u.grad(T)=q, hence the
cell-sampled continuum source is q=-lap(theta)+u.grad(theta). These expressions
are independently differentiated tensor functions, not discrete source fitting.
The actual composed flow/thermal solver, including upwind thermal transport,
must recover this field under global refinement. Nonzero advection is checked.
This is synthetic verification, not measured physical validation.

Retained failed diagnostic (20 October 2026, not qualified): an earlier
theta=sin(pi*x)*sin(pi*y)*sin(pi*z) had relative errors
0.030108719796317806, 0.014144882215052201, 0.011262719113810956 on 4/8/12
cells per axis. Its orders 1.0899012034777529 and 0.5619590817653167 failed
the unchanged >=0.7 gate. That theta was tangent to the chosen curl flow:
u.grad(theta)=0 analytically (sample maximum 1.02e-15). It does not establish
nonzero continuum advective transport. No claim is made that this earlier
case passed. The present non-tangent case keeps the >=0.7 order and <0.1
finest-grid relative-temperature-rise-error gates.
"""
import math
import unittest

import numpy as np

from python.spike_core.enclosure_cht import solve_enclosure_cht
from tests.python.test_enclosure_cht import fixture
from tests.python.test_enclosure_laminar import exact_fields


def manufactured_advection(n):
    """Return exact input, executed result and independent comparison data."""
    request = fixture((n, n, n))
    request["grid"]["spacing_m"] = [1/n]*3
    request["flow"]["model"] = "laminar_inertial"
    request["flow"]["nonlinear_controls"] = {
        "max_iterations": 60, "relaxation": 1., "relative_tolerance": 1e-10}
    centers = (np.arange(n)+.5)/n
    xyz = np.meshgrid(centers, centers, centers, indexing="ij")
    velocity, force, _ = exact_fields(xyz, amplitude=1.)
    x, y, z = xyz
    pi = np.pi
    sx, sy, sz = np.sin(pi*x), np.sin(pi*y), np.sin(pi*z)
    cx, cy, cz = np.cos(pi*x), np.cos(pi*y), np.cos(pi*z)
    theta = sx*sx*sy*sz
    gradient = np.stack((2*pi*sx*cx*sy*sz, pi*sx*sx*cy*sz, pi*sx*sx*sy*cz), axis=-1)
    advection = np.sum(velocity*gradient, axis=-1)
    heat = 2*pi*pi*(sx*sx-np.cos(2*pi*x))*sy*sz + advection
    request["flow"]["body_force_n_m3"] = force.tolist()
    request["heat_sources_w_m3"] = heat.tolist()
    result = solve_enclosure_cht(request)
    if result["status"] != "completed":
        raise AssertionError(result)
    actual = np.asarray(result["fields"]["temperature_k"])-300.
    metrics = {
        "n": n,
        "relative_temperature_rise_l2_error": float(np.linalg.norm(actual-theta)/np.linalg.norm(theta)),
        "maximum_analytical_advection_w_m3": float(np.max(np.abs(advection))),
        "independent_generated_heat_w": float(np.sum(heat)/n**3),
    }
    return request, result, metrics


class EnclosureChtAdvectionTests(unittest.TestCase):
    def test_nonzero_continuum_advection_spatial_convergence(self):
        errors = []
        for n in (4, 8, 12):
            with self.subTest(n=n):
                _, result, metrics = manufactured_advection(n)
                errors.append(metrics["relative_temperature_rise_l2_error"])
                self.assertFalse(result["production_qualified"])
                self.assertEqual(result["model_status"], "experimental")
                self.assertGreater(metrics["maximum_analytical_advection_w_m3"], 1.)
                flow = result["flow_diagnostics"]
                energy = result["energy_diagnostics"]
                self.assertGreater(flow["reynolds_upper_bound"], 2.)
                self.assertLessEqual(flow["momentum_relative_residual"], 1e-10)
                self.assertLess(flow["relative_energy_defect"], 1e-9)
                fields = [np.asarray(v) for v in result["fields"]["face_velocity_m_s"]]
                # Independently recompute every cell's mass balance from emitted faces.
                divergence = sum(np.diff(values, axis=axis)*n for axis, values in enumerate(fields))
                self.assertLess(float(np.max(np.abs(divergence))), 1e-10)
                for axis, values in enumerate(fields):
                    np.testing.assert_array_equal(np.take(values, (0, n), axis=axis), 0.)
                self.assertLess(result["transfer_diagnostics"]["maximum_fine_divergence_s_inv"], 1e-10)
                generated = metrics["independent_generated_heat_w"]
                self.assertAlmostEqual(energy["generated_heat_w"], generated, delta=1e-12)
                outward = math.fsum(energy["outward_heat_w"].values())
                self.assertLess(abs(generated-outward), 1e-10*max(abs(generated), 1.))
                self.assertLess(energy["relative_energy_balance"], 1e-9)
                self.assertLess(energy["maximum_row_scaled_residual_k"], 1e-10)
        self.assertLess(errors[-1], .1)
        for index, ratio in enumerate((2., 1.5)):
            order = math.log(errors[index]/errors[index+1])/math.log(ratio)
            self.assertGreaterEqual(order, .7, (errors, order))


if __name__ == "__main__":
    unittest.main()
