# SPDX-License-Identifier: Apache-2.0
"""Executed thermal-to-stress references and worker admission failures."""
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.assembly_thermomechanical import run_assembly_thermomechanical
from python.spike_core.service_assembly_field import handle_assembly_field_request
from tests.python.test_assembly_tetra_structural import request as elastic_request, fix, rigid_constraints
from tests.python.test_assembly_tetra_thermal import request as heat_request


def request():
    structural = elastic_request()
    for i in range(len(structural['mesh']['vertices'])):
        fix(structural, i)
    return {'contract': 'spike/assembly-thermomechanical-request/v1',
            'thermal': heat_request(deepcopy(structural['mesh'])), 'structural': structural}


class ThermomechanicalTests(unittest.TestCase):
    def test_executed_gradient_to_clamped_stress_and_energy(self):
        raw = request(); before = deepcopy(raw)
        out = run_assembly_thermomechanical(raw)
        self.assertEqual(raw, before)
        self.assertEqual(out['input_digest'], hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest())
        xyz = np.array(raw['thermal']['mesh']['vertices'])
        temperatures = 300+100*xyz[:, 0]
        np.testing.assert_allclose(out['thermal']['node_temperatures_k'], temperatures, atol=1e-10)
        self.assertEqual(out['structural_input_digest'], out['structural']['input_digest'])
        self.assertEqual(out['mesh_digest'], out['structural']['mesh_digest'])
        energy = 0.
        for cell, result in zip(raw['thermal']['mesh']['cells'], out['structural']['cells']):
            eigenstrain = 1e-5*(np.mean(temperatures[cell['vertices']])-300)
            # K=E/[3(1-2nu)], fully clamped isotropic stress=-3 K alpha dT.
            stress = -4e9*eigenstrain
            np.testing.assert_allclose(result['stress_pa'], [stress]*3+[0.]*3, atol=1e-5)
            self.assertLess(result['von_mises_pa'], 1e-6)
            energy += result['volume_m3']*1.5*4e9*eigenstrain**2
        self.assertAlmostEqual(out['structural']['elastic_energy_j'], energy, places=6)
        self.assertFalse(out['production_qualified'])

    def test_real_uniform_heating_free_expansion(self):
        raw = request()
        raw['structural']['dirichlet'] = []
        rigid_constraints(raw['structural'])
        for face in raw['thermal']['boundaries']:
            face['temperature_k'] = 350.
        out = run_assembly_thermomechanical(raw)
        np.testing.assert_allclose(out['structural']['node_displacements_m'],
                                   np.array(raw['structural']['mesh']['vertices'])*.0005,
                                   atol=1e-14)
        self.assertLess(max(abs(s) for c in out['structural']['cells'] for s in c['stress_pa']), 1e-5)

    def test_unicode_ownership_uses_identical_canonical_digests(self):
        raw = request()
        for sub in ('thermal', 'structural'):
            raw[sub]['mesh']['object_map']['solid']['body_id'] = '\u03bc-coil'
        out = run_assembly_thermomechanical(raw)
        self.assertEqual(out['mesh_digest'], out['structural']['mesh_digest'])
        self.assertEqual(out['structural_input_digest'], out['structural']['input_digest'])

    def test_mismatch_temperature_and_nonfinite_rejected_before_heat(self):
        for mutation in ('mesh', 'ownership', 'temperature', 'nan', 'extra'):
            raw = request()
            if mutation == 'mesh': raw['structural']['mesh']['vertices'][0][0] = .001
            if mutation == 'ownership': raw['structural']['mesh']['object_map']['solid']['label'] = 'other'
            if mutation == 'temperature': raw['structural']['nodal_temperatures_k'] = {'0': 350}
            if mutation == 'nan': raw['thermal']['materials'][0]['thermal_conductivity_w_mk'] = float('nan')
            if mutation == 'extra': raw['result'] = {}
            with patch('python.spike_core.assembly_thermomechanical.run_assembly_tetra_thermal') as solver:
                with self.assertRaises(ValueError): run_assembly_thermomechanical(raw)
                solver.assert_not_called()

    def test_cancel_before_and_after_blocking_heat(self):
        raw = request()
        with self.assertRaises(ValueError): run_assembly_thermomechanical(raw, cancel_check=lambda: True)
        from python.spike_core.assembly_tetra_thermal import run_assembly_tetra_thermal
        cancelled = [False]
        def heat(value):
            out = run_assembly_tetra_thermal(value)
            cancelled[0] = True
            return out
        with patch('python.spike_core.assembly_thermomechanical.run_assembly_tetra_thermal', side_effect=heat):
            with self.assertRaisesRegex(ValueError, 'CANCELLED'):
                run_assembly_thermomechanical(raw, cancel_check=lambda: cancelled[0])

    def test_unanchored_solid_and_thermal_failure_do_not_return_success(self):
        raw = request(); raw['structural']['dirichlet'] = []
        with self.assertRaises(ValueError): run_assembly_thermomechanical(raw)
        raw = request(); raw['thermal']['materials'][0]['thermal_conductivity_w_mk'] = -1
        response = handle_assembly_field_request('run_assembly_thermomechanical', {'request': raw})
        self.assertFalse(response['ok'])

    def test_worker_dispatch_and_exact_admission(self):
        for method, raw in [('run_assembly_thermomechanical', request()),
                            ('run_assembly_tetra_structural', request()['structural'])]:
            response = handle_assembly_field_request(method, {'request': raw})
            self.assertTrue(response['ok'], response)
            self.assertFalse(response['result']['production_qualified'])
            self.assertFalse(handle_assembly_field_request(method, {'request': raw, 'override': True})['ok'])
        self.assertIsNone(handle_assembly_field_request('unrelated-method', {}))
