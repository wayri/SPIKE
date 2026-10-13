# SPDX-License-Identifier: Apache-2.0
"""Original typed extension round-trip and complete PCB source oracles."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from python.spike_core.extension_analysis_results import design_binding
from python.spike_core.extensions import ExtensionManifest
from python.spike_core.gmsh_extension_api import execute
from python.spike_core.gmsh_extension_mesh import admit_gmsh_mesh
from python.spike_core.gmsh_extension_runtime import dispatch


def request(contribution='gmsh-prepare-pcb'):
    design = {'contract': 'spike/v1', 'design_id': 'original-gmsh-fixture'}
    binding = design_binding(design)
    model = {'contract':'spike/pcb-volume-model/v1','board':{'id':'board','outer_mm':[[0,0],[2,0],[2,2],[0,2]],'holes_mm':[]},
             'layers':[{'id':'top','z_min_mm':0,'z_max_mm':.2,'background_material_id':'fr4'},
                       {'id':'core','z_min_mm':.2,'z_max_mm':1,'background_material_id':'fr4'}],
             'copper':[{'id':'pad','net':'SIG','layer_id':'top','outer_mm':[[.5,.5],[1.5,.5],[1.5,1.5],[.5,1.5]],'holes_mm':[]}],
             'vias':[{'id':'via','net':'SIG','center_mm':[1,1],'z_min_mm':0,'z_max_mm':1,'outer_radius_mm':.2,'inner_radius_mm':.1}],
             'copper_material_id':'copper','drill_material_id':'air'}
    geometry = {'contract':'spike/pcb-volume-mesh-request/v1','model':model,
        'sizing':{'contract':'spike/pcb-focus-sizing/v1','net_names':['SIG'],'source_ids':[],
                  'fine_size_mm':.4,'coarse_size_mm':.8,'halo_mm':.2,'growth_rate':.5,'regions':[]},
        'resources':{'max_cells':10000,'max_vertices':10000}}
    return {'contract':'spike/extension/v1','request_id':'fixture','contribution_id':contribution,
            'context':{'design':design,'design_binding':binding,'parameters':{'request':geometry,'expected_design_sha256':binding['digest_sha256']}}}


class GmshExtensionTests(unittest.TestCase):
    def test_manifest_routes_are_geometry_only(self):
        manifest = ExtensionManifest.from_dict(json.loads(Path('extensions/gmsh_suite/spike-extension.json').read_text()))
        self.assertEqual(manifest.id, 'spike.gmsh-suite')
        routes = [r for c in manifest.contributes['applications'] for r in c.get('workspace_routes', [])]
        self.assertEqual({r['workspace'] for r in routes}, {'mesh','thermal','em','si','pi'})
        self.assertTrue(all(r['operation'] == 'mesh' and not r['compatible_solver_ids'] for r in routes))

    def test_prepare_keeps_copper_via_drill_and_whole_stack(self):
        data = request()
        data['context']['parameters'].pop('expected_design_sha256')
        result = execute(data)['data']
        self.assertEqual(result['design_binding'], data['context']['design_binding'])
        kinds = {m['kind'] for m in result['job']['object_metadata'].values()}
        self.assertTrue({'board_layer','copper','plated_via','drill'} <= kinds)
        self.assertFalse(result['solved'])
        self.assertEqual(result['geometry_evidence']['net_ids'], ['SIG'])

    def test_stale_binding_scripts_and_unsupported_volume_reject_before_engine(self):
        mutations = [lambda r:r['context']['parameters'].update(expected_design_sha256='a'*64),
                     lambda r:r['context']['parameters'].update(geo='Merge arbitrary.step;'),
                     lambda r:r.update(contribution_id='gmsh-field-solve'),
                     lambda r:r['context']['parameters']['request']['model']['board'].update(outer_mm=[[0,0],[2,2],[2,0],[0,2]])]
        for mutate in mutations:
            data = request('gmsh-mesh-pcb'); mutate(data)
            with patch('python.spike_core.gmsh_occ_runtime.run_occ_case') as run:
                with self.assertRaises(ValueError): execute(data)
                run.assert_not_called()

    def test_missing_runtime_returns_probe_diagnostic(self):
        with patch('python.spike_core.gmsh_occ_runtime.verify_installation',side_effect=ValueError('missing entry artifacts')):
            result = execute({'contribution_id':'gmsh-probe','context':{'parameters':{}}})
        self.assertFalse(result['data']['available'])
        self.assertEqual(result['data']['physics_solvers'], [])

    @unittest.skipUnless(sys.platform == 'win32' and Path('C:/msys64/ucrt64/lib/gmsh.py').is_file(), 'Requires local optional Gmsh runtime')
    def test_real_extension_mesh_preserves_complete_conductors_and_ownership(self):
        data = request('gmsh-mesh-pcb')
        result = dispatch(data)
        mesh = result['data']['mesh_result']
        admitted = admit_gmsh_mesh(mesh, data['context']['design_binding'])
        self.assertFalse(admitted['solved'])
        self.assertFalse(admitted['admission']['cross_engine_reuse'])
        self.assertGreater(len(mesh['solver_mesh']['cells']), 0)
        self.assertEqual({c['material_id'] for c in mesh['solver_mesh']['cells']}, {'copper','fr4','air'})
        self.assertEqual(set(mesh['solver_mesh']['object_map']), {s for c in mesh['solver_mesh']['cells'] for s in c['source_object_ids']})
        self.assertAlmostEqual(mesh['metrics']['cad_volume_mm3'], 4, places=8)
        # Curved via surfaces have straight mesh facets: no exact curved-volume claim.
        self.assertAlmostEqual(mesh['metrics']['tetrahedron_volume_mm3'], 4, places=8)
        self.assertTrue(mesh['interface_faces'])
        for mutate in (lambda m:m['boundary_faces'].pop(),lambda m:m['tetrahedra'][0].__setitem__(0,999999),
                       lambda m:m.update(solved=True),lambda m:m['provenance'].update(design_digest_sha256='0'*64)):
            invalid = copy.deepcopy(mesh); mutate(invalid)
            with self.assertRaises(ValueError): admit_gmsh_mesh(invalid,data['context']['design_binding'])


if __name__ == '__main__': unittest.main()
