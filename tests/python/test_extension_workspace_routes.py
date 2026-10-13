# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from python.spike_core.extension_workflows import validate_workspace_routes
from python.spike_core.extension_mesh_results import admit_extension_mesh

class ExtensionWorkspaceTests(unittest.TestCase):
    def test_board_independence_is_explicit_boolean(self):
        route = {'id':'reference', 'workspace':'thermal', 'operation':'solve',
                 'label':'Reference', 'model_status':'experimental'}
        def entry(value):
            return {'applications':[{'id':'reference', 'workspace_routes':[value]}]}
        with self.assertRaises(ValueError):
            validate_workspace_routes(entry(route), [])
        validate_workspace_routes(entry({**route, 'requires_board':False}), [])
        for value in (None, 0, 'false', [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_workspace_routes(entry({**route, 'requires_board':value}), [])
    def test_route_requires_declared_reference_and_cannot_qualify_physics(self):
        route={"id":"mesh", "workspace":"mesh", "operation":"mesh", "label":"Mesh", "model_status":"unvalidated", "preview_contribution_id":"preview"}
        contributes={"applications":[{"id":"mesh", "workspace_routes":[route]}, {"id":"preview"}]}
        validate_workspace_routes(contributes,["design.read"])
        for changes in ({"preview_contribution_id":"absent"},{"model_status":"validated"},{"operation":"shell"}):
            bad=copy.deepcopy(contributes);bad["applications"][0]["workspace_routes"][0].update(changes)
            with self.assertRaises(ValueError):validate_workspace_routes(bad,["design.read"])
    def mesh(self):
        return {"contract":"spike/emerge-mesh/v1", "status":"completed", "model_status":"unvalidated", "solved":False,"units":"mm","coordinate_frame":"design_top_copper", "nodes_mm":[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],"tetrahedra":[[0,1,2,3]],"triangles":[[0,1,2]],"provenance":{"design_id":"fixture","design_digest_sha256":"a"*64,"case_sha256":"b"*64,"generated_script_sha256":"c"*64}}
    def test_mesh_binding_bounds_and_degeneracy(self):
        binding={"design_id":"fixture","digest_sha256":"a"*64}
        result=admit_extension_mesh(self.mesh(),binding,extension_id="fixture.mesh")
        self.assertFalse(result["admission"]["physics_validated"])
        self.assertFalse(result["admission"]["cross_engine_reuse"])
        for change in ({"tetrahedra":[[0,1,2,4]]},{"tetrahedra":[[0,0,2,3]]},{"solved":True},{"units":"m"},{"coordinate_frame":"arbitrary"},{"model_status":"validated"}):
            bad=self.mesh();bad.update(change)
            with self.assertRaises(ValueError):admit_extension_mesh(bad,binding,extension_id="fixture.mesh")
        bad=self.mesh();bad["nodes_mm"][3]=[.3,.2,0]
        with self.assertRaisesRegex(ValueError,"Degenerate"):admit_extension_mesh(bad,binding,extension_id="fixture.mesh")
        with self.assertRaisesRegex(ValueError,"binding"):admit_extension_mesh(self.mesh(),{"design_id":"other","digest_sha256":"a"*64},extension_id="fixture.mesh")
    def test_fdtd_grid_keeps_axes_not_fake_tetrahedra(self):
        mesh=self.mesh();mesh.update(contract="spike/openems-grid/v1",lines_mm={"x":[0,1,2],"y":[0,.2],"z":[-.1,0]});del mesh["tetrahedra"];del mesh["triangles"];del mesh["nodes_mm"]
        result=admit_extension_mesh(mesh,{"design_id":"fixture","digest_sha256":"a"*64},extension_id="fixture.fdtd")
        self.assertEqual(result["lines_mm"]["z"],[-.1,0])
        mesh["lines_mm"]["x"]=[0,0,2]
        with self.assertRaisesRegex(ValueError,"increasing"):admit_extension_mesh(mesh,{"design_id":"fixture","digest_sha256":"a"*64},extension_id="fixture.fdtd")

    def test_malformed_connectivity_fails_with_value_error(self):
        binding={"design_id":"fixture","digest_sha256":"a"*64}
        for key,cells in (("tetrahedra",[[0,1,2,{}]]),("tetrahedra",[[0,1,2,[]]]),
                          ("tetrahedra",[[0,1,2,True]]),("tetrahedra",[[0,1,2,3.0]]),
                          ("triangles",[[0,1,{}]]),("triangles",[[0,1,[]]])):
            bad=self.mesh();bad[key]=cells
            with self.subTest(key=key,cells=cells),self.assertRaisesRegex(ValueError,"connectivity"):
                admit_extension_mesh(bad,binding,extension_id="fixture.mesh")

    def test_overflowed_edges_are_rejected_but_uniform_scales_preserved(self):
        binding={"design_id":"fixture","digest_sha256":"a"*64}
        bad=self.mesh();bad['nodes_mm']=[[-1e308,0,0],[1e308,0,0],[-1e308,1,0],[-1e308,0,1]]
        with self.assertRaisesRegex(ValueError,"nonfinite"):
            admit_extension_mesh(bad,binding,extension_id="fixture.mesh")
        for factor in (1e-200,1e200):
            mesh=self.mesh();mesh['nodes_mm']=[[x*factor for x in node] for node in mesh['nodes_mm']]
            result=admit_extension_mesh(mesh,binding,extension_id="fixture.mesh")
            self.assertEqual(result['tetrahedra'],[[0,1,2,3]])

    def test_unhashable_metadata_and_route_references_fail_closed(self):
        binding={"design_id":"fixture","digest_sha256":"a"*64}
        for key in ('contract','model_status'):
            mesh=self.mesh();mesh[key]={}
            with self.assertRaises(ValueError):admit_extension_mesh(mesh,binding,extension_id='fixture.mesh')
        base={"id":"mesh","workspace":"mesh","operation":"mesh","label":"Mesh","model_status":"unvalidated"}
        for key in ('workspace','operation','setup_contribution_id','preview_contribution_id','mesh_kind'):
            route={**base,key:[]}
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_workspace_routes({'applications':[{'id':'mesh','workspace_routes':[route]}]},['design.read'])
        for contributes in ([],{'applications':{}},{'applications':[{}]},{'applications':[{'id':[]}]}):
            with self.assertRaises(ValueError):validate_workspace_routes(contributes,['design.read'])
