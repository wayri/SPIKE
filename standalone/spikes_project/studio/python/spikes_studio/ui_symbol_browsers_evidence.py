# SPDX-License-Identifier: Apache-2.0
"""Actual symbol-and-text rendering in native palette and floating catalogs."""
from pathlib import Path
import wx
from .document import write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def selector():
        try:
            dialog=next(w for w in wx.GetTopLevelWindows() if isinstance(w,wx.Dialog) and w.GetTitle()=='Add component')
            check(dialog.part_choice.GetCount()>1,'component selection retains generic and manufacturer choices')
            check(all(dialog.part_choice.GetItemBitmap(i).IsOk() for i in range(dialog.part_choice.GetCount())),'every component-model choice has a symbol beside its text')
            dialog.Layout();wx.Yield();capture_window(dialog,directory/'component-model-symbols.png');dialog.EndModal(wx.ID_CANCEL)
        except Exception as error:
            frame._symbol_error=error
            for window in wx.GetTopLevelWindows():
                if isinstance(window,wx.Dialog):window.EndModal(wx.ID_CANCEL)
    try:
        frame.set_theme('Light',save=False);frame.Layout();wx.Yield()
        check(all(frame.designer_palette.GetItemImage(item)>=0 for item,key in frame.designer_palette.symbol_items),'palette groups and every clickable item have symbols')
        frame.parts.SetSelection(0);frame.canvas.Refresh();wx.Yield();capture_window(frame,directory/'palette-light.png')
        frame.show_browser();panel=frame.catalog_panel;panel.search.SetValue('family:resistor');panel.filter()
        window=frame.tool_windows.entries[11][0];window.Layout();wx.Yield()
        check(panel.list.GetItemCount()>0 and panel.list.OnGetItemImage(0)==panel.list.images.index('resistor'),'filtered resistor catalog rows have resistor symbols')
        capture_window(window,directory/'catalog-symbols.png')
        frame.execute_command('view.manufacturer_parts');window=frame.tool_windows.entries[16][0]
        panel=frame.manufacturer_panel;panel.search.SetValue('yageo');panel.refresh();panel.listing.SetSelection(0);panel.select();window.Layout();wx.Yield()
        check(all(panel.listing.OnGetItemImage(i)>=0 for i in range(len(panel.rows))),'manufacturer list symbols remain attached to filtered rows')
        capture_window(window,directory/'manufacturer-symbols.png')
        for tool_window,page,placeholder in frame.tool_windows.entries.values():tool_window.Hide()
        wx.CallLater(100,selector);frame.place_shortcut('part.resistor',explicit=True)
        if hasattr(frame,'_symbol_error'):raise frame._symbol_error
        frame.set_theme('Dark',save=False);frame.SetSize((960,720));frame.Layout();wx.Yield();capture_window(frame,directory/'palette-dark-narrow.png')
        check(frame.designer_palette.images.image_list.GetImageCount()==32,'symbol image sets stay bounded across theme changes')
        write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
