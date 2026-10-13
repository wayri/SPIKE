# SPDX-License-Identifier: Apache-2.0
"""Original retained conducting plates and hollow enclosure fixture."""
import copy
import itertools
import unittest

from python.spike_core.assembly_em import prepare_assembly_em
from tests.python.test_assembly_tetra_thermal import cube,exterior


def fixture():
    bodies=[]
    assembly={'contract':'spike/assembly-ir/v1','assembly_id':'original-enclosed-em',
        'name':'Original conducting plate fixture','boards':[], 'parts':[]}
    for oid,z in [('return',0.),('signal',.004)]:
        mesh=cube(owner=oid)
        mesh['vertices']=[[x*.01,y*.01,z+zz*.001] for x,y,zz in mesh['vertices']]
        assembly['boards'].append({'id':oid,'design_id':oid+'-source','frame':{'frame_id':oid+'-frame'}})
        bodies.append({'occurrence_id':oid,'reference_id':oid+'-source','source_sha256':'a'*64,
            'mesh':mesh,'boundary_faces':[{'id':str(i),'vertices':f} for i,f in enumerate(exterior(mesh))],
            'material_map':{'k':'copper'},'stack_binding':{'id':'original-electrode','source_sha256':'b'*64}})
    # Original cubical wall topology; the central cube is omitted, retaining
    # both inward cavity faces and the outward closed enclosure surface.
    coordinates=[-.003,-.002,.012,.013]
    case=cube(3,owner='case')
    case['vertices']=[[coordinates[round(x*3)],coordinates[round(y*3)],coordinates[round(z*3)]]
                      for x,y,z in case['vertices']]
    case['cells']=[c for c in case['cells'] if not all(
        -.002<=case['vertices'][i][axis]<=.012 for i in c['vertices'] for axis in range(3))]
    case['counts']['cells']=len(case['cells'])
    assembly['parts'].append({'id':'case','model_id':'original-hollow-case','part_type':'enclosure',
                             'frame':{'frame_id':'case-frame'}})
    bodies.append({'occurrence_id':'case','reference_id':'original-hollow-case','source_sha256':'c'*64,
        'mesh':case,'boundary_faces':[{'id':str(i),'vertices':f} for i,f in enumerate(exterior(case))],
        'material_map':{'k':'aluminium'}})
    def face(body,z):
        return next(f for f in body['boundary_faces'] if all(
            body['mesh']['vertices'][v][2]==z for v in f['vertices']) and
            sum(body['mesh']['vertices'][v][0] for v in f['vertices'])<.015)
    # Opposed triangle patches share the same diagonal; footprint x<y.
    ground_face=face(bodies[0],.001); signal_face=face(bodies[1],.004)
    geometry={'contract':'spike/assembly-field-handoff-request/v1','domain':'em','assembly':assembly,
        'bodies':bodies,'materials':[{'id':mid,'provenance':'Original fixture explicit conductivity',
            'conductivity_s_m':sigma,'relative_permittivity':1.,'relative_permeability':1.}
            for mid,sigma in [('copper',5.8e7),('aluminium',3.5e7)]],
        'ports':[{'id':'drive','reference_impedance_ohm':50.,
            'return':{'occurrence_id':'return','face_id':ground_face['id']},
            'signal':{'occurrence_id':'signal','face_id':signal_face['id']}}]}
    return {'contract':'spike/assembly-em-request/v1','geometry':geometry,
        'ports':[{'id':'drive','start_m':[.002,.005,.001],'stop_m':[.003,.006,.004],
                  'direction':'z','excite':True}],
        'settings':{'frequency_hz':[.5e9,1e9,1.5e9],'mesh_resolution_m':.001,
            'air_margin_m':.006,'max_timesteps':20000,'end_criteria':1e-6,'timeout_s':120,'threads':2}}


class AssemblyEmTests(unittest.TestCase):
    def test_preflight_and_no_source_mutation(self):
        request=fixture(); before=copy.deepcopy(request)
        prepared=prepare_assembly_em(request)
        self.assertEqual(request,before)
        self.assertEqual(len(prepared['compiled']['ports']),1)

    def test_missing_physical_inputs_and_resource_rejection(self):
        request=fixture()
        for key,value in [('max_timesteps',True),('mesh_resolution_m',1.),('threads',0),
                          ('frequency_hz',[1e9,1e9])]:
            bad=copy.deepcopy(request); bad['settings'][key]=value
            with self.assertRaises(ValueError):prepare_assembly_em(bad)
        bad=copy.deepcopy(request);bad['ports']=[];bad['geometry']['ports']=[]
        with self.assertRaises(ValueError):prepare_assembly_em(bad)
        bad=copy.deepcopy(request)
        bad['settings'].update(mesh_resolution_m=1e-6,air_margin_m=10)
        with self.assertRaisesRegex(ValueError,'before allocation'):prepare_assembly_em(bad)

    def test_service_returns_error_envelope(self):
        from python.spike_core.service_assembly_field import handle_assembly_field_request
        result=handle_assembly_field_request('prepare_assembly_em',{'request':{}})
        self.assertFalse(result['ok'])

    def test_stale_result_request_binding_is_rejected(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from python.spike_core.assembly_em import run_assembly_em
        request=fixture(); compiled=prepare_assembly_em(request)['compiled']
        def fake_run(*args,**kwargs):
            (kwargs['cwd']/'result.json').write_text(json.dumps({'contract':'spike/assembly-em-result/v1',
                'status':'completed','solver_executed':True,'model_status':'unvalidated','production_qualified':False,
                'compiled_digest':compiled['compiled_digest'],'request_digest':'stale', 'run_id':'stale',
                'frequency_hz':request['settings']['frequency_hz'],'excited_port_id':'drive',
                's_parameter_column':[{'port_id':'drive','real':[0]*3,'imag':[0]*3}]}),encoding='utf-8')
            return {'returncode':0,'timed_out':False,'quota_exceeded':False}
        with tempfile.TemporaryDirectory() as directory, patch(
                'extensions.openems_suite.engine._run_isolated_python',side_effect=fake_run):
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                run_assembly_em(request,Path(directory)/'new-run')
