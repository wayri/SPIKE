# SPDX-License-Identifier: Apache-2.0
"""Independent continuous manufactured oracle for the fixed-velocity SA solve."""
import copy
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from spike_core.enclosure_refinement import build_enclosure_grid
from spike_core.enclosure_sa_transport import (
    CONTRACT, sa_noft2_coefficients, solve_enclosure_sa_transport,
)


def independent_source(q, nu, distance, omega, grad, laplacian, velocity):
    # Independently evaluate the continuum balance; no solver auxiliary or
    # discrete operator participates in the manufactured source.
    chi = q/nu
    fv1 = chi**3/(chi**3+7.1**3)
    bar = q*(1.-chi/(1.+chi*fv1))/(.41**2*distance**2)
    shat = np.empty_like(q)
    for index in np.ndindex(q.shape):
        s, b = float(omega[index]), float(bar[index])
        shat[index] = s+b if b >= -.7*s else s+s*(.49*s+.9*b)/(-.5*s-b)
    ratio = np.full(q.shape, 10.)
    np.divide(q, shat*.41**2*distance**2, out=ratio, where=shat != 0.)
    ratio = np.minimum(ratio, 10.)
    g = ratio+.3*(ratio**6-ratio)
    fw = g*((1.+2.**6)/(g**6+2.**6))**(1./6.)
    destruction = (.1355/.41**2+1.622/(2./3.))*fw*(q/distance)**2
    return (sum(u*dq for u, dq in zip(velocity, grad))-.1355*shat*q+destruction
            -((nu+q)*laplacian+1.622*sum(dq**2 for dq in grad))/(2./3.))


def manufactured_request(n, *, seed=.5, dimensional_scale=1., refined=False,
                         q_amplitude=.64):
    grid = build_enclosure_grid({
        "shape": [n, n, n], "spacing_m": [1./n]*3, "origin_m": [0., 0., 0.],
        "local_refinement": ([{"bounds_m": [[0., .5], [0., 1.], [0., 1.]],
                              "split_factor": 2}] if refined else [])})
    shape = grid["shape"]
    x, y, z = np.meshgrid(*grid["cell_centers_m"], indexing="ij")
    b = [t*(1.-t) for t in (x, y, z)]
    db = [1.-2.*t for t in (x, y, z)]
    f, df = [v**2 for v in b], [2.*a*v for a, v in zip(db, b)]
    ddf = [2.*a**2-4.*v for a, v in zip(db, b)]
    nu = .01*dimensional_scale
    amplitude = q_amplitude*dimensional_scale
    speed = 10.*dimensional_scale
    modulation = 1.+.5*x+.3*y
    exact = amplitude*b[0]*b[1]*b[2]*modulation
    grad = [amplitude*b[(a+1)%3]*b[(a+2)%3]
            *(db[a]*modulation+b[a]*(.5, .3, 0.)[a]) for a in range(3)]
    lap = amplitude*(-2.*(b[0]*b[1]+b[1]*b[2]+b[2]*b[0])*modulation
                     +b[1]*b[2]*db[0]+.6*b[0]*b[2]*db[1])
    analytical_velocity = [speed*f[0]*df[1]*f[2], -speed*df[0]*f[1]*f[2],
                           np.zeros(shape)]
    curl = [speed*df[0]*f[1]*df[2], speed*f[0]*df[1]*df[2],
            -speed*(ddf[0]*f[1]+f[0]*ddf[1])*f[2]]
    omega = np.sqrt(sum(c**2 for c in curl))
    distance = np.minimum.reduce([x, 1.-x, y, 1.-y, z, 1.-z])
    source = independent_source(exact, nu, distance, omega, grad, lap, analytical_velocity)
    axes, centers = grid["axes_m"], grid["cell_centers_m"]
    def poly(t):
        return (t*(1.-t))**2
    # Face-averaged streamfunction differences give exactly shared solenoidal
    # fluxes, independent of the SA assembler, including nonuniform cuts.
    face_u = speed * (poly(axes[0])[:, None, None]
                      * (np.diff(poly(axes[1]))/np.diff(axes[1]))[None, :, None]
                      * poly(centers[2])[None, None, :])
    face_v = -speed * ((np.diff(poly(axes[0]))/np.diff(axes[0]))[:, None, None]
                       * poly(axes[1])[None, :, None] * poly(centers[2])[None, None, :])
    face_w = np.zeros((shape[0], shape[1], shape[2]+1))
    return {"contract": CONTRACT, "grid": grid, "face_velocity_m_s": [face_u, face_v, face_w],
            "molecular_kinematic_viscosity_m2_s": nu,
            "initial_nu_tilde_m2_s": seed*exact,
            "manufactured_source_m2_s2": source,
            "nonlinear_controls": {"max_iterations": 60, "relative_tolerance": 1e-10,
                                   "relaxation": 1.}}, exact


class EnclosureSATransportTests(unittest.TestCase):
    def solve(self, request):
        result = solve_enclosure_sa_transport(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertTrue(result["research_only"])
        self.assertFalse(result["production_qualified"])
        self.assertLessEqual(result["diagnostics"]["steady_relative_residual"], 1e-10)
        return result, np.asarray(result["fields"]["nu_tilde_m2_s"])

    def test_continuous_manufactured_three_grid_convergence(self):
        errors = []
        for n in (4, 8, 12):
            request, exact = manufactured_request(n)
            result, q = self.solve(request)
            errors.append(float(np.linalg.norm(q-exact)/np.linalg.norm(exact)))
            self.assertGreater(result["diagnostics"]["maximum_eddy_kinematic_viscosity_m2_s"], 0.)
            self.assertGreater(result["diagnostics"]["iterations"], 0)
            self.assertEqual(result["diagnostics"]["positivity_clipping_count"], 0)
            self.assertGreater(float(q.min()), 0.)
        orders = [math.log(errors[i]/errors[i+1])/math.log((8, 12)[i]/(4, 8)[i])
                  for i in range(2)]
        self.assertLess(errors[-1], .1, errors)
        self.assertTrue(all(order >= .7 for order in orders), (errors, orders))

    def test_alternate_initial_seed(self):
        request, _ = manufactured_request(4, seed=.2)
        _, q1 = self.solve(request)
        request, _ = manufactured_request(4, seed=2.)
        _, q2 = self.solve(request)
        np.testing.assert_allclose(q1, q2, rtol=2e-8, atol=0.)

    def test_strong_nonlinear_manufactured_transport(self):
        request, exact = manufactured_request(8, q_amplitude=1.92)
        result, q = self.solve(request)
        nu = request["molecular_kinematic_viscosity_m2_s"]
        self.assertGreater(result["diagnostics"]["maximum_eddy_kinematic_viscosity_m2_s"], .1*nu)
        self.assertLess(np.linalg.norm(q-exact)/np.linalg.norm(exact), .1)
        self.assertGreater(float(q.max()/nu), 3.)
        self.assertGreater(result["diagnostics"]["nonlinear_diffusion_fraction"], .05)
        self.assertGreater(result["diagnostics"]["gradient_source_maximum_m5_s2"], 0.)
        self.assertGreater(result["diagnostics"]["modified_vorticity_guarded_cells"], 0)
        self.assertLess(result["diagnostics"]["modified_vorticity_guarded_cells"], q.size)

    def test_nonuniform_refinement(self):
        request, exact = manufactured_request(4, refined=True)
        _, q = self.solve(request)
        self.assertLess(np.linalg.norm(q-exact)/np.linalg.norm(exact), .1)

    def test_zero_state_is_exact_laminar_limit(self):
        request, exact = manufactured_request(4)
        del request["manufactured_source_m2_s2"]
        request["initial_nu_tilde_m2_s"] = np.zeros_like(exact)
        result, q = self.solve(request)
        self.assertEqual(result["diagnostics"]["iterations"], 0)
        self.assertTrue((q == 0.).all())
        self.assertTrue((np.asarray(result["fields"]["eddy_kinematic_viscosity_m2_s"]) == 0.).all())

    def test_unforced_positive_state_decays_without_clipping(self):
        request, exact = manufactured_request(4)
        del request["manufactured_source_m2_s2"]
        request["face_velocity_m_s"] = [np.zeros_like(v) for v in request["face_velocity_m_s"]]
        result, q = self.solve(request)
        self.assertLess(float(q.max()/exact.max()), 1e-8)
        self.assertEqual(result["diagnostics"]["positivity_clipping_count"], 0)

    def test_time_unit_scaling_preserves_solution_and_residual(self):
        base_request, _ = manufactured_request(4)
        _, base = self.solve(base_request)
        for scale in (1e-20, 1e20):
            request, _ = manufactured_request(4, dimensional_scale=scale)
            result, q = self.solve(request)
            np.testing.assert_allclose(q/scale, base, rtol=2e-8, atol=0.)
            self.assertGreater(result["diagnostics"]["iterations"], 0)

    def test_coefficients_zero_and_guard_branches(self):
        zero = sa_noft2_coefficients(np.array([0., 0.]), 1., np.ones(2), np.array([0., 2.]))
        np.testing.assert_array_equal(zero["r"], [10., 0.])
        self.assertEqual(zero["fw"][1], 0.)
        self.assertAlmostEqual(zero["fw"][0], 65.**(1./6.), places=8)
        values = sa_noft2_coefficients(np.array([7.1, 3.]), 1., np.ones(2), np.array([100., .01]))
        self.assertAlmostEqual(values["fv1"][0], .5, places=15)
        fv = 27./(27.+7.1**3)
        bar = 3.*(1.-3./(1.+3.*fv))/.41**2
        expected = .01+.01*(.49*.01+.9*bar)/(-.5*.01-bar)
        self.assertAlmostEqual(values["modified_vorticity_s_inv"][1], expected, places=15)
        self.assertGreater(expected, 0.)
        self.assertEqual(values["r"][1], 10.)
        self.assertGreater(sa_noft2_coefficients(1., 1., 1., 1.)["fv1"], 0.)

    def test_rejections_do_not_publish_fields(self):
        request, _ = manufactured_request(4)
        mutations = [
            lambda r: r["initial_nu_tilde_m2_s"].fill(-1.),
            lambda r: r["initial_nu_tilde_m2_s"].fill(float("nan")),
            lambda r: r["face_velocity_m_s"][0].__setitem__((0, 0, 0), 1.),
            lambda r: r["face_velocity_m_s"][0].__setitem__((1, 1, 1), 1.),
            lambda r: r.__setitem__("molecular_kinematic_viscosity_m2_s", 0.),
            lambda r: r["grid"]["cell_centers_m"][0].__setitem__(0, 0.),
            lambda r: r["nonlinear_controls"].__setitem__("max_iterations", 1),
            lambda r: r.__setitem__("unknown", True),
        ]
        for mutation in mutations:
            bad = copy.deepcopy(request)
            mutation(bad)
            result = solve_enclosure_sa_transport(bad)
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)
        for q, d in ((-1., 1.), (1., 0.), (math.nan, 1.)):
            with self.assertRaises(ValueError):
                sa_noft2_coefficients(q, 1., d, 1.)

    def test_cancellation_and_unrepresentable_scale(self):
        request, _ = manufactured_request(4)
        self.assertEqual(solve_enclosure_sa_transport(request, cancel_check=lambda: True)["status"], "cancelled")
        request["initial_nu_tilde_m2_s"] *= 1e-180
        request["molecular_kinematic_viscosity_m2_s"] *= 1e-180
        result = solve_enclosure_sa_transport(request)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("fields", result)


if __name__ == "__main__":
    unittest.main()
