"""Real-window theme, pane, analytics and attached-subcircuit workflow regression."""
from copy import deepcopy
from pathlib import Path
import time
import wx
from .document import write_json,Document
from .themes import PALETTES
from .ui_evidence import capture_window


def verify_upgrade(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);checks={};deadline=time.monotonic()+60
    library=Path(__file__).resolve().parents[2]/'library'
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    def fail(exc):
        frame.validation_failure=True
        if frame.active_run:frame.active_run.stop()
        write_json(destination/'error.json',{'error':str(exc),'checks':checks});frame.timer.Stop();frame.Destroy()
    def begin():
        try:frame.run();wx.CallLater(150,await_rc)
        except Exception as exc:fail(exc)
    def await_rc():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Upgrade GUI run timed out')
            if frame.job_running:wx.CallLater(150,await_rc);return
            check(frame.math is not None,'actual native RC capture is available')
            frame.traces.clear()
            for expr in ('V(out)','V(in)','I(R1)'):frame.add_trace(expr)
            layout={'mode':'custom','panes':{'V(out)':1,'V(in)':2,'I(R1)':3},'heights':{'1':2,'2':1,'3':1}}
            frame.doc.commit(lambda d:d.__setitem__('plot_layout',layout));frame.draw_plot()
            check(len(frame.axes)==3,'same-unit traces can be stacked into separate panes')
            frame.axes[0].set_xlim(.001,.004)
            check(frame.axes[1].get_xlim()==frame.axes[0].get_xlim(),'stacked panes share zoomed time axis')
            for name in PALETTES:
                frame.set_theme(name,save=False);frame.book.SetSelection(1)
                check(frame.palette['fg']==frame.inspector.GetForegroundColour().GetAsString(wx.C2S_HTML_SYNTAX).lower(),'widget foreground adapts to '+name)
                capture_window(frame,destination/('theme-'+name.replace(' ','-').lower()+'.png'))
            frame.set_theme('Dark',save=False);frame.book.SetSelection(0);frame.fit();capture_window(frame,destination/'canvas-dark.png')
            from .desktop import Properties
            frame.canvas.selected={frame.doc.data['components'][1]['id']};dialog=Properties(frame)
            def inspect_dialog():
                try:
                    check(dialog.fields['value'].GetForegroundColour().GetAsString(wx.C2S_HTML_SYNTAX).lower()==frame.palette['fg'],'new property dialog inherits current theme')
                    capture_window(dialog,destination/'properties-dark.png');dialog.EndModal(wx.ID_CANCEL)
                except Exception as exc:dialog.EndModal(wx.ID_CANCEL);fail(exc)
            wx.CallLater(200,inspect_dialog);dialog.ShowModal();dialog.Destroy()
            if getattr(frame,'validation_failure',False):return
            frame.book.SetSelection(10);frame.analytics.stats()
            check(frame.analytics.last_report['samples']==len(frame.math.time),'analytics statistics use recorded samples')
            frame.analytics.resample.SetValue(True);frame.analytics.fft(False);capture_window(frame,destination/'analytics-spectrum-dark.png')
            choose=frame.choose_path
            try:
                frame.choose_path=lambda *a,**k:library/'ripple-analytics.json';frame.analytics.load()
            finally:frame.choose_path=choose
            frame.analytics.run_extension()
            check(frame.analytics.last_report['measurements']['Peak-to-peak']['value']>0,'loaded expression extension evaluates recorded signal')
            power=frame.power_tree;frame.book.SetSelection(9);power.add('source');source_id=power.selected
            power.add('converter');converter_id=power.selected
            power.fields['name'].SetValue('Interconnect loss');power.fields['voltage_v'].SetValue('12');power.fields['efficiency'].SetValue('1')
            try:
                frame.choose_path=lambda *a,**k:library/'series-loss.cir';power.attach()
            finally:frame.choose_path=choose
            power.apply();power.add('load');power.fields['current_a'].SetValue('0.1');power.fields['max_current_a'].SetValue('0.2');power.apply()
            check(len(frame.doc.data['power_tree']['stages'])==3,'power-tree controls create connected supply/stage/load')
            check(frame.doc.data['power_tree']['stages'][1]['model']['sha256']!='','actual subcircuit file snapshot has source hash')
            capture_window(frame,destination/'power-tree-dark.png')
            frame.path=destination/'power-project.spksch';frame.save_document()
            check(Document.load(frame.path).data['power_tree']==frame.doc.data['power_tree'],'power tree with model survives project round trip')
            original_box=wx.MessageBox
            try:
                wx.MessageBox=lambda *a,**k:wx.YES  # only this isolated test frame's replace confirmation
                power.compile()
            finally:wx.MessageBox=original_box
            frame.run();frame._upgrade_converter_id=converter_id;wx.CallLater(150,await_power)
        except Exception as exc:fail(exc)
    def await_power():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Compiled power-tree simulation timed out')
            if frame.job_running:wx.CallLater(150,await_power);return
            check(frame.result['status']=='completed','compiled real subcircuit runs in native C++ engine')
            voltage=frame.result['data']['node_voltage_v']['rail_'+frame._upgrade_converter_id]
            check(abs(voltage-11.8)<1e-9,'native stage response follows 2-ohm model and 0.1-A load')
            write_json(destination/'power-native-result.json',frame.result);write_json(destination/'checks.json',checks)
            frame.timer.Stop();frame.Destroy()
        except Exception as exc:fail(exc)
    begin()
