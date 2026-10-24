# SPDX-License-Identifier: Apache-2.0
"""Explicit-profile composition preserves original admission and physical proof."""
from copy import deepcopy
import json
import unittest
from python.spike_core.dc_board_study import board_model, compile_model, solve_board_model, validate_board_run
from tests.python.test_dc_board_source import source_model


class BoardScalingTests(unittest.TestCase):
    def test_explicit_scaled_native_fixture_and_saved_coverage(self):
        prepared = source_model()
        old = board_model(prepared, target_mm=1., max_cells=5000)
        scaled = board_model(prepared, target_mm=1., max_cells=50000, scalable=True)
        run = solve_board_model(scaled)
        saved = json.loads(json.dumps(run)); validate_board_run(saved)
        self.assertEqual(saved['source_model']['contract'], 'spike/dc-board-volume-scalable-model/v1')
        self.assertEqual(saved['result']['source_request']['contract'], 'spike/tetra-dc-rt0-scalable-request/v1')
        self.assertEqual(saved['coverage']['partition_stats']['volume_count'], len(prepared['groups']))
        original = solve_board_model(old)
        self.assertAlmostEqual(run['result']['joule_heat_w']/original['result']['joule_heat_w'], 1., places=8)
        self.assertAlmostEqual(run['result']['current_density_observable']['physical_volume_m3'],
                               original['result']['current_density_observable']['physical_volume_m3'], places=18)

    def test_original_contract_cannot_silently_increase_resource_limits(self):
        raw = board_model(source_model(), target_mm=1., max_cells=5000)
        bad = deepcopy(raw); bad['max_cells'] = 50000
        with self.assertRaisesRegex(ValueError, 'tetrahedron budget'): compile_model(bad)
        raw['contract'] = 'spike/dc-board-volume-scalable-model/v1'; raw['max_cells'] = 50001
        with self.assertRaisesRegex(ValueError, 'tetrahedron budget'): compile_model(raw)


if __name__ == '__main__': unittest.main()
