# SPDX-License-Identifier: Apache-2.0
"""Independent supporting mathematics checks, not turbulence qualification.

The oracle differentiates Polynomial objects and the rational eddy-viscosity
law directly. It does not import a discrete operator or solver coefficients.
Absolute 1e-12 derivative/force budgets apply to this fixed SI fixture
(continuous force norm approximately 5e-3 N/m^3); they are not general accuracy
bounds. Covariance checks use a fixed 1e-10 relative solution budget.
"""
import copy
import unittest

import numpy as np
from numpy.polynomial import Polynomial

from python.spike_core.enclosure_rans_research import solve_enclosure_rans_research
from tests.python.test_enclosure_rans_research import exact_mean, fixture


def independent_mean_oracle(coordinates):
    """Continuous curl, its derivatives, and -div(2 mu S)+u.grad(u)+grad(p)."""
    b = Polynomial([0., 1., -1.])
    psi_factor = b*b
    terms = ((10., (0, 1, 0)), (-10., (1, 0, 0)), (0., (0, 0, 0)))

    def derivative(component, orders):
        coefficient, powers = terms[component]
        return coefficient*np.prod([
            psi_factor.deriv(powers[j]+orders[j])(coordinates[j])
            for j in range(3)], axis=0)

    velocity = np.stack([derivative(a, (0, 0, 0)) for a in range(3)], axis=-1)
    jacobian = np.stack([
        np.stack([derivative(a, tuple(int(k == j) for k in range(3)))
                  for j in range(3)], axis=-1)
        for a in range(3)], axis=-2)

    def dynamic_viscosity(points):
        q = (1.92*np.prod([b(t) for t in points], axis=0)
             * (1.+.5*points[0]+.3*points[1]))
        # rho=1 kg/m^3, molecular nu=.01 m^2/s for this fixture.
        return .01+q**4/(q**3+(7.1*.01)**3)

    viscosity = dynamic_viscosity(coordinates)
    gradient = []
    for axis in range(3):
        points = [t.astype(complex) for t in coordinates]
        points[axis] += 1e-25j
        gradient.append(dynamic_viscosity(points).imag/1e-25)
    force = np.zeros_like(velocity)
    for a in range(3):
        force[..., a] = sum(
            velocity[..., j]*jacobian[..., a, j]
            - viscosity*derivative(a, tuple(2*int(k == j) for k in range(3)))
            - (jacobian[..., a, j]+jacobian[..., j, a])*gradient[j]
            for j in range(3))
        force[..., a] += .001*np.prod([
            b.deriv(int(k == a))(coordinates[k]) for k in range(3)], axis=0)
    return velocity, force


class IndependentRANSMathematicsTests(unittest.TestCase):
    def test_eddy_viscosity_derivative_by_complex_step(self):
        q = np.r_[0., np.logspace(-8, 5, 50)]
        nu, step = .01, 1e-26
        perturbed = q+1j*step
        # Product/quotient law written independently, without solver helpers.
        complex_derivative = (
            perturbed**4/(perturbed**3+(7.1*nu)**3)).imag/step
        damping = q**3/(q**3+(7.1*nu)**3)
        analytic_derivative = damping*(4.-3.*damping)
        self.assertLess(float(np.max(abs(complex_derivative-analytic_derivative))), 1e-12)
        self.assertEqual(float(analytic_derivative[0]), 0.)

    def test_continuous_force_against_independent_polynomial_derivatives(self):
        points = [np.array([.13, .25, .38, .72]),
                  np.array([.21, .37, .61, .83]),
                  np.array([.19, .43, .66, .78])]
        velocity, force = independent_mean_oracle(points)
        reference_velocity, reference_force, _, _ = exact_mean(points)
        self.assertGreater(float(np.linalg.norm(force)), 1e-3)
        self.assertLess(float(np.max(abs(velocity-reference_velocity))), 1e-12)
        self.assertLess(float(np.max(abs(force-reference_force))), 1e-12)

    def test_density_and_time_covariance_of_actual_coupled_solution(self):
        request, _ = fixture(4)
        reference = solve_enclosure_rans_research(request)
        self.assertEqual(reference["status"], "completed", reference)

        def compare(actual, expected):
            actual, expected = np.asarray(actual), np.asarray(expected)
            scale = float(np.max(abs(expected)))
            error = float(np.max(abs(actual-expected)))
            if scale:
                self.assertLess(error/scale, 1e-10)
            else:
                self.assertEqual(error, 0.)

        for density, time_scale in ((.037, 1.), (7.3, 1.), (1., 1e-30), (1., 1e30)):
            with self.subTest(density=density, time_scale=time_scale):
                scaled = copy.deepcopy(request)
                scaled["density_kg_m3"] = density
                scaled["molecular_kinematic_viscosity_m2_s"] *= time_scale
                scaled["initial_nu_tilde_m2_s"] *= time_scale
                scaled["manufactured_momentum_source_n_m3"] *= density*time_scale**2
                scaled["manufactured_sa_source_m2_s2"] *= time_scale**2
                result = solve_enclosure_rans_research(scaled)
                self.assertEqual(result["status"], "completed", result)
                self.assertLessEqual(result["diagnostics"]["joint_relative_residual"], 1e-9)
                self.assertFalse(result["production_qualified"])
                for actual, expected in zip(result["fields"]["face_velocity_m_s"],
                                            reference["fields"]["face_velocity_m_s"]):
                    compare(np.asarray(actual)/time_scale, expected)
                compare(np.asarray(result["fields"]["nu_tilde_m2_s"])/time_scale,
                        reference["fields"]["nu_tilde_m2_s"])
                compare(np.asarray(result["fields"]["pressure_pa"])/(density*time_scale**2),
                        reference["fields"]["pressure_pa"])


if __name__ == "__main__":
    unittest.main()
