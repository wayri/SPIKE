# SPDX-License-Identifier: Apache-2.0
"""Original analytical fixtures; actual CCX checks skip only if not installed."""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from python.spike_core.calculix_deck import compile_calculix_deck
from python.spike_core.calculix_runtime import parse_calculix_temperatures, probe_calculix_runtime, run_calculix_deck
from python.spike_core.calculix_runtime import _artifact_bytes
from python.spike_core.calculix_thermal import prepare_calculix_thermal, run_calculix_thermal, verify_calculix_thermal_result
from python.spike_core.multiboard_identity import canonical_json_digest
from tests.python.test_assembly_tetra_thermal import cube, request, contact_request, boundary, faces_at
from tests.python.test_assembly_tetra_radiation import slab
from tests.python.test_assembly_field_handoff import fixture


class CalculixDeckTests(unittest.TestCase):
    def test_artifact_budget_survives_removed_temporary_file_only(self):
        vanished = Mock()
        vanished.stat.side_effect = FileNotFoundError('thermal.cel disappeared')
        retained = Mock()
        retained.stat.return_value = SimpleNamespace(st_mode=0o100600,st_size=1234)
        directory = Mock()
        directory.iterdir.return_value = [vanished,retained]
        self.assertEqual(_artifact_bytes(directory),1234)
        vanished.stat.side_effect = PermissionError('access denied')
        with self.assertRaises(PermissionError):
            _artifact_bytes(directory)

    def test_si_tensor_faces_sources_and_safe_ids(self):
        raw, _ = slab(1)
        raw['materials'][0]['thermal_conductivity_w_mk'] = [[2,.1,.2],[.1,3,.3],[.2,.3,4]]
        raw['heat_sources_w_m3'] = {raw['mesh']['cells'][0]['id']: 120}
        before = copy.deepcopy(raw)
        compiled = compile_calculix_deck(raw)
        self.assertEqual(raw, before)
        self.assertIn('*CONDUCTIVITY,TYPE=ANISO\n2,3,4,', compiled['deck'])
        self.assertIn('1,BF,120', compiled['deck'])
        self.assertIn('*RADIATE', compiled['deck'])
        self.assertIn('*FILM', compiled['deck'])
        self.assertIn('ABSOLUTE ZERO=0', compiled['deck'])
        self.assertEqual(compile_calculix_deck(raw), compiled)
        for old in raw['mesh']['cells']:
            self.assertNotIn(old['id'], compiled['deck'])
        mm = copy.deepcopy(raw)
        mm['mesh']['units'] = 'mm'
        mm['mesh']['vertices'] = [[x*1000 for x in p] for p in raw['mesh']['vertices']]
        self.assertEqual(compile_calculix_deck(mm)['deck'], compiled['deck'])

    def test_unanchored_invalid_and_contact_topology_fail_closed(self):
        raw = request()
        raw['boundaries'] = []
        with self.assertRaisesRegex(ValueError, 'UNANCHORED'):
            compile_calculix_deck(raw)
        raw = contact_request()
        self.assertEqual(len(compile_calculix_deck(raw)['contact_map']), 2)
        raw['contacts'][0]['right_vertices'][0] = 15
        with self.assertRaises(ValueError):
            compile_calculix_deck(raw)
        raw = request()
        raw['mode'] = 'transient'
        with self.assertRaises(ValueError):
            compile_calculix_deck(raw)

    def test_temperature_parser_final_coverage_and_corruption(self):
        header = ' temperatures for set NALL and time 1.000000D+00\n'
        self.assertEqual(parse_calculix_temperatures(header+'2 310\n1 300\n', 2), [300,310])
        for text in (header+'1 300\n', header+'1 300\n1 301\n2 310\n',
                     header+'1 NaN\n2 310\n', header+'1 -1\n2 310\n',
                     header+'1 300\n3 310\n', header.replace('1.000000D+00','0.5')+'1 300\n2 310\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_calculix_temperatures(text,2)

    def test_missing_runtime_is_not_a_result_and_commands_are_rejected(self):
        req, problem = fixture()
        with patch.dict(os.environ, {'SPIKE_CALCULIX_EXECUTABLE': 'C:/nonexistent/spike-ccx.exe'}):
            prepared = prepare_calculix_thermal(req, problem)
            self.assertEqual(prepared['status'], 'unavailable')
            self.assertFalse(prepared['runtime']['available'])
            with self.assertRaisesRegex(ValueError, 'UNAVAILABLE'):
                run_calculix_thermal(req, problem)
        for options in ({'command': 'ccx'}, {'executable': 'ccx'}, {'threads':True}, {'timeout_seconds':float('nan')}):
            with self.assertRaisesRegex(ValueError, 'OPTIONS'):
                run_calculix_deck(compile_calculix_deck(request()),options)


@unittest.skipUnless(probe_calculix_runtime()['available'], 'Separately installed CalculiX executable unavailable')
class CalculixExecutableTests(unittest.TestCase):
    def run_case(self, raw):
        return run_calculix_deck(compile_calculix_deck(raw), {'timeout_seconds':30})['node_temperatures_k']

    def test_slab_and_convection_radiation_two_meshes(self):
        raw = request(cube(2))
        np.testing.assert_allclose(self.run_case(raw), [300+100*p[0] for p in raw['mesh']['vertices']], atol=1e-3)
        for n in (1,2):
            raw, power = slab(n)
            np.testing.assert_allclose(self.run_case(raw), [350+power/2*(1-p[0]) for p in raw['mesh']['vertices']], atol=.015)

    def test_convection_only_slab(self):
        raw = request(cube(2))
        raw['boundaries'] = boundary(faces_at(raw['mesh'],0),'heat_flux',heat_flux_w_m2=100)
        raw['boundaries'] += boundary(faces_at(raw['mesh'],1),'convection',heat_transfer_coefficient_w_m2k=10,ambient_temperature_k=300)
        np.testing.assert_allclose(self.run_case(raw), [310+50*(1-p[0]) for p in raw['mesh']['vertices']], atol=.002)

    def test_quadratic_volume_heat_refinement(self):
        errors = []
        for n in (1,2,4):
            raw = request(cube(n))
            raw['boundaries'] = boundary(faces_at(raw['mesh'],0),'temperature',temperature_k=300)
            raw['boundaries'] += boundary(faces_at(raw['mesh'],1),'temperature',temperature_k=300)
            raw['heat_sources_w_m3'] = {c['id']:100 for c in raw['mesh']['cells']}
            temperatures = np.array(self.run_case(raw))
            xyz = np.array(raw['mesh']['vertices'])
            errors.append(math.sqrt(np.mean([(temperatures[c['vertices']].mean() -
                (300+25*xyz[c['vertices'],0].mean()*(1-xyz[c['vertices'],0].mean())))**2
                for c in raw['mesh']['cells']])))
        self.assertTrue(all(b < a/3 for a,b in zip(errors, errors[1:])), errors)

    def test_contact_occurrence_identity_and_saved_admission(self):
        req, problem = fixture()
        result = run_calculix_thermal(req, problem, {'timeout_seconds':30})
        self.assertEqual(result['occurrence_temperatures']['board']['maximum_k'],340)
        self.assertEqual(result['occurrence_temperatures']['case']['minimum_k'],360)
        self.assertAlmostEqual(sum(c['left_to_right_heat_w'] for c in result['field_result']['contacts']),-80,places=5)
        self.assertEqual(verify_calculix_thermal_result(req,problem,result),result)
        self.assertRegex(result['execution']['solver_version'], r'^\d+\.\d+(\.\d+)?$')
        changed = copy.deepcopy(result)
        changed['field_result']['cell_heat_flux_w_m2'][0]['heat_flux_w_m2'][0] += 1
        changed['result_digest'] = canonical_json_digest({k:v for k,v in changed.items() if k!='result_digest'})
        with self.assertRaisesRegex(ValueError,'derivation'):
            verify_calculix_thermal_result(req,problem,changed)
        changed = copy.deepcopy(problem)
        for b in changed['boundaries']:
            b['temperature_k'] += 1
        with self.assertRaisesRegex(ValueError,'STALE'):
            verify_calculix_thermal_result(req,changed,result)

    def test_extension_process_returns_actual_bound_result(self):
        req, problem = fixture()
        request_payload = {'contract':'spike/extension/v1', 'contribution_id':'calculix-thermal-run',
                           'context': {'parameters':{'request':req, 'problem':problem,
                                                    'engine_options':{'timeout_seconds':30}}}}
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/'request.json', Path(directory)/'result.json'
            source.write_text(json.dumps(request_payload),encoding='utf-8')
            completed = subprocess.run([sys.executable,'extensions/calculix_suite/extension.py',
                '--request',str(source),'--result',str(target)], capture_output=True,timeout=40)
            self.assertEqual(completed.returncode,0,completed.stderr.decode(errors='replace'))
            result = json.loads(target.read_text())
        self.assertEqual(result['status'],'completed')
        self.assertTrue(result['data']['solved'])
        verify_calculix_thermal_result(req,problem,result['data']['result'])

    def test_host_admission_and_embedded_project_reopen(self):
        from python.spike_core.extensions import ExtensionManifest, ProcessExtension
        from python.spike_core.assembly_field_study import export_assembly_field_study
        from python.spike_core.assembly_field_study import import_assembly_field_study
        from python.spike_core.project_package import read_project
        from tests.python.test_project_assembly_field import _payload, _call, MODEL_ARTIFACT
        from python.spike_core.project_package import write_spike_package
        req, problem = fixture()
        directory = Path('extensions/calculix_suite').resolve()
        manifest = ExtensionManifest.from_dict(json.loads((directory/'spike-extension.json').read_text()))
        engine = ProcessExtension(manifest, directory, True)
        response = engine.invoke('calculix-thermal-run', {'parameters':{
            'request': req, 'problem': problem, 'engine_options': {'timeout_seconds':30}}})
        result = response['data']['result']
        self.assertEqual(result['contract'], 'spike/calculix-thermal-result/v1')
        record = export_assembly_field_study(req, problem, result)
        self.assertEqual(import_assembly_field_study(record,current_request=req,current_problem=problem)['result'],result)
        setup_only = export_assembly_field_study(req,problem,result,include_results=False)
        self.assertIsNone(import_assembly_field_study(setup_only,current_request=req,current_problem=problem)['result'])
        changed = copy.deepcopy(req)
        changed['materials'][0]['thermal_conductivity_w_mk'] *= 2
        with self.assertRaisesRegex(ValueError,'STALE'):
            import_assembly_field_study(record,current_request=changed,current_problem=problem)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'calculix.spike'
            payload = _payload(req)
            payload['models']['models'][0]['id'] = 'case-source'
            package_manifest = write_spike_package(path, payload, model_artifacts={'original-case.step': MODEL_ARTIFACT})
            saved = _call('save_assembly_field_study_in_project', path, package_manifest, record=record)
            self.assertTrue(saved['ok'], saved)
            reopened = read_project(path, include_members=True)
            with patch('python.spike_core.calculix_runtime.run_calculix_deck', side_effect=AssertionError('Offline reopening cannot solve')):
                loaded = _call('read_assembly_field_study_in_project', path, reopened.manifest)
            self.assertTrue(loaded['ok'], loaded)
            self.assertEqual(loaded['result']['state'], 'current')
            self.assertEqual(loaded['result']['record']['result'], result)


if __name__ == '__main__':
    unittest.main()
