# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.directive_forms import SPECS,new_form,parse_directive,type_key_for


class DirectiveFormTests(unittest.TestCase):
    def test_supported_cards_round_trip_byte_for_byte(self):
        cards=['.tran 10u 5m uic','.ac dec 20 1 1meg','.dc V1 0 5 .1','.op',
               '.noise V(out) V1 dec 20 1 1meg','.tf V(out) V1','.pz in 0 out 0 vol pz',
               '.sens V(out) ac dec 10 1 1k','.disto dec 20 1 1meg .9','.four 1k V(out) V(in)',
               '.temp 25 50','.ic V(out)=0 V(in)=1','.nodeset V(out)=0','.param gain={2 * base}',
               '.step param gain list 1 2 4','.options reltol=1e-3 method=gear',
               '.measure tran average_out AVG V(out) FROM=1m TO=5m']
        for card in cards:
            with self.subTest(card=card):
                form=parse_directive(card);self.assertIsNotNone(form);self.assertEqual(form.render(),card)

    def test_editing_fields_renders_expected_cards(self):
        form=parse_directive('.tran 10u 5m uic');form.values[1]='10m'
        self.assertEqual(form.render(),'.tran 10u 10m uic')
        form=new_form('ac');form.values=['oct','12','10','100k']
        self.assertEqual(form.render(),'.ac oct 12 10 100k')
        form=new_form('dc');form.values=['Iload','0','2','0.05','Vbias 0 1 .1']
        self.assertEqual(form.render(),'.dc Iload 0 2 0.05 Vbias 0 1 .1')

    def test_rendered_priority_forms_pass_document_edit_validation(self):
        from spikes_studio.document import Document,RC_DECK
        doc=Document.from_netlist(RC_DECK);ident=doc.data['directives'][0]['id']
        tran=parse_directive('.tran 10u 5m uic');tran.values[1]='8m'
        doc.edit_directive(ident,text=tran.render(),enabled=True,group=tran.spec.group)
        self.assertIn('.tran 10u 8m uic',doc.data['source'])
        temp=new_form('temp')
        added=doc.edit_directive(text=temp.render(),enabled=True,group=temp.spec.group)
        self.assertEqual(next(v['text'] for v in doc.data['directives'] if v['id']==added),'.temp 25')

    def test_malformed_or_complex_unsafe_cards_fall_back_to_raw(self):
        for card in ('','.tran 1u','.ac dec twenty 1 2','.ac weird 10 1 2','.op extra','.param x=1\n+ y=2',
                     '.measure tran only_name','.unknown value','.pz V(out) V1 cur pz','.disto dec 20 1 1meg .9 extra'):
            with self.subTest(card=card):self.assertIsNone(parse_directive(card))

    def test_type_detection_and_all_defaults_render(self):
        self.assertEqual(type_key_for('.temp 25'),'temp')
        for spec in SPECS:
            with self.subTest(kind=spec.key):self.assertTrue(new_form(spec.key).render().startswith('.'+spec.key))

    def test_each_form_has_one_label_per_value_and_step_fields(self):
        for spec in SPECS:self.assertEqual(len(spec.fields),len(spec.defaults),spec.key)
        form=parse_directive('.step param r 1k 4k 1k');form.values[3]='8k'
        self.assertEqual(form.render(),'.step param r 1k 8k 1k')
        form=parse_directive('.step param r list 1k 2k');form.values[2]='1k 4k'
        self.assertEqual(form.render(),'.step param r list 1k 4k')


if __name__=='__main__':unittest.main()
