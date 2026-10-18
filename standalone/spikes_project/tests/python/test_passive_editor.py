# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in wx')
class PassiveEditorTests(unittest.TestCase):
    def test_values_package_coefficients_and_kelvin_pins(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.component_panel import InsertDialog
        from spikes_studio.passive_catalog import make_record,model
        app=wx.GetApp() or wx.App(False);frame=Studio();dialog=None
        try:
            frame.Show();self.assertEqual(len(frame.catalog_panel.catalog['records']),7908)
            dialog=InsertDialog(frame.catalog_panel,make_record('resistor',100))
            dialog.package_choice.SetStringSelection('01005');dialog.construction_choice.SetStringSelection('Thin film')
            for key,value in {'r':'1.234k','tolerance_percent':'.05','corner':'1','temperature_c':'125','tc1_per_k':'50u'}.items():dialog.parameter_fields[key].SetValue(value)
            edited=dialog.edited_record();self.assertEqual(edited['package_code'],'01005');self.assertEqual(edited['construction'],'Thin film')
            self.assertAlmostEqual(model(edited)['effective_value'],1234*1.0005*1.005)
            nearest=wx.FindWindowByLabel('Use nearest preferred value',dialog)
            event=wx.CommandEvent(wx.wxEVT_BUTTON,nearest.GetId());nearest.GetEventHandler().ProcessEvent(event)
            self.assertEqual(dialog.parameter_fields['r'].GetValue(),'1230')
            self.assertFalse(dialog.parameter_fields['contact_resistance_ohm'].IsEnabled())
            self.assertEqual([dialog.book.GetPageText(i) for i in range(dialog.book.GetPageCount())],['Value & parameters','Parasitics & temperature','Pins & connections'])
            dialog.Destroy();dialog=InsertDialog(frame.catalog_panel,make_record('kelvin_shunt',.001))
            self.assertEqual(set(dialog.pins),{'FP','FN','SP','SN'})
            self.assertFalse(dialog.parameter_fields['parallel_capacitance_f'].IsEnabled())
            self.assertTrue(dialog.parameter_fields['contact_resistance_ohm'].IsEnabled())
            self.assertTrue(all(len(r['pins'])==4 for r in dialog.library_rows if r))
        finally:
            if dialog:dialog.Destroy()
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()


if __name__=='__main__':unittest.main()
