"""Editable sampled controller setup, explicit trust, compile and closed-loop run."""
from copy import deepcopy
import wx
from .controller_block import Controller,default_config,validate


class ControllerPanel(wx.Panel):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner;self.compiled=None
        box=wx.BoxSizer(wx.VERTICAL)
        self.note_text='Generic C/C++ sampled controller · AI/DI read node voltage; AO/DO drive existing voltage sources. Not firmware emulation. HDL tools are in Blocks / IDE; HDL pin co-simulation is not connected here.'
        self.note=wx.StaticText(self,label=self.note_text);self.note.Wrap(1050);box.Add(self.note,0,wx.ALL,7)
        from .controller_visual import ControllerVisual
        self.settings=ControllerVisual(self);box.Add(self.settings,1,wx.EXPAND|wx.ALL,5)
        from .desktop import text_editor
        self.code=text_editor(self,default_config()['source']);box.Add(self.code,2,wx.EXPAND|wx.ALL,5)
        self.trust=wx.CheckBox(self,label='I trust this code. It executes with my user permissions; process limits are NOT a filesystem/network sandbox.');box.Add(self.trust,0,wx.ALL,5)
        self.enabled=wx.CheckBox(self,label='Attach compiled controller to the next Continuous run (not batch F5)');box.Add(self.enabled,0,wx.ALL,5)
        row=wx.WrapSizer(wx.HORIZONTAL)
        from .controller_pin_dialog import edit_pins
        b=wx.Button(self,label='Block library…');b.SetToolTip('Load a parameterized sampled PWM/PI block or import your own C/C++ library. Does not execute code.');b.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(self.choose_block));row.Add(b,0,wx.ALL,3)
        b=wx.Button(self,label='Pin properties…');b.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(lambda:edit_pins(self)));row.Add(b,0,wx.ALL,3)
        for label,fn in [('Apply / save setup',self.apply),('Compile trusted C/C++',self.compile),('Run closed loop',self.run),('Pause / resume',owner.pause_run),('Stop',owner.stop_run),('Restore saved setup',self.reflect)]:
            b=wx.Button(self,label=label);b.Bind(wx.EVT_BUTTON,lambda e,f=fn:owner.guarded(f));row.Add(b,0,wx.ALL,3)
        box.Add(row,0,wx.EXPAND);self.log=wx.TextCtrl(self,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,140));box.Add(self.log,1,wx.EXPAND|wx.ALL,5);self.SetSizer(box);self.reflect()
        self.Bind(wx.EVT_WINDOW_DESTROY,self.destroyed)
        self.Bind(wx.EVT_SIZE,self.resized)

    def resized(self,event):
        self.note.SetLabel(self.note_text);self.note.Wrap(max(250,self.GetClientSize().width-20));event.Skip()

    def destroyed(self,event):
        if event.GetEventObject() is self and self.compiled:self.compiled.close();self.compiled=None
        event.Skip()

    def reflect(self):
        self.loaded_id=self.owner.doc.data['id'];self.enabled.SetValue(False)
        config=deepcopy(self.owner.doc.data.get('controller_setup') or default_config());self.code.SetText(config['source']);self.settings.load(config)
        if hasattr(self.owner,'code_bindings'):self.owner.configure_code_editors()

    def config(self):
        config=self.settings.config();config['source']=self.code.GetText();validate(config);return config

    def load_block(self,config):
        if self.owner.job_running:raise ValueError('Stop the active job before changing controller setup')
        validate(config)
        if self.compiled:self.compiled.close();self.compiled=None
        self.enabled.SetValue(False);self.trust.SetValue(False)
        self.settings.load(deepcopy(config));self.code.SetText(config['source'])
        self.owner.configure_code_editors()
        self.log.SetValue('Block loaded into editor only. Review pin bindings; Apply / save setup, then explicitly trust and compile. No code was executed.')

    def choose_block(self):
        if self.owner.job_running:raise ValueError('Stop the active job before changing controller setup')
        from .compiled_ic_dialog import CompiledICDialog
        with CompiledICDialog(self) as dialog:
            if dialog.ShowModal()==wx.ID_OK:self.load_block(dialog.result)

    def apply(self):
        if self.owner.job_running:raise ValueError('Stop the active job before changing controller setup')
        config=self.config();self.owner.doc.commit(lambda d:d.__setitem__('controller_setup',config));self.owner.update_title()
        self.owner.refresh_document();self.owner.configure_code_editors()

    def compile(self):
        if not self.trust.GetValue():raise ValueError('Read and check the trusted-code consent first')
        self.apply();config=self.config()
        def done(controller):
            if self.compiled:self.compiled.close()
            self.compiled=controller;self.log.SetValue(controller.build_log+'\nCompiled digest: '+controller.manifest.executable_sha256+'\nPin order: inputs '+', '.join(p['name'] for p in controller.inputs)+'; outputs '+', '.join(p['name'] for p in controller.outputs)+'\nState[] is explicit and persists; C static/global variables reset each subprocess tick. First feedback tick follows the first accepted plant point.')
        self.owner.background(lambda:Controller(config,trusted=True),done,'Compiling trusted controller in a bounded subprocess')

    def attached(self):
        if not self.enabled.GetValue():return None
        if self.compiled is None or self.compiled.config!=self.config():raise ValueError('Compile the current controller setup before enabling coupling')
        if not self.trust.GetValue():raise ValueError('Trusted-code consent was cleared')
        return self.compiled

    def run(self):
        self.enabled.SetValue(True);self.owner.start_interactive()
