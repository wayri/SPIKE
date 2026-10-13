# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original conservation, continuous-profile and semidiscrete-exponential oracles."""
import copy
import unittest

import numpy as np
from scipy.linalg import expm

from python.spike_core.internal_airflow import run_internal_airflow
from python.spike_core.multiboard_identity import canonical_json_digest


def request(nx=40, ny=16):
    return {'contract': 'spike/internal-channel-airflow-request/v1',
        'geometry': {'length_m': .3, 'gap_m': .01, 'span_m': .1},
        'fluid': {'density_kg_m3': 1., 'specific_heat_j_kgk': 1000.,
                  'thermal_conductivity_w_mk': .03, 'dynamic_viscosity_pa_s': 2e-5},
        'operating': {'mean_velocity_m_s': .1, 'inlet_temperature_k': 300.,
                      'lower_wall_heat_flux_w_m2': 10., 'upper_wall_heat_flux_w_m2': 10.},
        'mesh': {'axial_cells': nx, 'transverse_cells': ny}}


def exact_transverse_semidiscrete(req):
    """Independent dense generator exponential, no production marching/matrices."""
    n = req['mesh']['transverse_cells']
    length, gap, span = (req['geometry'][k] for k in ('length_m', 'gap_m', 'span_m'))
    rho, cp, conductivity = (req['fluid'][k] for k in (
        'density_kg_m3', 'specific_heat_j_kgk', 'thermal_conductivity_w_mk'))
    speed = req['operating']['mean_velocity_m_s']
    edges = np.linspace(0., 1., n + 1)
    primitive = 3 * edges**2 - 2 * edges**3
    capacity_flow = rho * cp * speed * gap * span * np.diff(primitive)
    matrix = np.zeros((n + 1, n + 1))
    for j in range(n - 1):
        g = conductivity * span * n / gap
        matrix[j, j] -= g
        matrix[j + 1, j + 1] -= g
        matrix[j, j + 1] += g
        matrix[j + 1, j] += g
    matrix[0, n] = req['operating']['lower_wall_heat_flux_w_m2'] * span
    matrix[n - 1, n] = req['operating']['upper_wall_heat_flux_w_m2'] * span
    matrix[:n] /= capacity_flow[:, None]
    return expm(length * matrix)[:n, n]


class InternalAirflowTests(unittest.TestCase):
    def test_velocity_pressure_and_every_station_enthalpy(self):
        req = request()
        req['operating']['upper_wall_heat_flux_w_m2'] = 20.
        original = copy.deepcopy(req)
        result = run_internal_airflow(req)
        self.assertEqual(req, original)
        # Integral momentum: dp=12*mu*U*L/H^2; flow=rho*U*H*span.
        self.assertAlmostEqual(result['pressure_drop_pa'], .072, places=12)
        self.assertAlmostEqual(result['mass_flow_kg_s'], .0001, places=14)
        self.assertAlmostEqual(np.mean(result['velocity_u_m_s']), .1, places=14)
        velocity = np.array(result['velocity_u_m_s'])
        self.assertTrue(np.all(velocity > 0))
        np.testing.assert_allclose(velocity, velocity[::-1], atol=1e-15)
        # dTb/dx=(q_lower+q_upper)*span/(mass_flow*cp)=30 K/m.
        np.testing.assert_allclose(result['bulk_temperature_k'],
            300 + 30 * np.array(result['x_m']), rtol=0, atol=2e-10)
        self.assertAlmostEqual(result['heat_balance']['wall_input_w'], .9, places=13)
        self.assertLess(result['heat_balance']['relative_imbalance'], 1e-10)
        self.assertLess(result['diagnostics']['maximum_equation_residual_w'], 1e-12)
        self.assertFalse(result['production_qualified'])
        self.assertEqual(result['turbulence_model'], 'none')
        self.assertFalse(result['diagnostics']['mesh_convergence_verified'])
        self.assertAlmostEqual(result['diagnostics']['maximum_temperature_rise_k'],
            max(max(result['wall_temperature_k']['lower']), max(result['wall_temperature_k']['upper']),
                np.max(result['temperature_k'])) - 300.)
        digest = result.pop('result_digest')
        self.assertEqual(digest, canonical_json_digest(result))

    def test_adiabatic_uniform_field_and_opposed_flux(self):
        req = request()
        req['operating'].update(lower_wall_heat_flux_w_m2=0., upper_wall_heat_flux_w_m2=0.)
        result = run_internal_airflow(req)
        np.testing.assert_array_equal(result['temperature_k'], np.full((40, 16), 300.))
        self.assertEqual(result['heat_balance']['imbalance_w'], 0.)
        req['operating'].update(lower_wall_heat_flux_w_m2=10., upper_wall_heat_flux_w_m2=-10.)
        result = run_internal_airflow(req)
        np.testing.assert_allclose(result['bulk_temperature_k'], 300., rtol=0, atol=2e-12)
        self.assertGreater(result['wall_temperature_k']['lower'][-1], 300)
        self.assertLess(result['wall_temperature_k']['upper'][-1], 300)

    def test_axial_first_order_against_independent_matrix_exponential(self):
        errors = []
        for nx in (20, 40, 80):
            req = request(nx=nx, ny=7)
            req['geometry']['length_m'] = .015
            result = run_internal_airflow(req)
            expected = 300 + exact_transverse_semidiscrete(req)
            errors.append(np.linalg.norm(np.array(result['temperature_k'][-1]) - expected))
        self.assertTrue(all(1.8 < a / b < 2.2 for a, b in zip(errors, errors[1:])), errors)

    def test_transverse_refinement_to_continuous_developed_profile(self):
        errors, wall_errors = [], []
        for ny in (8, 16, 32):
            req = request(nx=100, ny=ny)
            req['geometry']['length_m'] = 1.
            result = run_internal_airflow(req)
            eta = np.array(result['y_m']) / .01
            # Integrating k*T_yy=rho*cp*u*dTb/dx gives this quartic;
            # its velocity-weighted mean is zero and both wall fluxes are q.
            exact = 320 + (10 * .01 / .03) * (2 * eta**3 - eta**4 - eta + 17 / 70)
            errors.append(np.linalg.norm(np.array(result['temperature_k'][-1]) - exact) / np.sqrt(ny))
            wall_errors.append(abs(result['wall_temperature_k']['lower'][-1] - (320 + 17 / 21)))
        self.assertTrue(all(3.5 < a / b < 4.5 for a, b in zip(errors, errors[1:])), errors)
        self.assertLess(errors[-1], .003)
        self.assertTrue(all(b < a for a, b in zip(wall_errors, wall_errors[1:])), wall_errors)
        self.assertLess(wall_errors[-1], .005)

    def test_input_resource_physical_envelope_and_cancel(self):
        cases = []
        for group, key, value in [('mesh', 'axial_cells', True), ('mesh', 'transverse_cells', 201),
            ('mesh', 'axial_cells', 1001), ('fluid', 'density_kg_m3', float('nan')),
            ('operating', 'mean_velocity_m_s', 10.), ('operating', 'mean_velocity_m_s', 1e-10),
            ('operating', 'lower_wall_heat_flux_w_m2', -1e10),
            ('geometry', 'gap_m', 1e-300), ('fluid', 'dynamic_viscosity_pa_s', True)]:
            req = request()
            req[group][key] = value
            cases.append(req)
        cases.append(request(nx=1000, ny=200))
        invalid = request()
        invalid['turbulence_model'] = 'sst'
        cases.append(invalid)
        for req in cases:
            with self.subTest(req=req), self.assertRaises(ValueError):
                run_internal_airflow(req)
        count = 0
        def cancelled():
            nonlocal count
            count += 1
            return count == 5
        with self.assertRaisesRegex(ValueError, 'Cancelled'):
            run_internal_airflow(request(), cancel_check=cancelled)
        self.assertEqual(count, 5)


if __name__ == '__main__':
    unittest.main()
