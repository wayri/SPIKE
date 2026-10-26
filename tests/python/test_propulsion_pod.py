# SPDX-License-Identifier: Apache-2.0
"""Independent transient, work, admission and compiled-controller checks."""
import copy
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod import DEFAULT_REQUEST, validate_request, angular_secants, coupled_step, run_propulsion_pod
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_field import FieldMotor
from python.spike_core.service_propulsion_pod import handle_propulsion_pod_request

class PodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motor = FieldMotor({'remanence_t': 0.})

    def test_rl_midpoint_against_independent_recurrence(self):
        motor = self.motor
        dt, resistance, extra = .0001, [2., 3.], [.001, .002]
        initial, voltage = np.array([.4, -.2]), np.array([1., -2.])
        result = coupled_step(motor, DEFAULT_REQUEST['propeller'], initial, .3, 0., voltage,
                              dt, resistance, extra, 1e-4, 0., 300.)
        L = motor.inductance_h+np.diag(extra)
        expected = np.linalg.solve(2*L+dt*np.diag(resistance),
                                   (2*L-dt*np.diag(resistance))@initial+2*dt*voltage)
        np.testing.assert_allclose(result['currents_a'], expected, rtol=1e-13, atol=1e-14)
        self.assertEqual(result['speed_rad_s'], 0.)
        self.assertLess(abs(result['energy']['defect_j']), 1e-14)

    def test_nonconstant_pm_self_potential_secant(self):
        # Deliberately anisotropic mathematical fixture: circular physical test
        # rotors have nearly constant C and cannot detect dropping this term.
        M = np.array([[.01, .02], [-.04, .03]])
        S = np.array([[.8, .12], [.12, .3]])
        class Harmonic:
            def coupling_terms(self, angle):
                r = np.array([math.cos(angle), math.sin(angle)])
                dr = np.array([-r[1], r[0]])
                return {'dpsi_dangle_wb_turn_per_rad': (M@dr).tolist(),
                        'dpm_source_potential_dangle_j_per_rad': float(dr@S@r)}
        a, b = -.23, .17
        dpsi, dC = angular_secants(Harmonic(), a, b)
        r0, r1 = [np.array([math.cos(t), math.sin(t)]) for t in (a, b)]
        np.testing.assert_allclose((b-a)*dpsi, M@(r1-r0), rtol=1e-14, atol=1e-15)
        self.assertAlmostEqual((b-a)*dC, .5*(r1@S@r1-r0@S@r0), delta=1e-15)
        tiny, same = angular_secants(Harmonic(), .4, .4)
        self.assertTrue(np.isfinite(tiny).all() and math.isfinite(same))

    def test_admission_refuses_fractional_timing_and_invalid_values(self):
        for section, key, value in [('transient', 'time_step_s', float('nan')),
                                    ('transient', 'controller_period_s', .00055),
                                    ('shaft', 'inertia_kg_m2', True),
                                    ('transient', 'maximum_speed_rad_s', 9000.)]:
            request = copy.deepcopy(DEFAULT_REQUEST)
            request[section][key] = value
            with self.assertRaises(ValueError):
                validate_request(request)
        request = copy.deepcopy(DEFAULT_REQUEST)
        request['controller_source'] = 'untrusted code'
        self.assertFalse(handle_propulsion_pod_request('run_propulsion_pod', {'request': request})['ok'])

    def test_failed_shaft_step_does_not_mutate_input(self):
        currents = [.4, -.2]
        saved = list(currents)
        with self.assertRaises(ValueError):
            coupled_step(self.motor, DEFAULT_REQUEST['propeller'], currents, .3, 1e4, [1., 1.],
                         .001, [2., 2.], [.001, .001], 1e-4, 0., 300.)
        self.assertEqual(currents, saved)

    def test_actual_compiled_controller_closure_and_step_refinement(self):
        # Optional source-runtime/compiler are a prerequisite, not silently
        # replaced by a Python controller or successful skip.
        output = Path(__file__).resolve().parents[2]/'output/promo-propulsion-pod-20261023/.tmp'
        output.mkdir(parents=True, exist_ok=True)
        previous = tempfile.tempdir
        tempfile.tempdir = str(output)
        try:
            request = copy.deepcopy(DEFAULT_REQUEST)
            request['transient']['duration_s'] = .02
            coarse = run_propulsion_pod(request)
            request['transient']['time_step_s'] /= 2
            fine = run_propulsion_pod(request)
        finally:
            tempfile.tempdir = previous
        self.assertEqual(coarse['controller_ticks'], fine['controller_ticks'])
        self.assertEqual(coarse['controller_ticks'], 40)
        self.assertGreater(coarse['history'][-1]['speed_rad_s'], 20.)
        self.assertGreater(coarse['history'][-1]['thrust_n'], 0.)
        self.assertGreater(coarse['energy']['propeller_shaft_work_j'], 0.)
        self.assertLess(abs(coarse['energy']['defect_j']), 1e-10)
        self.assertLess(abs(coarse['history'][-1]['speed_rad_s']-fine['history'][-1]['speed_rad_s']), .05)
        np.testing.assert_allclose(coarse['history'][-1]['currents_a'], fine['history'][-1]['currents_a'], rtol=0., atol=.02)
        self.assertNotEqual(coarse['frames'][0]['element_b_t'], coarse['frames'][-1]['element_b_t'])
        self.assertEqual(coarse['provenance']['controller'], 'actual SPIKES persistent compiled C controller')

if __name__ == '__main__':
    unittest.main()
