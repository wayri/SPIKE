# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio import component_package as p
from spikes_studio.document import Document,RC_DECK


class ComponentPackageTests(unittest.TestCase):
    def test_bundled_rc_example_has_explicit_reference_pin(self):
        path=Path(__file__).resolve().parents[2]/'examples/components/rc_lowpass.spkcmp'
        value=p.load(path);self.assertEqual([pin['name'] for pin in value['symbol']['terminals']],['IN','OUT','REF'])
        doc=Document.from_netlist(RC_DECK)
        p.insert(doc,p.prepare_insert(doc,value,{'1':'in','2':'filtered','3':'0'}))
        self.assertIn('XCMP1 in filtered 0 ExampleRC',doc.data['source'])

    def test_custom_transistor_pin_labels_follow_native_node_order(self):
        from spikes_studio.pin_geometry import pins
        for source,mapping,labels,nodes in (
            ('.model MYQ NPN(IS=1p BF=100)\n',{'1':'c','2':'b','3':'e'},['C','E','B'],['c','e','b']),
            ('.model MYM NMOS(LEVEL=1 VTO=1 KP=1m)\n',{'1':'d','2':'g','3':'s','4':'bulk'},['D','S','G','B'],['d','s','g','bulk'])):
            doc=Document.from_netlist(RC_DECK);value=p.from_spice(source)
            ids=p.insert(doc,p.prepare_insert(doc,value,mapping))
            part=next(item for item in doc.data['components'] if item['id']==ids[0])
            self.assertEqual(part['nodes'],nodes);self.assertEqual([pin.label for pin in pins(part)],labels)

    def test_data_only_roundtrip_library_versions_and_conflicts(self):
        value=p.new_component()
        with tempfile.TemporaryDirectory() as root:
            store=p.ComponentStore(root);path=store.install(value)
            self.assertEqual(p.load(path),value);self.assertEqual(len(store.entries()),1)
            changed=deepcopy(value);changed['description']='Changed'
            with self.assertRaisesRegex(ValueError,'bump'):store.install(changed)
            changed['version']='1.0.1';store.install(changed);self.assertEqual(len(store.entries()),2)

    def test_custom_unknown_model_preserved_not_universally_executable(self):
        source='.model FUTURE DIAMOND(alpha=123)\n'
        value=p.from_spice(source,'FUTURE','Z',['D','G','S','B'])
        self.assertEqual(value['implementation']['source'],source)
        doc=Document.from_netlist(RC_DECK);before=deepcopy(doc.data)
        with self.assertRaises(Exception):p.prepare_insert(doc,value,{'1':'d','2':'g','3':'0','4':'0'})
        self.assertEqual(doc.data,before)

    def test_subcircuit_insert_reuse_native_source_and_single_undo(self):
        doc=Document.from_netlist(RC_DECK);value=p.new_component();before=deepcopy(doc.data)
        plan=p.prepare_insert(doc,value,{'1':'out','2':'0'},(700,300))
        self.assertEqual(doc.data,before);p.insert(doc,plan)
        self.assertEqual(len(doc.undo_stack),1);self.assertIn('XCMP1 out 0 UserPart',doc.data['source'])
        self.assertTrue(any(part['ref']=='XCMP1:R1' for part in doc.data['components']))
        plan2=p.prepare_insert(doc,value,{'1':'out','2':'0'});p.insert(doc,plan2)
        self.assertEqual(doc.data['source'].count('.subckt UserPart'),1)
        doc.undo();doc.undo();self.assertEqual(doc.data,before)

    def test_primitive_custom_symbol_and_pin_identity_survive_save(self):
        value=p.from_spice('.model MYD D(IS=1p)\n');doc=Document.from_netlist(RC_DECK)
        plan=p.prepare_insert(doc,value,{'1':'out','2':'0'});ids=p.insert(doc,plan)
        part=next(item for item in doc.data['components'] if item['id']==ids[0])
        from spikes_studio.pin_geometry import pins
        self.assertEqual([pin.label for pin in pins(part)],['A','K'])
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'test.spksch';doc.save(path);loaded=Document.load(path)
            self.assertEqual(next(c for c in loaded.data['components'] if c['id']==part['id'])['parameters'],part['parameters'])

    def test_source_commands_and_vendor_testbench_rejected_without_mutation(self):
        for extra in ('.include other.lib\n','.end\n','.global supply\n','VEXTRA hidden 0 99\n'):
            value=p.new_component();value['implementation']['source']+=extra
            p.validate(value)  # inert preservation is different from insertion
            doc=Document.from_netlist(RC_DECK);before=deepcopy(doc.data)
            with self.assertRaises(ValueError):p.prepare_insert(doc,value,{'1':'out','2':'0'})
            self.assertEqual(doc.data,before)

    def test_pin_order_and_stale_source_and_conflicts_fail_closed(self):
        doc=Document.from_netlist(RC_DECK);value=p.new_component()
        broken=deepcopy(value);broken['symbol']['terminals'].reverse()
        with self.assertRaisesRegex(ValueError,'order'):p.validate(broken)
        plan=p.prepare_insert(doc,value,{'1':'out','2':'0'});doc.commit(lambda data:data['metadata'].update(note='changed'))
        with self.assertRaisesRegex(ValueError,'changed'):p.insert(doc,plan)
        p.insert(doc,p.prepare_insert(doc,value,{'1':'out','2':'0'}))
        fork=deepcopy(value);fork['version']='2.0.0'
        with self.assertRaisesRegex(ValueError,'conflict'):p.prepare_insert(doc,fork,{'1':'out','2':'0'})

    def test_cpp_hash_covers_code_and_pin_interface_not_description(self):
        from spikes_studio.controller_block import DEFAULT_CODE
        value=p.new_component();value['implementation']={'language':'C++','entry':'control_step','source':DEFAULT_CODE,
            'controller':p.controller_config(value['symbol'],DEFAULT_CODE)}
        digest=p.behavior_digest(value);value['description']='New documentation';self.assertEqual(p.behavior_digest(value),digest)
        value['implementation']['source']+='\n';value['implementation']['controller']['source']+='\n'
        self.assertNotEqual(p.behavior_digest(value),digest)

    def test_shape_edit_preserves_pins_and_modes(self):
        from spikes_studio.symbol_design import add_shape,resize,set_pin
        symbol=p.symbol_for_pins(['IN','OUT']);before=deepcopy(symbol['terminals'])
        result=add_shape(symbol,'circle',(0,0),(20,0));self.assertEqual(result['terminals'],before)
        result=resize(result,120,100);self.assertEqual(result['terminals'][1]['mode'],'AO')
        result=set_pin(result,1,'2','OUTPUT','east',0);self.assertEqual(result['terminals'][1]['mode'],'AO')


if __name__=='__main__':unittest.main()
