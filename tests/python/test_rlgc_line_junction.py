# SPDX-License-Identifier: Apache-2.0
"""Independent physical nodal/spatial oracles for supplied RLGC stars."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

from examples.rlgc_line_junction.run_line import request
from python.spike_core import rlgc_line_junction as solver
from python.spike_core.rlgc_line_cascade import run_rlgc_line_cascade


def value(p):
    return complex(p['real'], p['imag'])


def pair(z):
    return {'real': float(z.real), 'imag': float(z.imag)}


def matrix(p):
    return np.array([[value(z) for z in row] for row in p])


def physical_oracle(raw, index):
    """Unknown left V/I states; impose external V+rI and right V/KCL.

    This uses neither production scattering matrices nor the junction wave law.
    """
    legs = raw['legs']; count = len(legs)
    reference = legs[0]['line_request']['reference_impedance_ohm']
    operators, transfers = [], []
    system = np.zeros((2 * count, 2 * count), complex)
    rhs = np.zeros((2 * count, count), complex)
    for j, leg in enumerate(legs):
        line = leg['line_request']; sample = line['samples'][index]
        omega = 2 * np.pi * sample['frequency_hz']
        m = np.array([[0, sample['resistance_ohm_per_m'] + 1j * omega * line['inductance_h_per_m']],
                      [sample['conductance_s_per_m'] + 1j * omega * line['capacitance_f_per_m'], 0]], complex)
        t = expm(-m * line['length_m']); operators.append(m); transfers.append(t)
        system[j, 2*j:2*j+2] = [1, reference]
        rhs[j, j] = 2 * np.sqrt(reference)
        if j:
            system[count+j-1, 2*j:2*j+2] = t[0]
            system[count+j-1, :2] = -transfers[0][0]
        system[-1, 2*j:2*j+2] = t[1]
    states = np.linalg.solve(system, rhs)
    scattering = np.vstack([(states[2*j] - reference * states[2*j+1]) / (2*np.sqrt(reference)) for j in range(count)])
    return scattering, states, operators


class JunctionNumericalTests(unittest.TestCase):
    def assert_close(self, actual, expected, atol=2e-12, rtol=1e-10):
        np.testing.assert_allclose(actual, expected, atol=atol, rtol=rtol)

    def test_independent_physical_fields_and_owned_quadrature(self):
        raw = request(); before = deepcopy(raw); out = solver.run_rlgc_line_junction(raw)
        self.assertEqual(raw, before); self.assertEqual(out['source_request'], raw)
        for k, point in enumerate(out['points']):
            scattering, states, operators = physical_oracle(raw, k)
            self.assert_close(matrix(out['network']['s_parameters'][k]), scattering)
            drive = np.array([value(z) for z in raw['excitations'][k]['incident_waves']])
            coherent = states @ drive; conductor = dielectric = 0.
            for j, (leg, child, m) in enumerate(zip(raw['legs'], out['legs'], operators)):
                line = leg['line_request']; sample = line['samples'][k]; length = line['length_m']
                def fields(x):
                    return expm(-m*x) @ coherent[2*j:2*j+2]
                child_point = child['result']['points'][k]
                for probe in child_point['probe_values']:
                    v, i = fields(probe['fractional_position']*length)
                    self.assert_close([value(probe['voltage_v']), value(probe['current_left_to_right_a'])], [v, i])
                    self.assertAlmostEqual(probe['electric_energy_j_per_m'], .5*line['capacitance_f_per_m']*abs(v)**2, delta=1e-20)
                    self.assertAlmostEqual(probe['magnetic_energy_j_per_m'], .5*line['inductance_h_per_m']*abs(i)**2, delta=1e-20)
                c = sample['resistance_ohm_per_m']*quad(lambda x: abs(fields(x)[1])**2, 0, length, epsabs=1e-13)[0]
                d = sample['conductance_s_per_m']*quad(lambda x: abs(fields(x)[0])**2, 0, length, epsabs=1e-13)[0]
                self.assert_close([child_point['power_balance']['conductor_loss_w'], child_point['power_balance']['dielectric_loss_w']], [c, d])
                conductor += c; dielectric += d
            self.assert_close([point['power_balance']['conductor_loss_w'], point['power_balance']['dielectric_loss_w']], [conductor, dielectric])
            self.assertEqual(point['power_balance']['residual_w'], point['power_balance']['net_input_w']-point['power_balance']['total_loss_w'])
            self.assertLess(abs(value(point['junction']['current_residual_a'])), 1e-12)
            self.assertLess(abs(point['junction']['power_residual_w']), 2e-12)

    def test_analytic_matched_three_port_and_maximum_eight_legs(self):
        for count in (3, 8):
            raw = request(); raw['legs'] = [deepcopy(raw['legs'][0]) for _ in range(count)]
            for j, leg in enumerate(raw['legs']):
                leg['id'] = str(j); leg['line_request']['length_m'] = .1 + .02*j
                for sample in leg['line_request']['samples']:
                    sample['resistance_ohm_per_m'] = sample['conductance_s_per_m'] = 0.
            for drive in raw['excitations']: drive['incident_waves'] = [pair(1+0j)] + [pair(0j)]*(count-1)
            out = solver.run_rlgc_line_junction(raw)
            for k, drive in enumerate(raw['excitations']):
                phase = np.diag([np.exp(-1j*2*np.pi*drive['frequency_hz']*5e-9*leg['line_request']['length_m']) for leg in raw['legs']])
                expected = phase @ (np.full((count, count), 2/count)-np.eye(count)) @ phase
                actual = matrix(out['network']['s_parameters'][k]); self.assert_close(actual, expected)
                self.assert_close(actual.conj().T@actual, np.eye(count))
                self.assertEqual(out['points'][k]['power_balance']['total_loss_w'], 0.)
                if count == 3: self.assert_close(np.abs(actual[:, 0])**2, [1/9, 4/9, 4/9])

    def test_two_leg_cascade_with_reversed_second_orientation(self):
        raw = request(); raw['legs'] = raw['legs'][:2]
        for drive in raw['excitations']: drive['incident_waves'] = drive['incident_waves'][:2]
        chain = {'contract': 'spike/rlgc-line-cascade-request/v1', 'sections': deepcopy(raw['legs']),
                 'excitations': [{'frequency_hz': d['frequency_hz'], 'incident_left': d['incident_waves'][0], 'incident_right': d['incident_waves'][1]} for d in raw['excitations']]}
        for probe in chain['sections'][1]['probes']: probe['fractional_position'] = 1-probe['fractional_position']
        star, cascade = solver.run_rlgc_line_junction(raw), run_rlgc_line_cascade(chain)
        for k in range(len(raw['excitations'])):
            self.assert_close(matrix(star['network']['s_parameters'][k]), matrix(cascade['network']['s_parameters'][k]))
            self.assert_close(star['points'][k]['power_balance']['total_loss_w'], cascade['points'][k]['power_balance']['total_loss_w'])
            for leg in (0, 1):
                for p, q in zip(star['legs'][leg]['result']['points'][k]['probe_values'], cascade['sections'][leg]['result']['points'][k]['probe_values']):
                    self.assert_close(value(p['voltage_v']), value(q['voltage_v']))
                    self.assert_close(value(p['current_left_to_right_a']), (1 if leg == 0 else -1)*value(q['current_left_to_right_a']))

    def test_strongly_attenuating_matched_legs_analytic_heat(self):
        raw = request()
        for leg in raw['legs']:
            line = leg['line_request']; line['length_m'] = 20.
            # Binary-exact matching isolates propagation from a rounded Zc mismatch.
            line['reference_impedance_ohm'] = 64.
            line['inductance_h_per_m'] = 2.**-22; line['capacitance_f_per_m'] = 2.**-34
            for sample in line['samples']:
                sample['resistance_ohm_per_m'] = 128.; sample['conductance_s_per_m'] = 2.**-5
        out = solver.run_rlgc_line_junction(raw)
        for k, excitation in enumerate(raw['excitations']):
            q = np.exp(-40-1j*2*np.pi*excitation['frequency_hz']*20*2.**-28)
            junction = np.full((3, 3), 2/3)-np.eye(3)
            self.assert_close(matrix(out['network']['s_parameters'][k]), q*q*junction, atol=1e-47, rtol=2e-12)
            incident = np.array([value(p) for p in excitation['incident_waves']]); returned = junction@(q*incident)
            for j, child in enumerate(out['legs']):
                heat = (1-abs(q)**2)*(abs(incident[j])**2+abs(returned[j])**2)
                self.assert_close(child['result']['points'][k]['power_balance']['total_loss_w'], heat)

    def test_coherent_permutation_scaling_and_probe_independence(self):
        raw = request(); base = solver.run_rlgc_line_junction(raw); perm = [2, 0, 1]; factor = -.3+.7j
        changed = deepcopy(raw); changed['legs'] = [changed['legs'][j] for j in perm]
        for drive in changed['excitations']: drive['incident_waves'] = [pair(factor*value(drive['incident_waves'][j])) for j in perm]
        for leg in changed['legs']: leg['probes'] = [leg['probes'][0]]
        out = solver.run_rlgc_line_junction(changed)
        for k in range(len(raw['excitations'])):
            self.assert_close(matrix(out['network']['s_parameters'][k]), matrix(base['network']['s_parameters'][k])[np.ix_(perm, perm)])
            self.assert_close(out['points'][k]['power_balance']['total_loss_w'], abs(factor)**2*base['points'][k]['power_balance']['total_loss_w'])
            for j, original in enumerate(perm):
                actual = out['legs'][j]['result']['points'][k]['probe_values'][0]
                expected = base['legs'][original]['result']['points'][k]['probe_values'][0]
                self.assert_close(value(actual['voltage_v']), factor*value(expected['voltage_v']))

    def test_zero_drives_exact_zero_fields_and_losses(self):
        raw = request()
        for drive in raw['excitations']: drive['incident_waves'] = [pair(0j)]*3
        out = solver.run_rlgc_line_junction(raw)
        for point in out['points']:
            self.assertTrue(all(z == 0 for z in point['power_balance'].values()))
            self.assertEqual(value(point['junction']['current_residual_a']), 0j)
        for leg in out['legs']:
            for point in leg['result']['points']:
                for probe in point['probe_values']:
                    self.assertEqual(value(probe['voltage_v']), 0j)
                    self.assertEqual(probe['total_loss_w_per_m'], 0.)

    def test_quadrature_refinement(self):
        raw = request(); out = solver.run_rlgc_line_junction(raw); k = 2
        _, states, operators = physical_oracle(raw, k)
        drive = np.array([value(z) for z in raw['excitations'][k]['incident_waves']]); state = (states@drive)[:2]
        line = raw['legs'][0]['line_request']; sample = line['samples'][k]; length = line['length_m']
        exact = out['legs'][0]['result']['points'][k]['power_balance']['total_loss_w']; errors = []
        for cells in (16, 32, 64):
            x = np.linspace(0, length, cells+1)
            density = [sample['resistance_ohm_per_m']*abs((expm(-operators[0]*t)@state)[1])**2 + sample['conductance_s_per_m']*abs((expm(-operators[0]*t)@state)[0])**2 for t in x]
            integral = (length/cells)*(sum(density)-.5*(density[0]+density[-1]))
            errors.append(abs(integral-exact))
        self.assertTrue(all(3.8 < a/b < 4.2 for a, b in zip(errors, errors[1:])), errors)
        self.assertLess(errors[-1], 2e-6)

    def test_strict_admission(self):
        def invalid(raw):
            with self.assertRaises(solver.RLGCLineJunctionError): solver.run_rlgc_line_junction(raw)
        for mutation in range(15):
            raw = request()
            if mutation == 0: raw['extra'] = 0
            elif mutation == 1: raw['legs'] = raw['legs'][:1]
            elif mutation == 2: raw['legs'][1]['id'] = raw['legs'][0]['id']
            elif mutation == 3: raw['legs'][1]['line_request']['reference_impedance_ohm'] = 75
            elif mutation == 4: raw['legs'][1]['line_request']['samples'][0]['frequency_hz'] = 2e6
            elif mutation == 5: raw['excitations'][0]['incident_waves'].pop()
            elif mutation == 6: raw['excitations'][0]['incident_waves'][0]['real'] = True
            elif mutation == 7: raw['excitations'][0]['incident_waves'][0]['imag'] = float('nan')
            elif mutation == 8: raw['legs'][0]['line_request']['length_m'] = False
            elif mutation == 9: raw['legs'][0]['line_request']['samples'][0]['frequency_hz'] = 0
            elif mutation == 10: raw['legs'][0]['probes'][0]['fractional_position'] = 1.1
            elif mutation == 11: raw['legs'][0]['probes'][1]['id'] = raw['legs'][0]['probes'][0]['id']
            elif mutation == 12: raw['excitations'][0]['frequency_hz'] = True
            elif mutation == 13: raw['legs'][0]['id'] = ' '*5
            else: raw['contract'] = 'wrong'
            with self.subTest(mutation=mutation): invalid(raw)

    def test_resource_preflight_before_any_leaf_solve(self):
        raw = request()
        for leg in raw['legs']:
            original = leg['line_request']['samples'][0]
            leg['line_request']['samples'] = [dict(original, frequency_hz=j+1.) for j in range(1024)]
            leg['probes'] = [{'id': str(j), 'fractional_position': j/31} for j in range(32)]
        raw['excitations'] = [{'frequency_hz': j+1., 'incident_waves': [pair(1j)]*3} for j in range(1024)]
        with patch.object(solver, 'build_rlgc_line_network') as leaf:
            with self.assertRaisesRegex(solver.RLGCLineJunctionError, 'Estimated nested'): solver.run_rlgc_line_junction(raw)
            leaf.assert_not_called()
        with patch.object(solver, '_MAX_WORK', 1), patch.object(solver, 'build_rlgc_line_network') as leaf:
            with self.assertRaisesRegex(solver.RLGCLineJunctionError, 'combined'): solver.run_rlgc_line_junction(request())
            leaf.assert_not_called()

    def test_cancellation_and_callback_failure(self):
        for cancel in (lambda: True, lambda: (_ for _ in ()).throw(RuntimeError('failed'))):
            with self.assertRaises(solver.RLGCLineJunctionError): solver.run_rlgc_line_junction(request(), cancel_check=cancel)
        calls = 0
        def late():
            nonlocal calls
            calls += 1
            return calls > 65
        with self.assertRaisesRegex(solver.RLGCLineJunctionError, 'cancelled'): solver.run_rlgc_line_junction(request(), cancel_check=late)

    def test_condition_residual_and_float_failure(self):
        with patch.object(solver.np.linalg, 'cond', return_value=1e9):
            with self.assertRaisesRegex(solver.RLGCLineJunctionError, 'condition'): solver.run_rlgc_line_junction(request())
        real_solve = np.linalg.solve
        with patch.object(solver.np.linalg, 'solve', side_effect=lambda a, b: real_solve(a, b)+.1):
            with self.assertRaisesRegex(solver.RLGCLineJunctionError, 'residual'): solver.run_rlgc_line_junction(request())
        for amplitude in (1e-200, 1e200):
            raw = request()
            for drive in raw['excitations']: drive['incident_waves'] = [pair(complex(amplitude))]*3
            with self.subTest(amplitude=amplitude), self.assertRaises(solver.RLGCLineJunctionError): solver.run_rlgc_line_junction(raw)

    def test_corrupt_child_fails_closed(self):
        real_child = solver.run_rlgc_line_fields
        for kind in ('voltage', 'current', 'power', 'negative_heat', 'heat', 'residual', 'identity', 'network'):
            def corrupt(raw, **kwargs):
                child = real_child(raw, **kwargs); p = child['points'][0]
                if kind == 'voltage': p['boundary_values']['right']['voltage_v']['real'] += .1
                elif kind == 'current': p['boundary_values']['right']['current_into_line_a']['real'] += .1
                elif kind == 'power': p['boundary_values']['right']['input_power_w'] += .1
                elif kind == 'negative_heat': p['power_balance']['conductor_loss_w'] = -1.
                elif kind == 'heat': p['power_balance']['conductor_loss_w'] += .1
                elif kind == 'residual': p['power_balance']['residual_w'] += .1
                elif kind == 'identity': child['input_digest'] = 'a'*64
                else: child['network']['port_names'] = ['wrong', 'right']
                return child
            with self.subTest(kind=kind), patch.object(solver, 'run_rlgc_line_fields', side_effect=corrupt):
                with self.assertRaises(solver.RLGCLineJunctionError): solver.run_rlgc_line_junction(request())


if __name__ == '__main__':
    unittest.main()
