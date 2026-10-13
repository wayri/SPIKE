# SPDX-License-Identifier: Apache-2.0
"""Original analytic geometry oracles; no production qualification claim."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from tests.python.test_assembly_thermal_meshing import fixture, has_runtime
from python.spike_core.assembly_thermal_meshing import prepare_assembly_thermal_mesh, run_assembly_thermal_mesh


def encapsulated(kind='potting'):
    p,a,o,r=fixture()
    p['assembly_ir']['boards']=p['assembly_ir']['boards'][:1]
    a['materials'].append({'id':'resin','thermal_conductivity_w_mk':0.5,'provenance':'Original geometry oracle'})
    a['encapsulation']=[{'id':'fill','kind':kind,'material_id':'resin',**(
        {'body_ids':['board-a'],'thickness_mm':0.2} if kind=='coating' else
        {'fill_region':{'kind':'polygon_prism','outer_mm':[[-1,-1],[3,-1],[3,3],[-1,3]],
                        'holes_mm':[],'z_min_mm':-1,'z_max_mm':2},'exclusions':[]})}]
    return p,a,o,r


class PreparationTests(unittest.TestCase):
    def test_recipe_identity_and_unchanged_source(self):
        p,a,o,r=encapsulated(); original=copy.deepcopy(p)
        plan=prepare_assembly_thermal_mesh(p,a,o,artifact_reader=r)
        self.assertEqual(plan['status'],'ready'); self.assertEqual(p,original)
        self.assertEqual(plan['jobs'][-1]['representation'],'occ_potting')
        a['encapsulation'][0]['fill_region']['z_max_mm']=3
        other=prepare_assembly_thermal_mesh(p,a,o,artifact_reader=r)
        self.assertNotEqual(plan['jobs'][-1]['reference_id'],other['jobs'][-1]['reference_id'])

    def test_invalid_assignments(self):
        for mutation in (lambda row:row.update(material_id='missing'),
                         lambda row:row.update(thickness_mm=float('nan')),
                         lambda row:row.update(body_ids=['not-retained'])):
            p,a,o,r=encapsulated('coating'); mutation(a['encapsulation'][0])
            with self.assertRaises(ValueError):prepare_assembly_thermal_mesh(p,a,o,artifact_reader=r)


@unittest.skipUnless(has_runtime(),'Requires admitted local OCC runtime')
class PhysicalGeometryTests(unittest.TestCase):
    def test_real_shell_and_potting_volume_interfaces_and_step(self):
        for kind,volume in [('coating',4.064),('potting',44.)]:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                p,a,o,r=encapsulated(kind)
                result=run_assembly_thermal_mesh(p,a,o,Path(d)/'run',artifact_reader=r)
                self.assertEqual(result['status'],'completed',result.get('blockers'))
                self.assertEqual(len(result['request']['bodies']),2)
                self.assertAlmostEqual(result['evidence'][0]['metrics']['cad_volume_mm3'],4.,places=10)
                for name in ('cad_volume_mm3','tetrahedron_volume_mm3'):
                    self.assertAlmostEqual(result['evidence'][1]['metrics'][name],volume,places=9)
                self.assertGreater(result['joint_interface_admission']['checked_interface_triangles'],0)
                self.assertFalse(result['contacts_inferred'])
                artifact=result['encapsulation_sources'][0]
                data=Path(artifact['path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),artifact['sha256'])
                self.assertEqual(result['request']['bodies'][1]['source_sha256'],artifact['sha256'])
                # Reimport the exported source through the ordinary retained STEP bridge.
                p['assembly_ir']={'assembly_id':'roundtrip','name':'Round trip','parts':[
                    {'id':'shell','model_id':'shell-model','frame':{'frame_id':'shell-frame'}}]}
                p['models']={'models':[{'id':'shell-model','model_type':'step','uri':'package:models/shell.step','digest':artifact['sha256']}]}
                a={'materials':[a['materials'][1]],'boards':{},'parts':{'shell':'resin'}}
                reopened=run_assembly_thermal_mesh(p,a,o,Path(d)/'reimport',artifact_reader=lambda _:data)
                self.assertEqual(reopened['status'],'completed',reopened.get('blockers'))
                self.assertAlmostEqual(reopened['evidence'][0]['metrics']['cad_volume_mm3'],volume,places=8)

    def test_rotated_source_frame_coating(self):
        from math import sin,cos
        p,a,o,r=encapsulated('coating');c,s=cos(.4),sin(.4)
        p['assembly_ir']['boards'][0]['frame']['transform']=[c,-s,0,3,s,c,0,2,0,0,1,1,0,0,0,1]
        with tempfile.TemporaryDirectory() as d:
            result=run_assembly_thermal_mesh(p,a,o,Path(d)/'run',artifact_reader=r)
            self.assertEqual(result['status'],'completed',result.get('blockers'))
            self.assertAlmostEqual(result['evidence'][1]['metrics']['cad_volume_mm3'],4.064,places=9)

    def _assert_physical_power(self, kind):
        from python.spike_core.assembly_thermal_autolink import autolink_assembly_thermal_contacts
        from python.spike_core.assembly_thermal_body_power import assign_assembly_thermal_body_power
        from python.spike_core.assembly_field_handoff import prepare_assembly_field_handoff
        from python.spike_core.assembly_field_thermal import run_assembly_field_thermal
        p,a,o,r=encapsulated(kind)
        with tempfile.TemporaryDirectory() as d:
            generated=run_assembly_thermal_mesh(p,a,o,Path(d)/'run',artifact_reader=r)
            self.assertEqual(generated['status'],'completed',generated.get('blockers'))
            request=generated['request']
            request['assembly']['thermal_contacts']=[{'id':'reviewed-resin-interface',
                'endpoint_a':'board-a','endpoint_b':'encapsulation:fill',
                'contact_area_mm2':16.,'thermal_resistance_k_per_w':1.}]
            problem={'contract':'spike/assembly-field-thermal-problem/v1','heat_sources':[], 'contacts':[], 'boundaries':[]}
            body=request['bodies'][1]
            planes_by_axis = ((-.2,2.2),(-.2,2.2),(-.2,1.2)) if kind=='coating' else ((-1,3),(-1,3),(-1,2))
            for face in body['boundary_faces']:
                xyz=[body['mesh']['vertices'][i] for i in face['vertices']]
                if any(all(abs(point[axis]-plane)<1e-9 for point in xyz)
                       for axis,planes in enumerate(planes_by_axis) for plane in planes):
                    problem['boundaries'].append({'face':{'occurrence_id':body['occurrence_id'],'face_id':face['id']},
                                                   'type':'temperature','temperature_k':300.})
            linked=autolink_assembly_thermal_contacts(request,problem,['reviewed-resin-interface'])['problem']
            heated=assign_assembly_thermal_body_power(request=request,problem=linked,occurrence_id='board-a',power_w=.1,
                expected_request_digest=prepare_assembly_field_handoff(request)['request_digest'])['problem']
            solved=run_assembly_field_thermal(request,heated)
            balance=solved['field_result']['heat_balance']
            self.assertAlmostEqual(balance['source_w'],.1,places=10)
            self.assertLess(abs(balance['imbalance_w']),1e-8)
            heat=sum(row['left_to_right_heat_w'] for row in solved['field_result']['contacts'])
            self.assertAlmostEqual(abs(heat),.1,places=8)
            self.assertGreater(solved['occurrence_temperatures']['board-a']['minimum_k'],300.)

    def test_potted_body_power_crosses_reviewed_contact_and_conserves_energy(self):
        self._assert_physical_power('potting')

    def test_coated_body_power_crosses_reviewed_contact_and_conserves_energy(self):
        self._assert_physical_power('coating')

    def test_exclusion_subtracts_actual_volume(self):
        p,a,o,r=encapsulated()
        a['encapsulation'][0]['exclusions']=[{'kind':'polygon_prism','outer_mm':[[-1,-1],[0,-1],[0,0],[-1,0]],
                                            'holes_mm':[],'z_min_mm':-1,'z_max_mm':2}]
        with tempfile.TemporaryDirectory() as d:
            result=run_assembly_thermal_mesh(p,a,o,Path(d)/'run',artifact_reader=r)
            self.assertEqual(result['status'],'completed',result.get('blockers'))
            self.assertAlmostEqual(result['evidence'][1]['metrics']['cad_volume_mm3'],41.,places=9)

if __name__=='__main__':unittest.main()
