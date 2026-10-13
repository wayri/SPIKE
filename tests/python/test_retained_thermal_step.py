# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SPIKE contributors
"""Independent energy and mapping oracles for prepared retained thermal steps."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.assembly_tetra_thermal_validation import AssemblyTetraThermalError
from python.spike_core.retained_thermal_step import prepare_retained_thermal_step
from python.spike_core import retained_thermal_step
from tests.python.test_assembly_tetra_thermal import boundary, contact_request, request


def single_cell():
    mesh = {'contract': 'spike/solver-mesh/v1', 'units': 'm',
            'coordinate_system': 'right_handed_xyz',
            'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'cells': [{'id': 'c', 'kind': 'tetrahedron', 'vertices': [0, 1, 2, 3],
                       'material_id': 'k', 'source_object_ids': ['body']}],
            'counts': {'vertices': 4, 'cells': 1},
            'object_map': {'body': {'kind': 'solid'}}}
    raw = request(mesh)
    raw['boundaries'] = []
    raw['heat_sources_w_m3'] = {}
    return raw


def capacity():
    return [{'material_id': 'k', 'density_kg_m3': 2., 'specific_heat_j_kgk': 10.}]


def prepare(raw=None, mapping=None):
    return prepare_retained_thermal_step(single_cell() if raw is None else raw, capacity(),
                                         {'d': [{'cell_id': 'c', 'weight': 1.}]} if mapping is None else mapping)


class RetainedThermalStepTests(unittest.TestCase):
    def test_uniform_heating_exact_energy_and_stateless_reuse(self):
        prepared = prepare()
        old = [300.] * 4
        original = copy.deepcopy(old)
        result = prepared.advance(old, .5, {'d': 10.})
        self.assertEqual(old, original)
        # Volume=1/6 m3 and rho*cp=20 J/(m3 K): delta T=10/(20/6)=3 K.
        np.testing.assert_allclose(result['node_temperatures_k'], [303.] * 4, atol=1e-9)
        self.assertAlmostEqual(result['device_temperatures_k']['d'], 303.)
        self.assertAlmostEqual(result['energy_balance']['stored_energy_change_j'], 10., places=8)
        self.assertAlmostEqual(result['energy_balance']['source_j'], 10.)
        self.assertLess(abs(result['energy_balance']['imbalance_j']), 1e-8)
        self.assertEqual(result, prepared.advance(old, .5, {'d': 10.}))

    def test_distinct_device_maps_and_transpose_gather(self):
        raw = contact_request()
        raw['boundaries'] = []
        raw['heat_sources_w_m3'] = {}
        ids = [cell['id'] for cell in raw['mesh']['cells']]
        left, right = ids[0], ids[-1]
        raw['contacts'] = []
        prepared = prepare(raw, {'left': [{'cell_id': left, 'weight': 1.}],
                                 'right': [{'cell_id': right, 'weight': 1.}]})
        result = prepared.advance([300.] * prepared.node_count, .1, {'left': 5., 'right': 0.})
        self.assertGreater(result['device_temperatures_k']['left'], 300.)
        self.assertAlmostEqual(result['device_temperatures_k']['right'], 300., places=8)
        self.assertAlmostEqual(result['energy_balance']['stored_energy_change_j'], 5., places=8)
        values = [float(i + 290) for i in range(prepared.node_count)]
        cells = {cell['id']: cell for cell in raw['mesh']['cells']}
        self.assertAlmostEqual(prepared.device_temperatures_k(values)['left'],
                               np.mean([values[i] for i in cells[left]['vertices']]))

    def test_contact_exchange_and_outward_boundary_ledger(self):
        raw = contact_request()
        raw['boundaries'] = []
        raw['heat_sources_w_m3'] = {}
        left = raw['mesh']['cells'][0]['id']
        prepared = prepare(raw, {'d': [{'cell_id': left, 'weight': 1.}]})
        old = [310.] * 8 + [300.] * 8
        result = prepared.advance(old, .1, {'d': 0.})
        self.assertLess(np.mean(result['node_temperatures_k'][:8]), 310.)
        self.assertGreater(np.mean(result['node_temperatures_k'][8:]), 300.)
        self.assertLess(abs(result['energy_balance']['stored_energy_change_j']), 1e-7)
        self.assertLess(abs(result['energy_balance']['imbalance_j']),
                        result['energy_balance']['acceptance_tolerance_j'])
        cool = single_cell()
        cool['boundaries'] = boundary([[0, 1, 2]], 'convection_radiation',
                                      heat_transfer_coefficient_w_m2k=2., ambient_temperature_k=300.,
                                      emissivity=.5, radiation_temperature_k=300.)
        cooled = prepare(cool).advance([350.] * 4, .01, {'d': 0.})
        ledger = cooled['energy_balance']
        self.assertGreater(ledger['convection_outward_j'], 0.)
        self.assertGreater(ledger['radiation_outward_j'], 0.)
        self.assertLess(ledger['stored_energy_change_j'], 0.)
        self.assertLess(abs(ledger['imbalance_j']), ledger['acceptance_tolerance_j'])

    def test_dirichlet_reaction_and_failure_paths(self):
        raw = single_cell()
        raw['boundaries'] = boundary([[0, 1, 2]], 'temperature', temperature_k=300.)
        prepared = prepare(raw)
        result = prepared.advance([300., 300., 300., 310.], .1, {'d': 0.})
        self.assertLess(result['energy_balance']['temperature_reaction_inward_j'], 0.)
        self.assertLess(abs(result['energy_balance']['imbalance_j']),
                        result['energy_balance']['acceptance_tolerance_j'])
        with self.assertRaisesRegex(AssemblyTetraThermalError, 'fixed boundary'):
            prepared.validate_temperature([301.] * 4)
        for energies in ({}, {'d': -1.}, {'d': float('nan')}, {'d': 1., 'other': 0.}):
            with self.subTest(energies=energies), self.assertRaises(AssemblyTetraThermalError):
                prepared.advance([300.] * 4, .1, energies)
        with self.assertRaises(AssemblyTetraThermalError):
            prepared.advance([300.] * 4, 0., {'d': 1.})
        with self.assertRaisesRegex(AssemblyTetraThermalError, 'cancelled'):
            prepared.advance([300.] * 4, .1, {'d': 1.}, cancel_check=lambda: True)
        for invalid in (np.array(300.), np.array([[300.] * 4]), [True] * 4,
                        [300., 300., 300., False]):
            with self.subTest(invalid=invalid), self.assertRaises(AssemblyTetraThermalError):
                prepared.validate_temperature(invalid)
        original_step = retained_thermal_step._step
        finished = [False]

        def finish_step(*args):
            result = original_step(*args)
            finished[0] = True
            return result

        with patch.object(retained_thermal_step, '_step', side_effect=finish_step):
            with self.assertRaisesRegex(AssemblyTetraThermalError, '^THERMAL_STEP_CANCELLED:'):
                prepared.advance([300.] * 4, .1, {'d': 1.}, cancel_check=lambda: finished[0])
        self.assertTrue(finished[0])

    def test_mapping_admission_and_unaccounted_source(self):
        raw = single_cell()
        raw['heat_sources_w_m3'] = {'c': 1.}
        with self.assertRaisesRegex(AssemblyTetraThermalError, 'zero authored'):
            prepare(raw)
        with patch.object(retained_thermal_step, '_assemble') as assemble:
            with self.assertRaisesRegex(AssemblyTetraThermalError, 'memory budget'):
                with patch.object(retained_thermal_step, 'MAX_WEIGHT_VALUES', 3):
                    prepare(single_cell())
            assemble.assert_not_called()
        for mapping in ({}, {'d': []}, {'d': [{'cell_id': 'missing', 'weight': 1.}]},
                        {'d': [{'cell_id': 'c', 'weight': .5}]},
                        {'d': [{'cell_id': 'c', 'weight': 1.}, {'cell_id': 'c', 'weight': 1.}]},
                        {'d': [{'cell_id': 'c', 'weight': float('inf')}]},
                        {'d': [{'cell_id': 'c', 'weight': -1.}]}):
            with self.subTest(mapping=mapping), self.assertRaises(AssemblyTetraThermalError):
                prepare(single_cell(), mapping)
        with self.assertRaisesRegex(AssemblyTetraThermalError, 'cancelled'):
            prepare_retained_thermal_step(single_cell(), capacity(),
                                          {'d': [{'cell_id': 'c', 'weight': 1.}]},
                                          cancel_check=lambda: True)


if __name__ == '__main__':
    unittest.main()
