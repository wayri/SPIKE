# SPDX-License-Identifier: Apache-2.0
"""Original analytical bulk slab and exhaustive broad-phase test oracles."""
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.assembly_tetra_thermal import run_assembly_tetra_thermal
from python.spike_core.assembly_tetra_thermal_validation import AssemblyTetraThermalError, require
from python.spike_core.tetra_aabb_candidates import overlapping_pairs
from tests.python.test_assembly_tetra_thermal import cube, request


class BulkThermalTests(unittest.TestCase):
    def test_bulk_transient_uniform_heat_capacity_reference(self):
        from python.spike_core.assembly_tetra_transient import run_assembly_tetra_transient
        from tests.python.test_assembly_tetra_transient import settings
        raw = request(cube(10))
        raw['boundaries'] = []
        raw['heat_sources_w_m3'] = {c['id']: 40. for c in raw['mesh']['cells']}
        out = run_assembly_tetra_transient(raw, settings(step=0.5, output=0.5))
        for frame in out['frames']:
            np.testing.assert_allclose(frame['node_temperatures_k'], 300 + 2 * frame['time_s'],
                                       atol=1e-8, rtol=0)

    def test_ten_thousand_tetrahedra_analytical_slab(self):
        raw = request(cube(12))
        out = run_assembly_tetra_thermal(raw)
        self.assertEqual(out['resources']['tetrahedra'], 10368)
        self.assertGreater(out['diagnostics']['cg_iterations'], 0)
        expected = [300 + 100 * p[0] for p in raw['mesh']['vertices']]
        np.testing.assert_allclose(out['node_temperatures_k'], expected, atol=2e-7, rtol=0)
        np.testing.assert_allclose([c['heat_flux_w_m2'] for c in out['cell_heat_flux_w_m2']],
                                   np.tile([-200., 0, 0], (10368, 1)), atol=2e-5, rtol=0)
        cold = sum(power for node, power in out['reactions_w'].items()
                   if raw['mesh']['vertices'][int(node)][0] == 0)
        self.assertAlmostEqual(cold, -200, places=6)
        self.assertLess(abs(out['heat_balance']['imbalance_w']), 1e-6)
        self.assertLess(out['diagnostics']['free_relative_residual'], 1e-8)
        self.assertLess(out['resources']['matrix_nonzeros'], 40 * len(expected))
        self.assertLess(out['resources']['geometry_comparisons'], 20 * 10368)

    def test_hierarchy_matches_exhaustive_pairs(self):
        rng = np.random.default_rng(743)
        lows = rng.uniform(-1, 1, (150, 3))
        highs = lows + rng.uniform(0.01, 0.5, (150, 3))
        actual = [tuple(sorted(pair)) for pair in overlapping_pairs(lows, highs, 100000, require)]
        expected = {(i, j) for i in range(150) for j in range(i + 1, 150)
                    if np.all(np.minimum(highs[i], highs[j]) > np.maximum(lows[i], lows[j]))}
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(expected))

    def test_budgets_fail_before_sparse_allocation(self):
        raw = request(cube(2))
        for constant, message in [('MAX_MATRIX_ENTRIES', 'entry budget'),
                                  ('MAX_WORKSPACE_BYTES', 'workspace.*budget'),
                                  ('MAX_HIERARCHY_VISITS', 'traversal budget'),
                                  ('MAX_COMPARISONS', 'comparison budget')]:
            with self.subTest(constant=constant), patch(
                    'python.spike_core.assembly_tetra_thermal_validation.' + constant, 1), patch(
                    'python.spike_core.assembly_tetra_thermal.coo_matrix') as sparse:
                with self.assertRaisesRegex(AssemblyTetraThermalError, message):
                    run_assembly_tetra_thermal(raw)
                sparse.assert_not_called()

    def test_mesh_count_budget_and_large_malformed(self):
        raw = request(cube(10))
        raw['mesh']['cells'][-1]['vertices'][1] = raw['mesh']['cells'][-1]['vertices'][0]
        with self.assertRaisesRegex(AssemblyTetraThermalError, 'indices'):
            run_assembly_tetra_thermal(raw)
        with patch('python.spike_core.assembly_tetra_thermal_validation.MAX_CELLS', 5):
            with self.assertRaisesRegex(AssemblyTetraThermalError, 'resource budget'):
                run_assembly_tetra_thermal(request())
