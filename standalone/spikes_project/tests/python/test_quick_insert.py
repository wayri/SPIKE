# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.quick_insert import suggestions


class SuggestionTests(unittest.TestCase):
    def test_common_components_and_monitor_groups(self):
        self.assertEqual(suggestions('')[0]['label'],'Resistor')
        self.assertEqual(suggestions('C')[0]['payload'],'generic.capacitor.001')
        rows=suggestions('meter',category='Monitors');self.assertEqual(len(rows),3)
        self.assertTrue(all(r['kind']=='monitor' for r in rows))
    def test_text_and_spice_are_explicit_and_completion_is_bounded(self):
        rows=suggestions('hello');self.assertEqual(rows[-1]['kind'],'text')
        rows=suggestions('.tr');self.assertTrue(rows[0]['completion']);self.assertTrue(rows[0]['payload'].startswith('.tran '))
        rows=suggestions('.param gain=2');self.assertEqual(rows[0]['kind'],'spice');self.assertIn('text',{r['kind'] for r in rows})
        self.assertLessEqual(len(suggestions('',limit=3)),3)
        with self.assertRaises(ValueError):suggestions('x'*8193)
    def test_manufacturer_readiness_and_source_net_completions(self):
        records=[dict(id='a',manufacturer='TI',mpn='LM358',category='opamp',description='amplifier',model={'readiness':'vendor_model_required'})]
        rows=suggestions('LM358',manufacturers=records);self.assertEqual(rows[0]['kind'],'manufacturer_review')
        rows=suggestions('V(o',nets=['out','other']);self.assertEqual({r['payload'] for r in rows if r['completion']},{'V(out)','V(other)'})


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class QuickInsertTests(unittest.TestCase):
    def test_actual_component_editor_and_monitor_binding(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.quick_insert_popup import insert_component,insert_monitor
        from spikes_studio.component_panel import InsertDialog
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();wx.Yield();before=len(frame.doc.data['components'])
            failures=[];attempts={'edit':0,'bind':0}
            def modal(kind):
                return next((w for w in wx.GetTopLevelWindows() if isinstance(w,wx.Dialog)
                             and w.GetParent() is frame and w.IsModal()
                             and (isinstance(w,InsertDialog) if kind=='edit' else w.GetTitle()=='Bind Mini scope')),None)
            def retry(kind,callback):
                attempts[kind]+=1
                if attempts[kind]<40:wx.CallLater(50,callback);return
                failures.append(kind+' dialog did not become available within 2 seconds')
                for window in wx.GetTopLevelWindows():
                    if isinstance(window,wx.Dialog) and window.GetParent() is frame and window.IsModal():window.EndModal(wx.ID_CANCEL)
            def edit():
                dialog=modal('edit')
                if dialog is None:retry('edit',edit);return
                dialog.parameter_fields['r'].SetValue('10k');dialog.accept()
            wx.CallLater(80,edit);insert_component(frame,frame.catalog_panel.index.by_id['generic.resistor.001'],(700,400))
            self.assertFalse(failures,failures)
            self.assertEqual(len(frame.doc.data['components']),before+1)
            self.assertEqual(frame.doc.data['components'][-1]['value'],'10000')
            self.assertEqual(frame.doc.data['components'][-1]['x'],700)
            def bind():
                dialog=modal('bind')
                if dialog is None:retry('bind',bind);return
                field=wx.FindWindowByName('Monitoring expression',dialog)
                if field is None:retry('bind',bind);return
                field.SetValue('V(out)');dialog.EndModal(wx.ID_OK)
            wx.CallLater(80,bind);insert_monitor(frame,'Mini scope',(500,400))
            self.assertFalse(failures,failures)
            self.assertEqual(frame.doc.data['instruments'][-1]['expression'],'V(out)')
            self.assertEqual(frame.doc.data['instruments'][-1]['kind'],'Mini plot')
            frame.doc.undo();self.assertEqual(frame.doc.data['instruments'],[])
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()

    def test_text_directive_rollback_keyboard_and_position(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.quick_insert_popup import QuickInsert
        from types import SimpleNamespace
        app=wx.GetApp() or wx.App(False);frame=Studio();popup=None
        try:
            popup=QuickInsert(frame,(650,400));popup.query.SetValue('A plain note');popup.accept();popup=None
            self.assertEqual(frame.doc.data['annotations'][-1]['text'],'A plain note')
            self.assertEqual(frame.doc.data['annotations'][-1]['x'],650)
            popup=QuickInsert(frame,(600,450));popup.query.SetValue('.param gain=2');popup.accept();popup=None
            self.assertIn('.param gain=2',frame.doc.data['source'])
            before=frame.doc.data['source'];popup=QuickInsert(frame,(600,450));popup.query.SetValue('.not_a_directive foo');popup.accept()
            self.assertFalse(popup.closed);self.assertEqual(frame.doc.data['source'],before)
            popup.key(SimpleNamespace(GetKeyCode=lambda:wx.WXK_ESCAPE));self.assertTrue(popup.closed);popup=None
        finally:
            if popup and not popup.closed:popup.close()
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()
