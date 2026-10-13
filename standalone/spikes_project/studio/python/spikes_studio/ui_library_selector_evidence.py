# SPDX-License-Identifier: Apache-2.0
"""Native-window evidence for manufacturer search, sorting and placement."""
from pathlib import Path
import wx
from .document import write_json, Document
from .ui_evidence import capture_window


def verify(frame, destination):
    directory = Path(destination); directory.mkdir(parents=True, exist_ok=True)
    checks = {}
    def check(condition, label):
        if not condition: raise AssertionError(label)
        checks[label] = True
    def edit():
        try:
            dialog = next(w for w in wx.GetTopLevelWindows() if isinstance(w, wx.Dialog) and w.GetTitle() == 'Add component')
            dialog.part_search.SetValue('yageo'); dialog.filter_library()
            check(len(dialog.library_rows) > 1, 'component selector finds matching manufacturer parts')
            dialog.part_choice.SetSelection(1); dialog.select_library()
            check(not dialog.parameter_fields['r'].IsEnabled(), 'sourced nominal value is protected from accidental edits')
            frame._selected_library_mpn = dialog.library_record['mpn']
            dialog.Layout(); wx.Yield(); capture_window(dialog, directory/'component-selector.png')
            dialog.accept()
        except Exception as error:
            frame._library_test_error = error
            for window in wx.GetTopLevelWindows():
                if isinstance(window, wx.Dialog): window.EndModal(wx.ID_CANCEL)
    try:
        frame.set_theme('Light', save=False); frame.SetSize((1320, 880))
        panel = frame.manufacturer_panel
        frame.book.SetSelection(frame.book.FindPage(panel))
        panel.search.SetValue('yageo'); panel.refresh()
        check(len(panel.rows) == 5 and all(r['manufacturer'] == 'Yageo' for r in panel.rows), 'manufacturer text search returns exact matching catalog records')
        panel.listing.SetSelection(0); panel.select()
        identity = panel.record['id']
        event = wx.ListEvent(wx.wxEVT_LIST_COL_CLICK); event.SetColumn(1)
        panel.listing._sort(event); panel.select()
        check(panel.record['id'] == identity, 'column sorting preserves selected record identity')
        panel.search.SetValue(''); panel.refresh()
        check(panel.record['id'] == identity, 'clearing search preserves matching selection')
        check(panel.listing.GetColumnCount() == 5, 'five headed columns are available')
        frame.Layout(); wx.Yield(); capture_window(frame, directory/'library-wide.png')
        frame.SetSize((960, 720)); frame.Layout(); wx.Yield(); capture_window(frame, directory/'library-narrow.png')
        panel.search.SetValue('SN74HC02N'); panel.refresh()
        check(len(panel.rows) == 1, 'standard HC package is searchable by exact MPN')
        panel.listing.SetSelection(0); panel.select()
        check(len(panel.record['pins']) == 14 and panel.record['pins'][0]['name'] == '1Y', 'standard NOR has full distinct package pins')
        check(panel.record['model']['readiness'] == 'vendor_model_required', 'functional logic does not claim circuit qualification')
        frame.Layout(); wx.Yield(); capture_window(frame, directory/'standard-logic-package.png')
        panel.search.SetValue('AD620ANZ'); panel.refresh()
        check(len(panel.rows) == 1 and panel.rows[0]['category'] == 'instrumentation_amplifier', 'standard instrumentation amplifier is searchable')
        frame.book.SetSelection(0)
        wx.CallLater(100, edit); frame.place_shortcut('part.resistor', explicit=True)
        if hasattr(frame, '_library_test_error'): raise frame._library_test_error
        record, mapping, count = frame.pending_library_placement
        check(record['_manufacturer_record']['mpn'] == frame._selected_library_mpn, 'placement retains selected exact MPN')
        event = wx.MouseEvent(wx.wxEVT_LEFT_DOWN); event.SetPosition(frame.canvas.point(620, 500))
        frame.canvas.GetEventHandler().ProcessEvent(event)
        part = next(p for p in frame.doc.data['components'] if p['ref'].startswith('RNEW'))
        check(part['parameters']['manufacturer_part']['mpn'] == frame._selected_library_mpn, 'inserted component retains manufacturer provenance')
        frame.doc.save(directory/'library-part.spksch')
        reopened = Document.load(directory/'library-part.spksch')
        restored = next(p for p in reopened.data['components'] if p['id'] == part['id'])
        check(restored['parameters']['manufacturer_part'] == part['parameters']['manufacturer_part'], 'manufacturer metadata survives save and reopen')
        write_json(directory/'verification.json', dict(ok=True, checks=checks))
    except Exception as error:
        write_json(directory/'verification.json', dict(ok=False, checks=checks, error=str(error)))
    frame.timer.Stop(); frame.autosave_timer.Stop(); frame.Destroy()
