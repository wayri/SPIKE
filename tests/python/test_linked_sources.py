# SPDX-License-Identifier: Apache-2.0
"""Saved source refresh preserves occurrences and fails closed on stale reviews."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core.service_linked_sources import handle_linked_source_request, MAX_LINKED_SOURCE_BYTES, _replace_model
from python.spike_core.service_project import import_design
from python.spike_core.project_package import read_project, write_spike_package, _source_member_name
from python.spike_core.mcad_importer import import_mcad_artifact
from python.spike_core.spider_v2 import AssemblyIRV1, BoardInstance
from python.spike_core.spider_v2_schema import CoordinateFrame


def pcb(x):
    return f'''(kicad_pcb (version 20240108) (generator pcbnew)
      (general (thickness 1.6)) (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
      (net 0 "") (net 1 "GND")
      (footprint "test" (layer "F.Cu") (uuid "11111111-1111-4111-8111-111111111111") (at {x} 2)
        (property "Reference" "U1") (property "Value" "Test"))
      (segment (start 0 0) (end {x} 2) (width 0.2) (layer "F.Cu") (net 1) (uuid "22222222-2222-4222-8222-222222222222")))'''.encode()


class LinkedSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'board.kicad_pcb'
        self.source.write_bytes(pcb(1))
        design = import_design(str(self.source), 'kicad_pcb', with_report=True)['design']
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        design['source']['artifact_path'] = 'package:' + _source_member_name(self.source.name, digest)
        self.ident = design['design_id']
        self.project = self.root / 'project.spike'
        board = BoardInstance(id='instance', design_id=self.ident, name='board', frame=CoordinateFrame(frame_id='board-frame', parent_frame_id='assembly'))
        assembly = AssemblyIRV1(assembly_id='assembly', name='assembly', boards=[board])
        self.payload = {'project': {'id':'project', 'name':'Linked'}, 'design_ir':design,
            'assembly_ir':assembly.to_dict(), 'assembly_designs':{'contract':'spike/assembly-designs/v1','active_design_id':self.ident,'designs':[design]},
            'analyses':{'setup':{'keep':True}}, 'results':{'old':42}, 'reports':{'old':42}}
        write_spike_package(self.project, self.payload, source_artifacts={self.source.name:self.source.read_bytes()})

    def request(self, method, **extras):
        return handle_linked_source_request(method, {'project_path':str(self.project),
            'expected_manifest_payload_sha256':read_project(self.project).manifest['manifest_payload_sha256'],
            'target_kind':'board','target_id':self.ident, 'invalidate_results':True, **extras}, request_id=1, application_version='test')

    def link(self):
        response = self.request('link_project_source',path=str(self.source))
        self.assertTrue(response['ok'],response)

    def test_disk_changes_refresh_geometry_and_preserve_instances(self):
        self.link()
        self.assertEqual(self.request('linked_source_status')['result']['status'],'unchanged')
        before=read_project(self.project)
        self.source.write_bytes(pcb(5))
        self.assertEqual(self.request('linked_source_status')['result']['status'],'changed')
        preview=self.request('prepare_linked_source_update')
        self.assertTrue(preview['ok'],preview)
        self.assertIn('snapshot',preview['result']['outcome'])
        response=self.request('apply_linked_source_update',expected_sha256=preview['result']['source']['sha256'])
        self.assertTrue(response['ok'],response)
        after=read_project(self.project)
        self.assertEqual(after.payload['assembly_ir'],before.payload['assembly_ir'])
        self.assertEqual(after.payload['design_ir']['design_id'],self.ident)
        self.assertNotEqual(after.payload['design_ir']['components'],before.payload['design_ir']['components'])
        self.assertNotEqual(after.payload['design_ir']['tracks'],before.payload['design_ir']['tracks'])
        self.assertEqual(after.payload['results'],{})
        self.assertEqual(after.payload['reports'],{})
        self.assertEqual(after.payload['analyses']['setup'],{'keep':True})
        self.assertEqual(self.request('linked_source_status')['result']['status'],'unchanged')
        snapshot=self.project.read_bytes()
        noop=self.request('apply_linked_source_update',expected_sha256=preview['result']['source']['sha256'])
        self.assertTrue(noop['result']['no_op'])
        self.assertEqual(snapshot,self.project.read_bytes())

    def test_active_board_refresh_discards_digest_bound_arrow_cache(self):
        opened=read_project(self.project,include_members=True)
        write_spike_package(self.project,opened.payload,preserved_members=opened.members,generate_geometry_tables=True)
        self.assertTrue(read_project(self.project).payload['geometry']['tables'])
        self.link(); self.source.write_bytes(pcb(4))
        preview=self.request('prepare_linked_source_update')['result']
        response=self.request('apply_linked_source_update',expected_sha256=preview['source']['sha256'])
        self.assertTrue(response['ok'],response)
        after=read_project(self.project,include_members=True)
        self.assertEqual(after.payload['geometry']['tables'],[])
        self.assertFalse(any(name.startswith('geometry/') and name.endswith('.arrow') for name in after.members))

    def test_concurrent_saved_project_change_is_not_overwritten(self):
        self.link(); self.source.write_bytes(pcb(4))
        preview=self.request('prepare_linked_source_update')['result']
        def concurrent_save(path,payload,**kwargs):
            current=read_project(path,include_members=True)
            current.payload['project']['name']='Concurrent edit'
            write_spike_package(path,current.payload,preserved_members=current.members)
            return write_spike_package(path,payload,**kwargs)
        with patch('python.spike_core.service_linked_sources.write_spike_package',side_effect=concurrent_save):
            response=self.request('apply_linked_source_update',expected_sha256=preview['source']['sha256'])
        self.assertFalse(response['ok'],response)
        self.assertEqual(read_project(self.project).payload['project']['name'],'Concurrent edit')
        self.assertEqual(read_project(self.project).payload['design_ir']['source']['source_digest'],hashlib.sha256(pcb(1)).hexdigest())

    def test_existing_legacy_design_setups_survive_and_result_invalidation_is_explicit(self):
        opened=read_project(self.project,include_members=True)
        opened.payload['extensions']={'legacy':{'design':{'component_bonds':[], 'topologies':{'si':{'custom':'keep'}}, 'model_assignments':{'owner':'user'}, 'custom_field':42}}}
        write_spike_package(self.project,opened.payload,preserved_members=opened.members)
        self.link(); self.source.write_bytes(pcb(4))
        preview=self.request('prepare_linked_source_update')['result']
        before=self.project.read_bytes()
        rejected=self.request('apply_linked_source_update',expected_sha256=preview['source']['sha256'],invalidate_results=False)
        self.assertFalse(rejected['ok']); self.assertEqual(before,self.project.read_bytes())
        response=self.request('apply_linked_source_update',expected_sha256=preview['source']['sha256'])
        self.assertTrue(response['ok'],response)
        design=read_project(self.project).payload['extensions']['legacy']['design']
        self.assertEqual(design['topologies'],{'si':{'custom':'keep'}})
        self.assertEqual(design['model_assignments'],{'owner':'user'})
        self.assertEqual(design['custom_field'],42)

    def test_stale_preview_manifest_missing_source_and_path_override(self):
        self.link()
        preview=self.request('prepare_linked_source_update')['result']
        self.source.write_bytes(pcb(3))
        before=self.project.read_bytes()
        bad=self.request('apply_linked_source_update',expected_sha256=preview['source']['sha256'])
        self.assertFalse(bad['ok'])
        self.assertEqual(before,self.project.read_bytes())
        for method in ('linked_source_status','prepare_linked_source_update','apply_linked_source_update'):
            self.assertFalse(self.request(method,path=str(self.source))['ok'])
            self.assertFalse(self.request(method,expected_manifest_payload_sha256='f'*64)['ok'])
        self.source.unlink()
        self.assertEqual(self.request('linked_source_status')['result']['status'],'missing')
        self.assertFalse(self.request('prepare_linked_source_update')['ok'])

    def test_link_mismatch_unlink_and_bounded_reads(self):
        self.source.write_bytes(pcb(8))
        before=self.project.read_bytes()
        self.assertFalse(self.request('link_project_source',path=str(self.source))['ok'])
        self.assertEqual(before,self.project.read_bytes())
        self.source.write_bytes(pcb(1)); self.link()
        with patch('python.spike_core.service_linked_sources.MAX_LINKED_SOURCE_BYTES',8):
            self.assertFalse(self.request('linked_source_status')['ok'])
        self.assertTrue(self.request('link_project_source',unlink=True)['ok'])
        self.assertFalse(self.request('linked_source_status')['ok'])

    def test_removed_entity_reference_blocks_transaction(self):
        self.link()
        opened=read_project(self.project,include_members=True)
        track=opened.payload['design_ir']['tracks'][0]['id']
        opened.payload['analyses']['selected_track']=track
        write_spike_package(self.project,opened.payload,preserved_members=opened.members)
        self.source.write_bytes(pcb(1).replace(b'(uuid "22222222-2222-4222-8222-222222222222")',b'(uuid "33333333-3333-4333-8333-333333333333")'))
        preview=self.request('prepare_linked_source_update')['result']
        before=self.project.read_bytes()
        response=self.request('apply_linked_source_update',expected_sha256=preview['source']['sha256'])
        self.assertFalse(response['ok'],response)
        self.assertEqual(before,self.project.read_bytes())

    def test_changed_step_drops_stale_visuals_and_guards_exact_shape_bindings(self):
        source=self.root/'case.step'
        source.write_bytes(b'ISO-10303-21;\nHEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;')
        outcome=import_mcad_artifact(source)
        old=outcome.to_dict()['model']; part=outcome.to_dict()['part']
        derived={**copy.deepcopy(old), 'id':'derived', 'model_type':'glb', 'extensions':{'spike.mcad.tessellation':{'source_model_id':old['id']}}}
        part['model_id']='derived'; part['extensions']['spike.mcad.tessellation']={'source_model_id':old['id']}
        shape={'shape_id':'shape', 'part_id':part['id']}
        payload={'models':{'models':[old,derived]},'assembly_ir':{'parts':[part]},'assembly_package_shapes':{'shapes':[shape],'constraints':[], 'thermal_contact_bindings':[], 'electrical_bond_bindings':[]}}
        preview={'outcome':outcome.to_dict()}
        contact=copy.deepcopy(payload); contact['assembly_ir']['thermal_contacts']=[{'endpoint_a':{'part_id':part['id']}}]
        with self.assertRaisesRegex(ValueError,'thermal contacts'):
            _replace_model(contact,old,preview,outcome.artifact_bytes)
        guarded=copy.deepcopy(payload); guarded['assembly_package_shapes']['constraints']=[{'references':[{'shape_id':'shape','part_id':part['id']}]}]
        with self.assertRaisesRegex(ValueError,'active constraints'):
            _replace_model(guarded,old,preview,outcome.artifact_bytes)
        _replace_model(payload,old,preview,outcome.artifact_bytes)
        self.assertEqual(payload['assembly_package_shapes']['shapes'],[])
        self.assertEqual(payload['assembly_ir']['parts'][0]['model_id'],old['id'])
        self.assertNotIn('spike.mcad.tessellation',payload['assembly_ir']['parts'][0]['extensions'])
        self.assertEqual([m['id'] for m in payload['models']['models']],[old['id']])

    def test_mechanical_refresh_retains_model_id_part_frame_and_source(self):
        source=self.root/'case.gltf'
        source.write_text(json.dumps({'asset':{'version':'2.0'},'nodes':[{'name':'first'}]}))
        outcome=import_mcad_artifact(source)
        opened=read_project(self.project,include_members=True)
        opened.payload['assembly_ir']['parts']=[outcome.to_dict()['part']]
        model=outcome.to_dict()['model']; model['transform']=[1,0,0,7,0,1,0,8,0,0,1,9,0,0,0,1]; model['extensions']['custom.keep']={'owner':'user'}
        opened.payload['models']={'contract':'spike/model-index/v1','models':[model]}
        write_spike_package(self.project,opened.payload,preserved_members=opened.members,model_artifacts={outcome.artifact_name:outcome.artifact_bytes})
        target={'target_kind':'model','target_id':outcome.model.id}
        self.assertTrue(self.request('link_project_source',path=str(source),**target)['ok'])
        before=read_project(self.project).payload['assembly_ir']['parts'][0]
        source.write_text(json.dumps({'asset':{'version':'2.0'},'nodes':[{'name':'changed'}]}))
        preview=self.request('prepare_linked_source_update',**target)['result']
        response=self.request('apply_linked_source_update',expected_sha256=preview['source']['sha256'],**target)
        self.assertTrue(response['ok'],response)
        after=read_project(self.project,include_members=True)
        part=after.payload['assembly_ir']['parts'][0]
        self.assertEqual(part['frame'],before['frame'])
        self.assertEqual(part['id'],before['id'])
        self.assertEqual(part['model_id'],outcome.model.id)
        model=after.payload['models']['models'][0]
        self.assertEqual(model['transform'],[1,0,0,7,0,1,0,8,0,0,1,9,0,0,0,1])
        self.assertEqual(model['extensions']['custom.keep'],{'owner':'user'})
        self.assertEqual(model['digest'],hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(after.members[model['uri'].removeprefix('package:')],source.read_bytes())


if __name__=='__main__': unittest.main()
