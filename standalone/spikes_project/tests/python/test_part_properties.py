from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.part_properties import form,parse,rewrite


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


if __name__=='__main__':unittest.main()
