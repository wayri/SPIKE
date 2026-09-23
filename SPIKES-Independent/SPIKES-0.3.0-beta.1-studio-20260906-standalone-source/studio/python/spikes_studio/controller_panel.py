"""Editable sampled controller setup, explicit trust, compile and closed-loop run."""
from copy import deepcopy
import json
import wx
from .controller_block import Controller,default_config,validate


class ControllerPanel(wx.Panel):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner;self.compiled=None
        box=wx.BoxSizer(wx.VERTICAL)
        note=wx.StaticText(self,label='Generic C/C++ sampled controller · AI/DI read node voltage; AO/DO drive existing voltage sources. Not Arduino/ESP32/RP2040/STM32 firmware emulation. Verilog synthesis/simulation remains in Blocks / IDE; Verilog pin co-simulation is not connected here.');note.Wrap(1050);box.Add(note,0,wx.ALL,7)
        self.settings=wx.TextCtrl(self,style=wx.TE_MULTILINE,size=(-1,190));box.Add(self.settings,1,wx.EXPAND|wx.ALL,5)
        from .desktop import text_editor
        self.code=text_editor(self,default_config()['source']);box.Add(self.code,2,wx.EXPAND|wx.ALL,5)
        self.trust=wx.CheckBox(self,label='I trust this code. It executes with my user permissions; process limits are NOT a filesystem/network sandbox.');box.Add(self.trust,0,wx.ALL,5)
        self.enabled=wx.CheckBox(self,label='Attach compiled controller to the next Continuous run (not batch F5)');box.Add(self.enabled,0,wx.ALL,5)
        row=wx.WrapSizer(wx.HORIZONTAL)
        for label,fn in [('Apply / save setup',self.apply),('Compile trusted C/C++',self.compile),('Run closed loop',self.run),('Pause / resume',owner.pause_run),('Stop',owner.stop_run),('Restore saved setup',self.reflect)]:
            b=wx.Button(self,label=label);b.Bind(wx.EVT_BUTTON,lambda e,f=fn:owner.guarded(f));row.Add(b,0,wx.ALL,3)
        box.Add(row,0,wx.EXPAND);self.log=wx.TextCtrl(self,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,140));box.Add(self.log,1,wx.EXPAND|wx.ALL,5);self.SetSizer(box);self.reflect()
        self.Bind(wx.EVT_WINDOW_DESTROY,self.destroyed)

    def destroyed(self,event):
        if event.GetEventObject() is self and self.compiled:self.compiled.close();self.compiled=None
        event.Skip()

    def reflect(self):
        self.loaded_id=self.owner.doc.data['id'];self.enabled.SetValue(False)
        config=deepcopy(self.owner.doc.data.get('controller_setup') or default_config());self.code.SetText(config.pop('source'));self.settings.SetValue(json.dumps(config,indent=2))

    def config(self):
        config=json.loads(self.settings.GetValue());config['source']=self.code.GetText();validate(config);return config

    def apply(self):
        if self.owner.job_running:raise ValueError('Stop the active job before changing controller setup')
        config=self.config();self.owner.doc.commit(lambda d:d.__setitem__('controller_setup',config));self.owner.update_title()

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
