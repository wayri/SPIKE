# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Production failure paths preserve energy evidence, never synthetic results."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.contracts import AnalysisSpec, DesignIR, ValidationIssue
from python.spike_core.hybrid_mesh import HybridMesh, MeshBranch, MeshNode
from python.spike_core.peec_plugin import solve_peec_2_5d, native_available
from python.spike_core.peec_network import solve_linear_system
from python.spike_core.peec_volume_support import ZoneBasisSupportError


class PEECEnergyAdmissionTests(unittest.TestCase):
    @unittest.skipUnless(native_available(), 'Native PEEC required')
    def test_loop_error_invalidates_an_otherwise_usable_port(self):
        design = DesignIR(layers=[{'name': 'F.Cu'}], nets=[{'id': 1, 'name': 'VCC'}],
            tracks=[{'id': 'rail', 'start': [0, 0], 'end': [4, 0], 'width': 1,
                     'layer': 'F.Cu', 'net_name': 'VCC'}])
        spec = AnalysisSpec(mode='ac', net_names=['VCC'], frequency_start_hz=1e3,
            frequency_stop_hz=1e4, frequency_points=2, mesh={'target_size_mm': 2})
        self.assertEqual(solve_peec_2_5d(design, spec).status, 'completed')
        issue = ValidationIssue('SPIKE-BE-PI-E-0201', 'error', 'Invalid loop component')
        with patch('python.spike_core.peec_plugin.extract_loop_parasitics',
                   return_value=([], [issue], {})):
            result = solve_peec_2_5d(design, spec)
        self.assertEqual(result.status, 'failed')
        self.assertFalse(result.networks)
        self.assertFalse(result.fields)

    def test_mna_rejects_nonfinite_and_nonunique_solutions(self):
        for matrix, rhs in (([[float('nan')]], [1]), ([[1]], [float('inf')]),
                            ([[0, 0], [0, 1]], [0, 1]), ([[1, 2]], [1])):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                solve_linear_system(np.array(matrix), np.array(rhs), True)
        with patch('numpy.linalg.solve', return_value=np.array([float('nan')])):
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                solve_linear_system(np.eye(1), np.ones(1), False)
        with patch('numpy.linalg.solve', return_value=np.array([0.0])):
            with self.assertRaisesRegex(ValueError, 'residual'):
                solve_linear_system(np.eye(1), np.ones(1), False)

    def test_mna_retains_valid_complex_multi_rhs(self):
        matrix = np.array([[2+1j, -.2], [-.2, 3-.5j]])
        rhs = np.array([[1, 0], [0, 2j]])
        solution, quality = solve_linear_system(matrix, rhs, True)
        np.testing.assert_allclose(matrix @ solution, rhs, atol=1e-14)
        self.assertLess(quality['relative_residual'], 1e-14)

    def test_ac_preserves_nonpassive_evidence_without_solving(self):
        mesh = HybridMesh(nodes=[MeshNode(i, i, 0, 0, 'F.Cu', 'VCC') for i in range(3)],
            branches=[MeshBranch(str(i), 'track', i, i+1, (i, 0, 0), (i+1, 0, 0),
                .2, .035, 5.8e7, 'F.Cu', 'VCC', str(i)) for i in range(2)])
        matrix = np.array([[1e-9, 2e-9], [2e-9, 1e-9]])
        solver = SimpleNamespace(compute_partial_inductance=lambda: matrix)
        with patch('python.spike_core.peec_plugin.native', object()), patch(
            'python.spike_core.peec_plugin.build_hybrid_mesh', return_value=mesh), patch(
            'python.spike_core.peec_plugin._make_native_solver', return_value=(solver, None)), patch(
            'python.spike_core.peec_plugin._solve_port') as solve:
            result = solve_peec_2_5d(DesignIR(), AnalysisSpec(mode='ac'))
        solve.assert_not_called()
        self.assertEqual(result.status, 'failed')
        self.assertFalse(result.fields)
        self.assertFalse(result.networks)
        self.assertFalse(result.provenance['solved'])
        self.assertEqual(result.provenance['inductance_units'], 'H')
        quality = result.provenance['numerical_quality']['inductance_passivity']
        self.assertEqual(quality['negative_eigenmode_count'], 1)
        self.assertAlmostEqual(quality['minimum_eigenvalue']/1e-9, -1)
        self.assertFalse(quality['projection_applied'])
        np.testing.assert_array_equal(matrix, [[1e-9, 2e-9], [2e-9, 1e-9]])
        json.dumps(result.to_dict(), allow_nan=False)

    def test_explicit_volume_request_fails_closed_when_backend_is_unavailable(self):
        mesh = HybridMesh(nodes=[MeshNode(i, i, 0, 0, 'F.Cu', 'VCC') for i in range(2)],
            branches=[MeshBranch('0', 'track', 0, 1, (0, 0, 0), (1, 0, 0),
                .2, .035, 5.8e7, 'F.Cu', 'VCC', '0')])
        solver = SimpleNamespace(compute_partial_inductance=lambda: np.eye(1))
        spec = AnalysisSpec(mode='ac', options={'peec_volume_extraction': 'enabled'})
        with patch('python.spike_core.peec_plugin.native', object()), patch(
            'python.spike_core.peec_plugin.build_hybrid_mesh', return_value=mesh), patch(
            'python.spike_core.peec_plugin._make_native_solver', return_value=(solver, None)), patch(
            'python.spike_core.peec_plugin.extract_volume_matrices',
            side_effect=ValueError('native finite-volume PEEC backend is unavailable')):
            result = solve_peec_2_5d(DesignIR(), spec)
        self.assertEqual(result.status, 'failed')
        self.assertIn('PEEC_VOLUME_EXTRACTION_FAILED', {issue.code for issue in result.issues})
        self.assertEqual(result.provenance['failure_stage'], 'volume_matrix_extraction')
        self.assertEqual(result.provenance['volume_current_model'], 'uniform_volume_current')

    def test_zone_support_failure_preserves_structured_ownership(self):
        mesh = HybridMesh(nodes=[MeshNode(i, i, 0, 0, 'F.Cu', 'VCC') for i in range(2)],
            branches=[MeshBranch('zone-branch', 'zone', 0, 1, (0, 0, 0), (1, 0, 0),
                .2, .035, 5.8e7, 'F.Cu', 'VCC', 'zone-source')])
        solver = SimpleNamespace(compute_partial_inductance=lambda: np.eye(1))
        report = {'violating_basis_count': 1, 'violations': [
            {'branch_id': 'zone-branch', 'source_id': 'zone-source',
             'outside_area_mm2': 0.01}]}
        failure = ZoneBasisSupportError('PEEC_ZONE_BASIS_OUTSIDE_COPPER',
                                        'zone-branch crosses source fill', report)
        spec = AnalysisSpec(mode='ac', options={'peec_volume_extraction': 'enabled'})
        with patch('python.spike_core.peec_plugin.native', object()), patch(
            'python.spike_core.peec_plugin.build_hybrid_mesh', return_value=mesh), patch(
            'python.spike_core.peec_plugin._make_native_solver', return_value=(solver, None)), patch(
            'python.spike_core.peec_plugin.extract_volume_matrices', side_effect=failure):
            result = solve_peec_2_5d(DesignIR(), spec)
        self.assertEqual(result.status, 'failed')
        self.assertIn('PEEC_ZONE_BASIS_OUTSIDE_COPPER', {issue.code for issue in result.issues})
        self.assertEqual(result.provenance['zone_basis_support'], report)
