# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


class ComponentParameterValueTests(unittest.TestCase):
    def test_units_engineering_values_and_sequences(self):
        from spikes_studio.component_parameter_form import field_spec,parse_value
        self.assertEqual(field_spec('r','ohm',100).label,'Resistance')
        self.assertEqual(parse_value('4.7k',field_spec('r','ohm',100)),4700)
        self.assertAlmostEqual(parse_value('100n',field_spec('c','F',1e-6)),1e-7)
        sequence=field_spec('x',None,[-1.,0.,1.])
        self.assertEqual(parse_value('-1, 0, 1',sequence),[-1.,0.,1.])
        scalar=field_spec('x',None,.1)
        self.assertEqual(parse_value('.25',scalar),.25)

    def test_integer_fields_reject_fractional_values(self):
        from spikes_studio.component_parameter_form import field_spec,parse_value
        with self.assertRaisesRegex(ValueError,'integer'):
            parse_value('3.5',field_spec('bits',None,12))
        self.assertEqual(parse_value('16',field_spec('modulus',None,16)),16)


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','Opt-in native parameter-form test')
class ComponentParameterFormTests(unittest.TestCase):
    def test_fields_are_labeled_and_legacy_adapter_is_not_visible_json(self):
        import wx
        from spikes_studio.component_parameter_form import ComponentParameterForm
        app=wx.GetApp() or wx.App(False);parent=wx.Frame(None)
        form=ComponentParameterForm(parent,{'r':1000.},primary_unit='ohm')
        try:
            labels=[child.GetLabel() for child in form.GetChildren() if isinstance(child,wx.StaticText)]
            self.assertIn('Resistance',labels);self.assertIn('ohm',labels)
            self.assertFalse(any(isinstance(child,wx.TextCtrl) and child.IsMultiLine() for child in form.GetChildren()))
            form.SetValue('{"r":4700}')
            self.assertEqual(form.values(),{'r':4700.})
            self.assertEqual(form.fields['r'].GetValue(),'4700')
            form.fields['r'].SetValue('bad draft')
            self.assertEqual(form.raw_values(),{'r':'bad draft'})
            with self.assertRaises(ValueError):form.values()
        finally:parent.Destroy()

    def test_component_panel_draft_search_reset_export_and_validation(self):
        import json
        import tempfile
        import wx
        from spikes_studio.component_panel import ComponentPanel
        from spikes_studio.document import Document,RC_DECK
        from spikes_studio.themes import PALETTES
        app=wx.GetApp() or wx.App(False);owner=wx.Frame(None);host=wx.Panel(owner)
        owner.palette=PALETTES['Light'];owner.doc=Document.from_netlist(RC_DECK)
        owner.pin_browser=lambda:None;owner.open_physics_models=lambda:None;owner.guarded=lambda callback:callback()
        owner.update_title=lambda:None;owner.assign_part_shortcut=lambda _ident:None
        chosen=[];owner.choose_path=lambda *_args:chosen[0] if chosen else None
        panel=ComponentPanel(owner,host)
        try:
            panel.search.ChangeValue('id:generic.resistor.001');panel.filter();panel.list.SetSelection(0);panel.select()
            original=panel.record['parameters']['r'];ident=panel.record['id']
            panel.parameters.fields['r'].SetValue('4.7k');self.assertEqual(panel.edited()['parameters']['r'],4700)
            panel.search.ChangeValue('family:capacitor');panel.filter();panel.list.SetSelection(0);panel.select()
            panel.search.ChangeValue('id:'+ident);panel.filter();panel.list.SetSelection(0);panel.select()
            self.assertEqual(panel.parameters.fields['r'].GetValue(),'4.7k')
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'edited.spkpart';chosen.append(str(path));panel.export()
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['record']['parameters']['r'],4700)
            panel.parameters.fields['r'].SetValue('invalid')
            with self.assertRaises(ValueError):panel.edited()
            panel.reset_draft();self.assertEqual(panel.edited()['parameters']['r'],original)
        finally:panel.Destroy();host.Destroy();owner.Destroy()


if __name__=='__main__':unittest.main()
