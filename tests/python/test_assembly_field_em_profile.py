# SPDX-License-Identifier: Apache-2.0
"""Original bounded EM profile and source-grid placement roundoff oracles."""
import copy
import itertools
import json
from pathlib import Path
import unittest
from python.spike_core.assembly_field_handoff import field_resource_limits, prepare_assembly_field_handoff
from python.spike_core.assembly_field_geometry import assert_disjoint_occurrences
from tests.python.test_assembly_tetra_thermal import cube
from tests.python.test_assembly_field_handoff import fixture


def fine_request(edge=1e-6,translation=321.4321):
    request,_=fixture();request['domain']='em';request['assembly']['boards']=[]
    request['assembly']['thermal_contacts']=[]
    request['assembly']['parts'][0]['frame']['transform'][3]=translation
    body=request['bodies'][1];request['bodies']=[body]
    points=[[.137,0.,0.],[.137+edge,0.,0.],[.137,1.,0.],[.137,0.,.035]]
    body['mesh']={'contract':'spike/solver-mesh/v1','units':'mm','coordinate_system':'right_handed_xyz',
        'vertices':points,'cells':[{'id':'0','kind':'tetrahedron','vertices':[0,1,2,3],
        'material_id':'k','source_object_ids':['source']}],
        'counts':{'vertices':4,'cells':1},'object_map':{'source':{'kind':'solid'}}}
    body['boundary_faces']=[{'id':str(i),'vertices':list(f)} for i,f in enumerate(itertools.combinations(range(4),3))]
    request['materials']=[{'id':'slab','conductivity_s_m':1.,'relative_permittivity':1.,
        'relative_permeability':1.,'provenance':'original fine-edge placement oracle'}]
    return request


class ProfileTests(unittest.TestCase):
    def test_published_schema_profile_is_em_only(self):
        from jsonschema import Draft202012Validator,ValidationError
        from referencing import Registry,Resource
        from python.spike_core.spider_v2 import AssemblyIRV1
        root=Path(__file__).resolve().parents[2];registry=Registry()
        for name in ('assembly-ir-v1','design-ir-v2','assembly-placement-policy-v1','solver-mesh-v1'):
            raw=json.loads((root/'schemas'/f'{name}.schema.json').read_text())
            registry=registry.with_resource(raw['$id'],Resource.from_contents(raw))
        schema=json.loads((root/'schemas/assembly-field-handoff-request-v1.schema.json').read_text())
        validator=Draft202012Validator(schema,registry=registry)
        request=fine_request();request['resource_profile']='routed_pcb_em_v1'
        request['assembly']=json.loads(json.dumps(AssemblyIRV1.from_dict(request['assembly']).to_dict()))
        validator.validate(request)
        request['domain']='si'
        with self.assertRaises(ValidationError):validator.validate(request)

    def test_defaults_and_domain_gate(self):
        self.assertEqual(field_resource_limits({})['max_control_bytes'],8*1024**2)
        for domain in ['thermal','si',None]:
            with self.assertRaisesRegex(ValueError,'EM-only'):
                field_resource_limits({'domain':domain,'resource_profile':'routed_pcb_em_v1'})
        with self.assertRaises(ValueError):field_resource_limits({'domain':'em','resource_profile':'unknown'})
        self.assertEqual(field_resource_limits({'domain':'em','resource_profile':'routed_pcb_em_v1'})['max_cells'],600000)

    def test_em_region_mesh_cannot_be_promoted_to_thermal_handoff(self):
        request,_=fixture()
        request['bodies'][0]['mesh']['object_map']['shared-source']['kind']='em_material_region'
        with self.assertRaisesRegex(ValueError,'global FEM conformity'):
            prepare_assembly_field_handoff(request)

    def test_source_grid_translation_has_bounded_certificate_and_default_rejects(self):
        request=fine_request()
        with self.assertRaisesRegex(ValueError,'Jacobian accuracy'):prepare_assembly_field_handoff(request)
        request['resource_profile']='routed_pcb_em_v1';before=copy.deepcopy(request)
        result=prepare_assembly_field_handoff(request)
        self.assertEqual(request,before)
        trace=result['source_traceability'][0]
        self.assertEqual(trace['cell_map'],{'0':'cell:0:0'})
        self.assertEqual(trace['placement_audit']['roundoff_bounded_cells'],1)
        self.assertLess(trace['placement_audit']['maximum_normalized_jacobian_perturbation'],1e-6)
        self.assertGreater(trace['placement_audit']['maximum_frobenius_condition'],1e5)
        self.assertEqual(prepare_assembly_field_handoff(json.loads(json.dumps(request,sort_keys=True))),result)

    def test_compact_source_ids_are_stable_across_json_key_order(self):
        request=fine_request();request['resource_profile']='routed_pcb_em_v1'
        mesh=request['bodies'][0]['mesh'];mesh['object_map']={'z-source':{'kind':'solid'},'a-source':{'kind':'solid'}}
        mesh['cells'][0]['source_object_ids']=['z-source','a-source']
        self.assertEqual(prepare_assembly_field_handoff(request),
                         prepare_assembly_field_handoff(json.loads(json.dumps(request,sort_keys=True))))

    def test_precision_loss_above_bound_rejected(self):
        for edge,translation in [(1e-9,114.2111),(1e-6,1e8)]:
            request=fine_request(edge,translation);request['resource_profile']='routed_pcb_em_v1'
            with self.subTest(edge=edge,translation=translation),self.assertRaises(ValueError):
                prepare_assembly_field_handoff(request)

    def test_spatial_hierarchy_preserves_overlap_and_touching_decisions(self):
        a=cube()
        for offset,overlap in [(1.,False),(.5,True),(2.,False)]:
            b=cube(origin=offset);mesh=copy.deepcopy(a)
            mesh['vertices']+=b['vertices']
            mesh['cells'] += [{**c,'vertices':[v+8 for v in c['vertices']]} for c in b['cells']]
            owners=['a']*6+['b']*6
            for indexed in [False,True]:
                if overlap:
                    with self.assertRaisesRegex(ValueError,'OVERLAP'):
                        assert_disjoint_occurrences(mesh,owners,spatial_index=indexed)
                else:
                    self.assertEqual(assert_disjoint_occurrences(mesh,owners,spatial_index=indexed)['inter_occurrence_comparisons'],0)


if __name__=='__main__':unittest.main()
