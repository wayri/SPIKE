"""Self-closing packaged GUI + spawned native-solver acceptance check."""
import json
from pathlib import Path
import time
import traceback


def run(library,destination):
    import wx
    from .desktop import Studio
    from .resources import resource_dir
    from .run_control import BatchRun
    from .document import RC_DECK
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    app=wx.App(False);app.SetAssertMode(wx.APP_ASSERT_EXCEPTION)
    frame=Studio(str(library));frame.Show();checks={};started=time.monotonic();job=None
    def finish(error=None):
        if job and job.state=='running':job.stop()
        destination.write_text(json.dumps({'passed':error is None,'checks':checks,'error':error,'platform':__import__('platform').platform(),'library':str(library)},indent=2)+'\n',encoding='utf-8')
        frame.timer.Stop();frame.Destroy()
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def poll():
        try:
            if time.monotonic()-started>60:raise TimeoutError('Packaged native worker exceeded 60 seconds')
            job.poll()
            if job.state=='running':wx.CallLater(100,poll);return
            if job.state!='completed':raise AssertionError('Spawned native transient failed: '+str(job.error))
            check(True,'spawned native transient completed')
            result=job.result
            check(result['status']=='completed','packaged solver reports completion')
            check(bool(result['data']),'packaged native waveform exists')
            finish()
        except Exception:finish(traceback.format_exc())
    def begin():
        nonlocal job
        try:
            check(library.is_file(),'native engine bundled')
            if __import__('os').name=='nt':
                from python.spikes.netlist import parse_netlist
                from python.spikes.native_runner import run_native_project
                for family in ('BSIMBULK','BSIMCMG'):
                    deck=f'.title BSIM package\nVd d 0 1\nVg g 0 PULSE(0 1 1n 1n 1n 10n 20n)\nM1 d g 0 0 mm\n.model mm {family}()\n.tran 100p 4n\n.end'
                    result=run_native_project(parse_netlist(deck,native_extensions=True),str(library),integration_method='backward_euler').to_dict()
                    check(result['status']=='completed',family+' packaged charge transient')
                    check(max(abs(v) for v in result['data']['element_current_a']['VG'])>1e-10,family+' gate displacement current')
            check((resource_dir('docs')/'COMPONENT_LIBRARY.md').is_file(),'current illustrated library guide bundled')
            check(len(frame.symbols)>1,'real schematic symbol library loaded')
            panel=frame.catalog_panel;panel.search.ChangeValue('family:resistor');panel.filter()
            check(len(panel.visible)==50,'catalog search works')
            frame.pin_browser(True);check(panel.GetParent() is frame.browser_side,'browser pins')
            frame.canvas.selected={frame.doc.data['components'][1]['id']};frame.pin_properties(True)
            check(frame.properties_editor is not None,'editable properties pin')
            frame.toggle_part_shortcuts(False);check(not frame.keymap.part_shortcuts,'part shortcuts disable')
            frame.set_theme('Light',save=False);frame.set_theme('Dark',save=False)
            from .model_preview import ModelPreview
            preview=ModelPreview(frame)
            preview.update_model(frame.doc.data['components'][2],{'esr_ohm':2,'esl_h':1e-6,'leakage_ohm':1e6},frame.doc.data['source'])
            preview.figure.savefig(destination.with_suffix('.preview.png'))
            check(len(preview.figure.axes)==2,'graphical model and analytical curve render')
            preview.Destroy()
            job=BatchRun(RC_DECK,str(library));wx.CallLater(100,poll)
        except Exception:finish(traceback.format_exc())
    wx.CallLater(400,begin);app.MainLoop()
    return 0 if destination.is_file() and json.loads(destination.read_text())['passed'] else 1
