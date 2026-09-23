"""Actual library search, draft/preview, modal insertion and canvas event tests."""
from copy import deepcopy
from pathlib import Path
import time
import wx
from .document import write_json
from .component_panel import InsertDialog
from .ui_evidence import capture_window


def verify_browser(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);checks={};panel=frame.catalog_panel;timings=[]
    import sys,traceback,faulthandler
    debug_stream=(destination/'native-trace.txt').open('w');frame.browser_debug_stream=debug_stream;faulthandler.enable(file=debug_stream)
    def exception_hook(kind,value,tb):
        write_json(destination/'unhandled.json',{'error':str(value),'traceback':''.join(traceback.format_exception(kind,value,tb))})
        frame.validation_failure=True;frame.timer.Stop();frame.Destroy()
    sys.excepthook=exception_hook
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
        write_json(destination/f'progress-{len(checks):02}.json',checks)
    def fail(exc):
        import traceback
        frame.validation_failure=True;write_json(destination/'error.json',{'error':str(exc),'traceback':traceback.format_exc(),'checks':checks});frame.timer.Stop();frame.Destroy()
    def run():
        try:
            frame.book.SetSelection(11);panel.fit_initial_layout();panel.search.ChangeValue('family:resistor');panel.filter()
            check(len(panel.visible)==50,'field search finds resistor family')
            check(bool(panel.list.GetWindowStyleFlag()&wx.LC_VIRTUAL),'results use native virtual list rows')
            panel.list.SetSelection(0);panel.select();ident=panel.record['id'];panel.parameters.SetValue('{"r":1234}')
            check('1234' in panel.recipe.GetValue(),'native SPICE preview reflects edited parameter draft')
            panel.search.ChangeValue('family:capacitor');panel.filter();panel.list.SetSelection(0);panel.select()
            panel.search.ChangeValue('family:resistor');panel.filter();panel.list.SetSelection(next(i for i,r in enumerate(panel.visible) if r['id']==ident));panel.select()
            check(panel.edited()['parameters']['r']==1234,'parameter drafts survive searches and selection changes')
            panel.toggle_favorite();panel.favorite_only.SetValue(True);panel.filter();check(len(panel.visible)==1,'project favorite filter works')
            panel.favorite_only.SetValue(False);panel.minimum.ChangeValue('500');panel.maximum.ChangeValue('2000');panel.sort.SetStringSelection('Primary value');panel.descending.SetValue(True);panel.filter()
            values=[r['parameters']['r'] for r in panel.visible];check(values==sorted(values,reverse=True) and all(500<=v<=2000 for v in values),'numeric range and descending sort use actual primary values')
            panel.minimum.ChangeValue('');panel.maximum.ChangeValue('');panel.sort.SetStringSelection('Name');panel.filter();panel.list.SetSelection(next(i for i,r in enumerate(panel.visible) if r['id']==ident));panel.select()
            for text in ('resistor','family:capacitor','category:"Basic RF"','status:native','unit:V -reference'):
                start=time.perf_counter();panel.index.query(text);timings.append((time.perf_counter()-start)*1000)
            capture_window(frame,destination/'browser-preview-dark.png')
            frame.set_theme('Light',save=False);capture_window(frame,destination/'browser-preview-light.png');frame.set_theme('Dark',save=False)
            before=deepcopy(frame.doc.data)
            def accept_dialog():
                try:
                    dialog=next(w for w in wx.GetTopLevelWindows() if isinstance(w,InsertDialog))
                    dialog.count.SetValue(3);dialog.pins['P'].SetValue('placed_{n}');dialog.pins['N'].SetValue('0');dialog.place.SetValue(True)
                    capture_window(dialog,destination/'multi-instance-dialog.png');dialog.EndModal(wx.ID_OK)
                except Exception as exc:fail(exc)
            wx.CallLater(200,accept_dialog)
            event=wx.ListEvent(wx.wxEVT_LIST_ITEM_ACTIVATED,panel.list.GetId());panel.list.GetEventHandler().ProcessEvent(event)
            check(frame.pending_library_placement is not None,'double-click activates reviewed click-to-place insertion')
            check(frame.doc.data==before,'arming placement does not mutate the circuit')
            event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(frame.canvas.point(180,360));frame.canvas.GetEventHandler().ProcessEvent(event)
            check(frame.pending_library_placement is None,'canvas click commits insertion and clears placement mode')
            added=[p for p in frame.doc.data['components'] if p['ref'].startswith('XCAT')]
            check(len(added)==3 and {p['nodes'][0] for p in added}=={'placed_1','placed_2','placed_3'},'three actual instances use separate expanded nets')
            check(all(p['value']=='1234' for p in added),'inserted primitives use the edited parameter value')
            check(frame.doc.data['source'].lower().count('.subckt ')==1,'batch reuses one content-specific subcircuit definition')
            capture_window(frame,destination/'three-instances.png')
            frame.doc.undo();frame.refresh_document();check(frame.doc.data==before,'one undo restores source layout and metadata')
            frame.doc.redo();frame.refresh_document();check(len(frame.doc.data['components'])==len(before['components'])+3,'redo restores all instances')
            panel.recent_only.SetValue(True);panel.filter();check(len(panel.visible)==1 and panel.visible[0]['id']==ident,'recent insert filter uses project history')
            frame.pending_library_placement=(panel.edited(),{'P':'next_{n}','N':'0'},2);snapshot=deepcopy(frame.doc.data)
            event=wx.KeyEvent(wx.wxEVT_KEY_DOWN);event.SetKeyCode(wx.WXK_ESCAPE);frame.canvas.GetEventHandler().ProcessEvent(event)
            check(frame.pending_library_placement is None and frame.doc.data==snapshot,'Escape cancels placement without mutation')
            panel.reset_filters();panel.search.ChangeValue('family:npn');panel.filter();panel.list.SetSelection(0);panel.select();check(not panel.insert_button.IsEnabled(),'bench-only presets cannot be inserted as native parts')
            frame.SetSize((1760,1000));check(True,'begin docking layout');frame.pin_browser(True);check(True,'browser pin returned');wx.Yield()
            check(panel.GetParent() is frame.browser_side and panel.right.GetSplitMode()==wx.SPLIT_HORIZONTAL,'same browser docks with stacked list and preview')
            check(panel.record['family']=='npn','docking preserves browser selection and state')
            pane=frame.docks.GetPane('browser');pane.Float().FloatingPosition((50,130)).FloatingSize((480,700));frame.docks.Update();wx.Yield()
            check(pane.IsFloating() and panel.GetParent() is frame.browser_side,'browser can float without replacing its controls')
            pane.Dock().Left();frame.docks.Update();wx.Yield();check(not pane.IsFloating(),'browser redocks into the workspace')
            resistor=next(p for p in frame.doc.data['components'] if p['ref']=='R1');capacitor=next(p for p in frame.doc.data['components'] if p['ref']=='C1')
            frame.canvas.selected={resistor['id']};check(True,'before properties pin');frame.pin_properties(True);check(True,'properties pin returned');frame.sync_properties();editor=frame.properties_editor
            editor.fields['value'].SetValue('2k');check(True,'properties draft changed');editor.apply();check(True,'properties apply returned');wx.Yield();check(True,'properties refresh returned')
            check(next(p for p in frame.doc.data['components'] if p['ref']=='R1')['value']=='2k','pinned properties apply actual electrical value')
            editor=frame.properties_editor;editor.fields['value'].SetValue('3k');frame.canvas.selected={capacitor['id']};frame.sync_properties()
            check(frame.properties_editor is editor and editor.fields['value'].GetValue()=='3k','selection change retains unapplied properties draft')
            frame.pin_properties(False);frame.pin_properties(True)
            check(frame.properties_editor is editor,'hiding and repinning preserves properties draft')
            frame.doc.commit(lambda d:d['metadata'].update({'browser_regression':'stale-edit-guard'}));snapshot=deepcopy(frame.doc.data);editor.apply()
            check(frame.doc.data==snapshot and not editor.applied,'stale pinned properties cannot overwrite a changed circuit')
            frame.sync_properties(True);check(frame.properties_editor.ids==[capacitor['id']],'explicit reload switches draft to selected component')
            capture_window(frame,destination/'pinned-panels-dark.png');frame.set_theme('Light',save=False);capture_window(frame,destination/'pinned-panels-light.png');frame.set_theme('Dark',save=False)
            frame.SetSize((1320,880));wx.Yield();capture_window(frame,destination/'pinned-panels-compact.png')
            check(panel.list.GetSize().height<=250,'compact list does not grow at the expense of the symbol preview')
            check(panel.preview_page.GetVirtualSize().height>=panel.preview_page.GetClientSize().height,'small-window preview retains scroll access to parameters')
            frame.pin_properties(False);frame.pin_browser(False);wx.Yield()
            check(panel.GetParent() is frame.catalog_host and panel.right.GetSplitMode()==wx.SPLIT_VERTICAL,'unpin restores full browser without duplicate instances')
            frame.book.SetSelection(0);frame.canvas.SetFocus();wx.Yield();frame.toggle_part_shortcuts(False);snapshot=deepcopy(frame.doc.data)
            event=wx.CommandEvent(wx.wxEVT_MENU,frame.ids['part.resistor']);frame.GetEventHandler().ProcessEvent(event)
            check(frame.pending_library_placement is None and frame.doc.data==snapshot,'disabled placement command cannot add or arm parts')
            frame.toggle_part_shortcuts(True);frame.source.SetFocus();wx.Yield();frame.GetEventHandler().ProcessEvent(event)
            check(frame.pending_library_placement is None,'part shortcut is suppressed in text editors')
            frame.book.SetSelection(0);frame.canvas.SetFocus();wx.Yield()
            def accept_shortcut():
                dialog=next(w for w in wx.GetTopLevelWindows() if isinstance(w,InsertDialog));dialog.EndModal(wx.ID_OK)
            wx.CallLater(150,accept_shortcut);frame.GetEventHandler().ProcessEvent(event)
            check(frame.pending_library_placement is not None and frame.pending_library_placement[0]['family']=='resistor','resistor shortcut opens reviewed placement workflow')
            event=wx.KeyEvent(wx.wxEVT_KEY_DOWN);event.SetKeyCode(wx.WXK_ESCAPE);frame.canvas.GetEventHandler().ProcessEvent(event)
            check(frame.doc.data==snapshot,'shortcut review and cancel leave document unchanged')
            write_json(destination/'checks.json',{'checks':checks,'query_ms':timings,'cache_state':'mixed warm and cold queries','catalog_records':5000});frame.timer.Stop();frame.Destroy()
        except Exception as exc:fail(exc)
    wx.CallLater(150,run)
