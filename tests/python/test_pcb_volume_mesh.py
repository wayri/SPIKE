# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Whole-model preparation, fixed numeric sizing and worker admission oracles."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from python.spike_core.solvers.geometry_meshing.preparation.gmsh_occ_mesher import _focus_fields, build_occ_mesh, validate_request
from python.spike_core.solvers.geometry_meshing.preparation.pcb_focus_sizing import assess_focus_mesh, plan_focus_regions
from python.spike_core.solvers.geometry_meshing.preparation.pcb_volume_mesh import prepare_pcb_volume_mesh
from python.spike_core.service_meshing import handle_meshing_request
from tests.python.test_pcb_focus_sizing import two_cell_mesh, region

ROOT = Path(__file__).resolve().parents[2]


def example():
    return json.loads((ROOT/'examples/pcb_focus_mesh/whole_board.json').read_text(encoding='utf-8'))


class PcbVolumeMeshTests(unittest.TestCase):
    def test_whole_model_and_ownership_survive_each_selection(self):
        request = example()
        original = copy.deepcopy(request)
        jobs = []
        for policy in ({}, {'net_names': [], 'source_ids': ['sig_trace']},
                       {'net_names': [], 'regions': [{'id': 'local', 'bounds_mm': [[1,1,0],[2,2,1]],
                                                     'target_size_mm': .2}]}):
            changed = copy.deepcopy(request)
            changed['sizing'].update(policy)
            prepared = prepare_pcb_volume_mesh(changed)
            job = prepared['job']
            validate_request(job)
            self.assertEqual(job['mesh']['min_size_mm'], 1e-6)
            self.assertFalse(prepared['production_qualified'])
            self.assertNotIn('solids', prepared['focus_plan'])
            self.assertFalse(prepared['geometry_evidence']['roi_cropping'])
            self.assertEqual(set(prepared['geometry_evidence']['net_ids']), {'SIG', 'OTHER', 'GND'})
            self.assertEqual(len(prepared['job_sha256']), 64)
            jobs.append(job)
        self.assertEqual(jobs[0]['solids'], jobs[1]['solids'])
        self.assertEqual(jobs[0]['solids'], jobs[2]['solids'])
        self.assertEqual(jobs[0]['object_metadata'], jobs[2]['object_metadata'])
        self.assertEqual(request, original)

    def test_rejections_before_native_allocation(self):
        mutations = [lambda r: r.update(extra=True), lambda r: r['resources'].update(max_cells=True),
                     lambda r: r['sizing'].update(net_names=['unknown']),
                     lambda r: r['sizing'].update(growth_rate=5e-324),
                     lambda r: r['sizing'].update(coarse_size_mm=.01),
                     lambda r: r['model']['copper'][0].update(net='GND')]
        for mutate in mutations:
            request = example()
            mutate(request)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                prepare_pcb_volume_mesh(request)
        job = prepare_pcb_volume_mesh(example())['job']
        job['focus']['growth_rate'] = 5e-324
        with self.assertRaises(ValueError):
            build_occ_mesh(None, job)

    def test_fixed_numeric_fields_and_boundary_extension_disabled(self):
        prepared = prepare_pcb_volume_mesh(example())
        gmsh = MagicMock()
        gmsh.model.mesh.field.add.side_effect = range(1, 100)
        _focus_fields(gmsh, prepared['focus_plan'], 1.5)
        field = gmsh.model.mesh.field
        self.assertEqual(field.add.call_args_list[-1].args, ('Min',))
        self.assertEqual(field.setAsBackgroundMesh.call_count, 1)
        values = {call.args[1]: call.args[2] for call in field.setNumber.call_args_list[:9]}
        self.assertAlmostEqual(values['Thickness'], 2.3)
        self.assertAlmostEqual(values['VIn'], .35)
        self.assertAlmostEqual(values['VOut'], 1.5)
        gmsh.option.setNumber.assert_any_call('Mesh.MeshSizeExtendFromBoundary', 0)
        gmsh.option.setNumber.assert_any_call('Mesh.MeshSizeFromPoints', 0)

    def test_diagnostics_without_duplicate_full_mesh(self):
        mesh = two_cell_mesh()
        result = assess_focus_mesh(mesh, [region()], 5, include_mesh=False)
        self.assertNotIn('mesh', result)
        self.assertTrue(result['all_cells_retained'])
        self.assertEqual(result['counts']['cells'], 2)
        solids = prepare_pcb_volume_mesh(example())['job']
        plan = plan_focus_regions(solids['solids'], solids['object_metadata'], solids['focus'],
                                  include_solids=False)
        self.assertNotIn('solids', plan)

    def test_worker_admission_and_structured_failure(self):
        with patch('python.spike_core.solvers.geometry_meshing.preparation.gmsh_occ_runtime.verify_installation', side_effect=ValueError('unavailable')):
            probe = handle_meshing_request('pcb_volume_mesh_capabilities', {})
        self.assertTrue(probe['ok'])
        self.assertFalse(probe['result']['runtime']['available'])
        self.assertTrue(probe['result']['prepare_available'])
        self.assertFalse(probe['result']['production_qualified'])
        with patch('python.spike_core.solvers.geometry_meshing.preparation.gmsh_occ_runtime.verify_installation', return_value={}), \
                patch('python.spike_core.solvers.geometry_meshing.preparation.pcb_volume_mesh.importlib.util.find_spec', return_value=None):
            absent = handle_meshing_request('pcb_volume_mesh_capabilities', {})
        self.assertFalse(absent['result']['prepare_available'])
        self.assertFalse(absent['result']['runtime']['available'])
        response = handle_meshing_request('prepare_pcb_volume_mesh', {'request': example()})
        self.assertTrue(response['ok'])
        for params in ({}, {'request': example(), 'shell': 'bad'}):
            result = handle_meshing_request('prepare_pcb_volume_mesh', params)
            self.assertFalse(result['ok'])
            self.assertEqual(result['error_code'], 'SPIKE-BE-IPC-E-0001')

    def test_schemas_offline_and_unknown_fields(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        schemas = [json.loads(path.read_text(encoding='utf-8')) for path in
                   sorted((ROOT/'schemas').glob('pcb-*-v1.schema.json'))]
        registry = Registry().with_resources((schema['$id'], Resource.from_contents(schema)) for schema in schemas)
        schema = next(s for s in schemas if s['$id'].endswith('pcb-volume-mesh-request-v1.schema.json'))
        for value in schemas:
            Draft202012Validator.check_schema(value)
        validator = Draft202012Validator(schema, registry=registry)
        request = example()
        validator.validate(request)
        request['model']['board']['unexpected'] = True
        self.assertTrue(list(validator.iter_errors(request)))

    def test_json_line_process_prepares_without_native_launch(self):
        payload = {'id': 'whole-board', 'method': 'prepare_pcb_volume_mesh', 'params': {'request': example()}}
        process = subprocess.run([sys.executable, '-m', 'python.spike_core.service'],
                                 input=json.dumps(payload)+'\n', text=True, capture_output=True,
                                 cwd=ROOT, timeout=45)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['result']['job']['contract'], 'spike/gmsh-occ-mesh/v2')


if __name__ == '__main__':
    unittest.main()
