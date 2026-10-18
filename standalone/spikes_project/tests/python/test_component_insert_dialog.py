# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','Opt-in native insertion dialog test')
class ComponentInsertDialogTests(unittest.TestCase):
    def test_value_first_parameters_and_isolated_pins(self):
        import wx
        from spikes_studio.component_panel import InsertDialog
        from spikes_studio.component_catalog import catalog
        from spikes_studio.document import Document,RC_DECK
        from spikes_studio.library_browser import insertion_plan,apply_insertion
        from spikes_studio.themes import PALETTES
        app=wx.GetApp() or wx.App(False);parent=wx.Frame(None)
        owner=SimpleNamespace(palette=PALETTES['Light'],doc=Document.from_netlist(RC_DECK));parent.owner=owner
        record=next(r for r in catalog()['records'] if r['family']=='resistor')
        a=InsertDialog(parent,record);b=InsertDialog(parent,record)
        try:
            self.assertEqual(a.book.GetPageText(a.book.GetSelection()),'Value & parameters')
            self.assertEqual(a.book.GetPageText(1),'Pins & connections')
            self.assertTrue(all(c.GetParent()==a.book.GetPage(1) for c in a.pins.values()))
            self.assertTrue(all(c.GetValue()!='0' for c in a.pins.values()))
            self.assertNotEqual(a.pins['P'].GetValue(),b.pins['P'].GetValue())
            a.parameter_fields['r'].SetValue('4.7k');edited=a.edited_record();self.assertEqual(edited['parameters']['r'],4700)
            plan=insertion_plan(owner.doc,edited,{p:c.GetValue() for p,c in a.pins.items()},count=2,primitive=True)
            apply_insertion(owner.doc,plan,edited['id'])
            added=[p for p in owner.doc.data['components'] if p['ref'] not in ('V1','R1','C1')]
            self.assertEqual(len(added),2);self.assertTrue(all(float(p['value'])==4700 for p in added))
            self.assertTrue(set(added[0]['nodes']).isdisjoint(added[1]['nodes']))
            ground=next(p for p in owner.doc.data['components'] if p['ref']=='V1')
            owner.doc.connect((ground['id'],1),(added[0]['id'],1))
            self.assertEqual(next(p for p in owner.doc.data['components'] if p['id']==added[0]['id'])['nodes'][1],'0')
            a.parameter_fields['r'].SetValue('not a value')
            with self.assertRaises(ValueError):a.edited_record()
        finally:a.Destroy();b.Destroy();parent.Destroy()

    def test_manufacturer_selection_and_custom_draft_are_preserved(self):
        import wx
        from spikes_studio.component_panel import InsertDialog,ComponentPanel
        from spikes_studio.component_catalog import catalog
        from spikes_studio.document import Document,RC_DECK
        from spikes_studio.themes import PALETTES
        from spikes_studio.manufacturer_parts import install
        app=wx.GetApp() or wx.App(False);parent=wx.Frame(None)
        owner=SimpleNamespace(palette=PALETTES['Light'],doc=Document.from_netlist(RC_DECK));parent.owner=owner
        record=next(r for r in catalog()['records'] if r['family']=='resistor');dialog=InsertDialog(parent,record)
        try:
            dialog.parameter_fields['r'].SetValue('4.7k')
            dialog.part_search.SetValue('yageo');dialog.filter_library()
            self.assertGreater(len(dialog.library_rows),1);self.assertEqual(dialog.parameter_fields['r'].GetValue(),'4.7k')
            dialog.part_choice.SetSelection(1);dialog.select_library();edited=dialog.edited_record()
            self.assertFalse(dialog.parameter_fields['r'].IsEnabled())
            self.assertEqual(edited['exact_mpn'],dialog.library_record['mpn'])
            plan=install(owner.doc,dialog.library_record,{p:c.GetValue() for p,c in dialog.pins.items()},primitive=True)
            added=next(p for p in owner.doc.data['components'] if p['ref'] in plan['refs'])
            self.assertEqual(added['parameters']['manufacturer_part']['mpn'],edited['exact_mpn'])
            self.assertIn('not manufacturer-qualified',added['evidence'])
            dialog.part_choice.SetSelection(0);dialog.select_library();self.assertEqual(dialog.parameter_fields['r'].GetValue(),'4.7k')
        finally:dialog.Destroy();parent.Destroy()

    def test_unavailable_library_model_disables_placement(self):
        import wx
        from spikes_studio.component_panel import InsertDialog
        from spikes_studio.component_catalog import catalog
        from spikes_studio.document import Document,RC_DECK
        from spikes_studio.themes import PALETTES
        app=wx.GetApp() or wx.App(False);parent=wx.Frame(None);parent.owner=SimpleNamespace(palette=PALETTES['Light'],doc=Document.from_netlist(RC_DECK))
        record=next(r for r in catalog()['records'] if r['family']=='led');dialog=InsertDialog(parent,record)
        try:
            dialog.part_choice.SetSelection(1);dialog.select_library()
            self.assertFalse(dialog.FindWindow(wx.ID_OK).IsEnabled())
            with self.assertRaises(ValueError):dialog.edited_record()
        finally:dialog.Destroy();parent.Destroy()
