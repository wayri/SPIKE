# SPDX-License-Identifier: Apache-2.0
import copy
import unittest

from python.spike_core.assembly_tetra_transient import run_assembly_tetra_transient
from python.spike_core.thermal_accuracy import run_time_refinement
from tests.python.test_assembly_tetra_transient import one_dof, insulated, settings
from tests.python.test_assembly_field_handoff import fixture


class ThermalAccuracyTests(unittest.TestCase):
    def audit(self, raw, setup, tolerance=.01, cancel=None):
        return run_time_refinement(raw, setup, {'absolute_k': tolerance, 'relative_rise': 0.},
            tetra_request=raw, cancel_check=cancel,
            runner=lambda s: run_assembly_tetra_transient(raw, s))

    def test_decay_refinement_against_exact_semidiscrete_solution(self):
        raw = one_dof()
        setup = settings(step=.2, output=1., initial=[300.] * 3 + [310.])
        original = copy.deepcopy((raw, setup))
        result = self.audit(raw, setup)
        e = result['evidence']
        self.assertEqual(e['status'], 'refinement_required')
        self.assertTrue(e['independent_time_refinement'])
        self.assertTrue(e['uniform_halved_grids'])
        self.assertTrue(.8 < e['empirical_l2_order'] < 1.1)
        self.assertAlmostEqual(result['fine_result']['node_temperatures_k'][3],
                               300 + 10 * 1.05 ** -20, places=9)
        self.assertFalse(result['fine_result']['diagnostics']['temporal_convergence_verified'])
        self.assertEqual((raw, setup), original)
        self.assertEqual(self.audit(raw, setup, .2)['evidence']['status'], 'within_requested_change')

    def test_output_events_defeat_refinement_and_cannot_pass(self):
        e = self.audit(one_dof(), settings(step=.2, output=.025,
            initial=[300.] * 3 + [310.]), 1.)['evidence']
        self.assertEqual(e['status'], 'event_grid_limited')
        self.assertFalse(e['independent_time_refinement'])
        self.assertIsNone(e['empirical_l2_order'])

    def test_exact_uniform_heating_has_no_invented_order(self):
        e = self.audit(insulated(), settings(step=.2, output=.2))['evidence']
        self.assertEqual(e['status'], 'within_requested_change')
        self.assertIsNone(e['empirical_l2_order'])

    def test_invalid_tolerance_and_cancel_fail_closed(self):
        with self.assertRaises(ValueError):
            self.audit(one_dof(), settings(), -1)
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            self.audit(one_dof(), settings(), cancel=lambda: True)
        setup = settings()
        setup['time_step_s'] = True
        with self.assertRaises(ValueError):
            self.audit(one_dof(), setup)

    def test_worker_occurrence_binding_and_mcp_registry(self):
        from python.spike_core.service_assembly_field import handle_assembly_field_request
        from python.spike_core.assembly_field_transient import verify_assembly_field_transient_result
        from python.spike_core.mcp_server import TOOLS
        raw, problem = fixture()
        setup = settings(material='slab', initial=300.)
        problem['boundaries'] = []
        out = handle_assembly_field_request('validate_assembly_thermal_time_refinement',
            {'request': raw, 'problem': problem, 'transient_settings': setup,
             'tolerances': {'absolute_k': .1, 'relative_rise': .01}})
        self.assertTrue(out['ok'], out)
        fine = out['result']['fine_result']
        from python.spike_core.multiboard_identity import canonical_json_digest
        self.assertEqual(out['result']['evidence']['runs'][-1]['full_record_sha256'],
                         canonical_json_digest(fine))
        self.assertEqual(verify_assembly_field_transient_result(raw, problem, fine), fine)
        self.assertEqual(fine['transient_settings']['time_step_s'], .025)
        self.assertIn('spike_validate_thermal_time_refinement', TOOLS)
        rejected = handle_assembly_field_request('validate_assembly_thermal_time_refinement', {})
        self.assertFalse(rejected['ok'])


if __name__ == '__main__':
    unittest.main()
