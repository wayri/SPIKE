from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.part_properties import field_specs,form,model_names,parse,rewrite


class PartPropertyTests(unittest.TestCase):
    def test_capacitance_value_and_initial_voltage_are_executable(self):
        doc=Document.from_netlist(RC_DECK);part=doc.data['components'][2]
        doc.update([part['id']],{'value':'220u'},model={'mode':'ideal','fields':{'ic':'2.5'}})
        el=parse(doc.data['source']).elements[2]
        self.assertAlmostEqual(el.value,220e-6);self.assertEqual(el.initial_condition,2.5)
        doc.update([part['id']],{'value':'100u'})
        self.assertEqual(parse(doc.data['source']).elements[2].initial_condition,2.5)

    def test_dc_pulse_pwl_selection_rewrites_source(self):
        doc=Document.from_netlist(RC_DECK);ident=doc.data['components'][0]['id']
        doc.update([ident],{'value':'0'},model={'mode':'pulse','fields':{'high':'5','width':'10u','period':'20u','rise':'1n','fall':'1n'}})
        el=parse(doc.data['source']).elements[0]
        self.assertEqual(el.waveform.kind,'pulse');self.assertEqual(el.waveform.pulse[1],5)
        self.assertAlmostEqual(el.waveform.pulse[-1],20e-6)
        doc.update([ident],{},model={'mode':'pwl','fields':{'points':'0 0\n1u 2\n2u 1'}})
        self.assertEqual(parse(doc.data['source']).elements[0].waveform.points,((0.,0.),(1e-6,2.),(2e-6,1.)))
        doc.undo();self.assertEqual(parse(doc.data['source']).elements[0].waveform.kind,'pulse')
        doc.redo();self.assertEqual(parse(doc.data['source']).elements[0].waveform.kind,'pwl')

    def test_dc_value_edit_preserves_ac_phasor(self):
        source=RC_DECK.replace('V1 in 0 1','V1 in 0 DC 1 AC 2 45')
        el=parse(rewrite(source,'V1',{'value':'3'})).elements[0]
        self.assertEqual((el.value,el.ac_magnitude,el.ac_phase_deg),(3,2,45))

    def test_untouched_parameter_bindings_survive_model_edits(self):
        source=RC_DECK.replace('R1 in out 1k','R1 in out {rvalue}').replace('C1 out 0 1u','C1 out 0 {cvalue} IC={initial}').replace('V1 in','.param rvalue=1k cvalue=1u initial=2\nV1 in')
        updated=rewrite(source,'C1',{},model={'mode':'ideal','fields':{'ic':'3'}})
        self.assertIn('C1 out 0 {cvalue} IC=3',updated)
        updated=rewrite(updated,'R1',{'nodes':['in','out']})
        self.assertIn('R1 in out {rvalue}',updated)

    def test_diode_binding_and_private_model_do_not_change_other_instance(self):
        source='Diodes\nI1 0 a 1m\nD1 a 0 shared\nI2 0 b 1m\nD2 b 0 shared\n.model shared D(IS=1p N=1)\n.model alt D(IS=2p N=2)\n.op\n.end\n'
        doc=Document.from_netlist(source);ident=doc.data['components'][1]['id']
        doc.update([ident],{},model={'mode':'named_model','fields':{'model_name':'alt'}})
        self.assertEqual(parse(doc.data['source']).elements[1].model_name,'ALT')
        doc.update([ident],{},model={'mode':'shockley','fields':{'is':'5p','n':'1.5','tnom':'50'}})
        elements=parse(doc.data['source']).elements
        self.assertAlmostEqual(elements[1].diode_model.saturation_current_a,5e-12)
        self.assertIn('TNOM=50',doc.data['source'])
        self.assertEqual(elements[1].diode_model.temperature_k,300.15)  # circuit .TEMP remains authoritative
        self.assertEqual(elements[3].model_name,'SHARED')
        self.assertEqual(elements[3].diode_model.emission_coefficient,1)
        self.assertEqual(form(doc.data['source'],'D1')['mode'],'shockley')

    def test_bad_model_or_pulse_edit_is_atomic(self):
        doc=Document.from_netlist(RC_DECK);before=doc.data['source'];ident=doc.data['components'][0]['id']
        for model in ({'mode':'pulse','fields':{'period':'-1'}},{'mode':'bsim','fields':{}},{'mode':'dc','fields':{'unexpected':'1'}}):
            with self.assertRaises(ValueError):doc.update([ident],{'value':'4'},model=model)
            self.assertEqual(doc.data['source'],before)
        self.assertFalse(doc.undo_stack)

    def test_switch_exposes_and_preserves_four_pins(self):
        source='Switch\nV1 in 0 5\nV2 ctl 0 1\nS1 in out ctl 0 1m 1G .5 1m\nR1 out 0 1k\n.op\n.end\n'
        doc=Document.from_netlist(source);part=doc.data['components'][2]
        self.assertEqual(part['nodes'],['in','out','ctl','0'])
        doc.update([part['id']],{},model={'mode':'smooth_switch','fields':{'ron':'.02'}})
        self.assertEqual(parse(doc.data['source']).elements[2].switch_model.on_resistance_ohm,.02)

    def test_npn_custom_edit_clones_shared_card_and_preserves_expressions(self):
        source=('BJTs\n.param sat=1f cap=2p\nQ1 c1 b1 0 shared\nQ2 c2 b2 0 shared\n'
                '.model shared NPN(IS={sat} BF=100 CBE={cap} TF=3n)\n'
                '.model other NPN(IS=2f BF=50)\n.model wrong NMOS(LEVEL=1 KP=1m)\n.op\n.end\n')
        self.assertEqual(model_names(source,'npn_ebers_moll'),['OTHER','SHARED'])
        item=form(source,'Q1')
        self.assertEqual(item['mode'],'existing_model')
        self.assertEqual(item['fields']['cbe'],'{cap}')
        updated=rewrite(source,'Q1',{},model={'mode':'custom_model','fields':{'bf':'250'}})
        self.assertIn('Q1 c1 b1 0 SPIKES_Q1',updated)
        self.assertIn('.model SPIKES_Q1 NPN(IS={sat} BF=250 CBE={cap} TF=3n)',updated)
        elements=parse(updated).elements
        self.assertEqual(elements[0].model_name,'SPIKES_Q1')
        self.assertEqual(elements[1].model_name,'SHARED')
        self.assertEqual(dict(elements[0].semiconductor_parameters)['forward_alpha'],250/251)
        self.assertEqual(dict(elements[1].semiconductor_parameters)['forward_alpha'],100/101)
        self.assertEqual(form(updated,'Q1')['mode'],'custom_model')

    def test_nested_model_shadow_does_not_replace_top_level_form_binding(self):
        source=('Scoped models\nQ1 c b 0 shared\n.model shared NPN(IS=1f BF=100)\n'
                '.subckt child c b e\nQX c b e shared\n.model shared NPN(IS=9f BF=999)\n'
                '.model nested_only NPN(BF=3)\n.ends child\n.op\n.end\n')
        self.assertEqual(model_names(source,'npn_ebers_moll'),['SHARED'])
        self.assertEqual(form(source,'Q1')['fields']['bf'],'100')
        updated=rewrite(source,'Q1',{},model={'mode':'custom_model','fields':{'nf':'1.2'}})
        self.assertIn('.model SPIKES_Q1 NPN(IS=1f BF=100 NF=1.2)',updated)
        self.assertNotIn('.model SPIKES_Q1 NPN(IS=9f BF=999',updated)

    def test_compact_field_labels_include_meaning_and_units(self):
        npn={key:label for key,label,_ in field_specs('npn_ebers_moll','custom_model')}
        nmos={key:label for key,label,_ in field_specs('nmos_level1','custom_model')}
        wbg={key:label for key,label,_ in field_specs('gan_hemt','custom_model')}
        self.assertEqual(npn['bf'],'Forward current gain BF')
        self.assertIn('[F]',npn['cbe']);self.assertIn('[s]',npn['tf'])
        self.assertIn('[A/V^2]',nmos['kp']);self.assertIn('[1/V]',nmos['lambda'])
        self.assertIn('[K/W]',wbg['thermal_resistance_k_per_w'])
        self.assertIn('[J/K]',wbg['thermal_capacitance_j_per_k'])

    def test_nmos_existing_binding_is_family_filtered_and_tail_is_preserved(self):
        source=('MOS\n.param width=4u length=2u\nM1 d g 0 b first W={width} L={length}\n'
                '.model first NMOS(LEVEL=1 VTO=1 KP=1m CGS=2p)\n'
                '.model second NMOS(LEVEL=1 VTO=2 KP=2m)\n.model bipolar NPN(BF=90)\n.op\n.end\n')
        self.assertEqual(model_names(source,'nmos_level1'),['FIRST','SECOND'])
        updated=rewrite(source,'M1',{'nodes':['drain','0','gate','bulk']},
                        model={'mode':'existing_model','fields':{'model_name':'second'}})
        self.assertIn('M1 drain gate 0 bulk SECOND W={width} L={length}',updated)
        self.assertEqual(parse(updated).elements[0].model_name,'SECOND')
        with self.assertRaises(ValueError):
            rewrite(source,'M1',{},model={'mode':'existing_model','fields':{'model_name':'bipolar'}})

    def test_compact_field_specs_include_parser_backed_dynamic_parameters(self):
        npn={key for key,_,_ in field_specs('npn_ebers_moll','custom_model')}
        nmos={key for key,_,_ in field_specs('nmos_level1','custom_model')}
        gan={key for key,_,_ in field_specs('gan_hemt','custom_model')}
        self.assertTrue({'cbe','cbc','tf','tr'} <= npn)
        self.assertTrue({'cgs','cgd','cds'} <= nmos)
        self.assertTrue({'gate_source_capacitance_f','gate_drain_capacitance_f',
                         'drain_source_capacitance_f','thermal_capacitance_j_per_k'} <= gan)

    def test_wbg_custom_edit_keeps_five_terminal_instance_and_card_fields(self):
        source=('WBG\nZ1 d g 0 b tj ganmod\n'
                '.model ganmod SPK_GAN(THRESHOLD_VOLTAGE_V=2.5 GATE_SOURCE_CAPACITANCE_F=1n '
                'THERMAL_CAPACITANCE_J_PER_K=.01)\n.op\n.end\n')
        updated=rewrite(source,'Z1',{},model={'mode':'custom_model',
                        'fields':{'threshold_voltage_v':'3'}})
        self.assertIn('Z1 d g 0 b tj SPIKES_Z1',updated)
        self.assertIn('GATE_SOURCE_CAPACITANCE_F=1n',updated)
        self.assertIn('THERMAL_CAPACITANCE_J_PER_K=.01',updated)
        self.assertEqual(parse(updated).elements[0].model_name,'SPIKES_Z1')

    def test_bsim_existing_rebind_is_family_filtered_and_preserves_geometry(self):
        cases=(('BSIMBULK','bsim_bulk','BSIMCMG'),('BSIMCMG','bsim_cmg','BSIMBULK'))
        for family,kind,other_family in cases:
            with self.subTest(family=family):
                source=(f'{family}\n.param width=4u\nM1 d g 0 b first W={{width}} L=1u\n'
                        f'.model first {family}(U0=.05 TOXE=1n)\n'
                        f'.model second {family}(U0=.06 TOXE=2n)\n'
                        f'.model wrong {other_family}(U0=.07)\n.op\n.end\n')
                item=form(source,'M1')
                self.assertEqual(item['kind'],kind)
                self.assertEqual(item['options'],[('existing_model',f'Existing .MODEL {family}')])
                self.assertEqual(model_names(source,kind),['FIRST','SECOND'])
                updated=rewrite(source,'M1',{},model={'mode':'existing_model',
                                'fields':{'model_name':'second'}})
                self.assertIn('M1 d g 0 b SECOND W={width} L=1u',updated)
                element=parse(updated).elements[0]
                self.assertEqual((element.kind,element.model_name),(kind,'SECOND'))
                with self.assertRaises(ValueError):
                    rewrite(source,'M1',{},model={'mode':'existing_model',
                            'fields':{'model_name':'wrong'}})
                with self.assertRaises(ValueError):
                    rewrite(source,'M1',{},model={'mode':'custom_model','fields':{}})


if __name__=='__main__':unittest.main()
