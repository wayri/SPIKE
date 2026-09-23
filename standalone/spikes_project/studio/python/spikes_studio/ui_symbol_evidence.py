"""Real event-driven visual designer regression; can run in a self-closing wx app."""
import json
from pathlib import Path
import wx
from .symbol_designer import SymbolDesignerPanel
from .symbol_design import checked


def verify(frame,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);results=[]
    def check(name,condition):
        results.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    try:
        panel=getattr(frame,'symbol_designer',None)
        if panel is None:
            panel=SymbolDesignerPanel(frame,frame);sizer=wx.BoxSizer(wx.VERTICAL);sizer.Add(panel,1,wx.EXPAND);frame.SetSizer(sizer)
        else:
            for i in range(frame.book.GetPageCount()):
                if frame.book.GetPage(i)==panel:frame.book.SetSelection(i);break
        frame.Layout();wx.Yield();canvas=panel.canvas
        def event(kind,point,held=False):
            e=wx.MouseEvent(kind);e.SetPosition(wx.Point(*point));e.SetLeftDown(held);canvas.GetEventHandler().ProcessEvent(e)
        start=canvas.point(panel.symbol['terminals'][0]['at']);end=canvas.point([10,-60])
        event(wx.wxEVT_LEFT_DOWN,start,True);event(wx.wxEVT_MOTION,end,True);event(wx.wxEVT_LEFT_UP,end)
        check('real drag relocates pin to top edge',panel.symbol['terminals'][0]['direction']=='north')
        check('drag snapped to grid',panel.symbol['terminals'][0]['at']==[10,-60])
        panel.add_pin();check('add named numbered pin',len(panel.symbol['terminals'])==3)
        panel.fields['pin_name'].SetValue('ENABLE');panel.apply_pin();check('edit pin label',panel.symbol['terminals'][2]['name']=='ENABLE')
        panel.undo();check('undo pin edit',panel.symbol['terminals'][2]['name']!='ENABLE')
        path=folder/'custom-ic.json';path.write_text(json.dumps(panel.symbol,indent=2),encoding='utf-8');check('saved geometry reload validates',checked(json.loads(path.read_text()))==panel.symbol)
        canvas.Refresh();canvas.Update();wx.Yield()
        bitmap=wx.Bitmap(frame.GetSize());memory=wx.MemoryDC(bitmap);memory.Blit(0,0,*frame.GetSize(),wx.WindowDC(frame),0,0);memory.SelectObject(wx.NullBitmap);bitmap.SaveFile(str(folder/'visual-symbol-designer.png'),wx.BITMAP_TYPE_PNG)
    except Exception as error:
        results.append({'error':repr(error),'passed':False})
    finally:
        (folder/'checks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        if hasattr(frame,'timer'):frame.timer.Stop()
        frame.Destroy()
