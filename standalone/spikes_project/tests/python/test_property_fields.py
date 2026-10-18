# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','Native wx property form test')
class PropertyFieldTests(unittest.TestCase):
    def setUp(self):
        import wx
        self.app=wx.GetApp() or wx.App(False)
        self.parent=wx.Frame(None)

    def tearDown(self):
        self.parent.Destroy()

    def test_labeled_limits_and_unknown_metadata_survive(self):
        from spikes_studio.property_fields import PropertyFields
        limits=PropertyFields(self.parent,{'power_w':.25,'custom_limit':7},kind='limits')
        limits.controls['voltage_v'][0].SetValue('50')
        self.assertEqual(json.loads(limits.GetValue()),{'power_w':.25,'voltage_v':50,'custom_limit':7})
        limits.controls['power_w'][0].SetValue('-2')
        with self.assertRaises(ValueError):limits.GetValue()
        meta={'note':'measured','nested':{'keep':3},'count':2}
        form=PropertyFields(self.parent,meta,kind='parameters')
        form.controls['note'][0].SetValue('reviewed')
        self.assertEqual(json.loads(form.GetValue()),{**meta,'note':'reviewed'})

    def test_pin_fields_preserve_order_and_mixed_edits_fail_closed(self):
        from spikes_studio.property_fields import PropertyFields
        pins=PropertyFields(self.parent,['a','0','s'],kind='nodes')
        pins.controls[2][0].SetValue('substrate')
        self.assertEqual(json.loads(pins.GetValue()),['a','0','substrate'])
        mixed=PropertyFields(self.parent,{'power_w':1},kind='limits',mixed=True)
        self.assertEqual(mixed.GetValue(),'<multiple values>')
        mixed.controls['power_w'][0].SetValue('2')
        with self.assertRaises(ValueError):mixed.GetValue()

    def test_thermal_inputs_preserve_metadata_and_reject_invalid_ranges(self):
        from spikes_studio.thermal_assessment_fields import ThermalAssessmentFields
        metadata={'retained':{'calibration':'unchanged'},'thermal_assessment':{'custom_evidence':'retained'}}
        form=ThermalAssessmentFields(self.parent,[{'parameters':metadata}])
        form.controls['theta_ja_k_w'].SetValue('20')
        form.controls['steady_power_w'].SetValue('250m')
        form.controls['ambient_c'].SetValue('25')
        form.controls['conditions_evidence'].SetValue('Measured board and airflow')
        result=form.merge(metadata)
        self.assertEqual(result['retained'],metadata['retained'])
        self.assertEqual(result['thermal_assessment']['custom_evidence'],'retained')
        self.assertEqual(result['thermal_assessment']['steady_power_w'],.25)
        form.controls['theta_ja_k_w'].SetValue('-1')
        with self.assertRaises(ValueError):form.merge(metadata)
        form.controls['theta_ja_k_w'].SetValue('20')
        form.controls['ambient_c'].SetValue('-300')
        with self.assertRaises(ValueError):form.merge(metadata)

    def test_capacitor_policy_lowers_to_actual_parasitics_and_honors_lock(self):
        from copy import deepcopy
        from spikes_studio.document import Document,RC_DECK
        from spikes_studio.property_fields import CapacitorModelFields
        from spikes_studio.model_fidelity import preflight
        doc=Document.from_netlist(RC_DECK)
        cap=doc.data['components'][2]
        model=CapacitorModelFields(self.parent,doc.data,[cap])
        model.choice.SetSelection(2);model.refresh()
        model.fields['esr_ohm'].SetValue('20m');model.fields['esl_h'].SetValue('5n')
        model.apply_to(doc.data)
        report=preflight(deepcopy(doc.data))
        self.assertIn('RSPKPAR_C1',report['effective_source'])
        self.assertIn('LSPKPAR_C1',report['effective_source'])
        self.assertAlmostEqual(doc.data['model_policy']['components']['C1']['parasitic_values']['esr_ohm'],.02)
        doc.data['model_policy']['schematic']['enforce']=True
        locked=CapacitorModelFields(self.parent,doc.data,[cap])
        self.assertFalse(locked.editable)
        self.assertFalse(locked.choice.IsEnabled())

    def test_properties_apply_value_and_model_as_one_undo_transaction(self):
        from spikes_studio.desktop import Studio,Properties
        from spikes_studio.document import Document,RC_DECK
        frame=Studio(None)
        frame.doc=Document.from_netlist(RC_DECK)
        frame.canvas.selected={frame.doc.data['components'][2]['id']}
        dialog=Properties(frame)
        dialog.EndModal=lambda result:None
        try:
            before=frame.doc.data['source']
            dialog.fields['value'].SetValue('220u')
            dialog.capacitor_model.choice.SetSelection(2);dialog.capacitor_model.refresh()
            dialog.capacitor_model.fields['esr_ohm'].SetValue('50m')
            dialog.apply()
            self.assertTrue(dialog.applied)
            self.assertEqual(len(frame.doc.undo_stack),1)
            self.assertEqual(frame.doc.data['model_policy']['components']['C1']['parasitic_values']['esr_ohm'],.05)
            frame.doc.undo()
            self.assertEqual(frame.doc.data['source'],before)
            self.assertNotIn('C1',frame.doc.data['model_policy']['components'])
        finally:
            dialog.Destroy();frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()


if __name__=='__main__':unittest.main()
