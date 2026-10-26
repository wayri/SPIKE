# SPDX-License-Identifier: Apache-2.0
"""Two-grid report checks; these fixtures are not simulation evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[2]/'examples/promo_showcase/propulsion_pod/coupled/compare_geometry_timesteps.py'
SPEC = importlib.util.spec_from_file_location('pod_timestep_comparison', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture(step):
    count = round(.02/step)
    return {'contract': 'spike/geometry-propulsion-loop-result/v1', 'status': 'completed',
            'physical_load_qualified': False, 'production_qualified': False,
            **{key: 'a'*64 for key in ('field_table_sha256', 'fluid_port_sha256',
                                      'controller_source_sha256', 'orchestrator_sha256')},
            'request': {'initial_currents_a': [0, 0, 0], 'drive': {'dc_bus_v': 48},
                        'thermal': {}, 'shaft': {}, 'transient': {'duration_s': .02,
                        'time_step_s': step, 'wall_budget_s': 60, 'controller_period_s': .01}},
            'accepted_steps': count, 'energy': {'defect_j': 0.},
            'history': [{'time_s': index*step, 'currents_a': [index*step, -index*step, 0],
                         'speed_rad_s': 200+index*step, 'angle_rad': index*step,
                         'temperature_k': [293.15]*11, 'field_torque_n_m': .1,
                         'flux_coordinates_wb_turn': [0., 0.]} for index in range(count+1)]}


class TimestepComparisonTests(unittest.TestCase):
    def test_aligned_nonidentical_fields_and_signed_energy(self):
        coarse, fine = fixture(.002), fixture(.001)
        fine['history'][4]['currents_a'] = [.104, -.104, 0]
        fine['energy']['defect_j'] = 1e-10
        result = MODULE.compare(coarse, fine)
        self.assertAlmostEqual(result['endpoint_observables']['currents_a']['maximum_absolute_change'], .1)
        self.assertEqual(result['common_endpoint_count'], 11)
        self.assertEqual(result['cumulative_energy']['defect_j']['coarse_minus_fine'], -1e-10)
        self.assertFalse(result['physical_qualified'])

    def test_reject_changed_sources_sampling_and_incomplete_times(self):
        mutations = [lambda r: r.update(orchestrator_sha256='b'*64),
                     lambda r: r['request']['transient'].update(controller_period_s=.005),
                     lambda r: r['history'][3].update(time_s=.0031),
                     lambda r: r.update(accepted_steps=19),
                     lambda r: r['history'][0].update(temperature_k=[float('nan')]*11)]
        for mutate in mutations:
            fine = fixture(.001)
            mutate(fine)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                MODULE.compare(fixture(.002), fine)

    def test_different_wall_budget_is_allowed_but_not_other_setup(self):
        fine = fixture(.001)
        fine['request']['transient']['wall_budget_s'] = 120
        MODULE.compare(fixture(.002), fine)
        altered = copy.deepcopy(fine)
        altered['request']['drive']['dc_bus_v'] = 47
        with self.assertRaises(ValueError):
            MODULE.compare(fixture(.002), altered)


if __name__ == '__main__':
    unittest.main()
