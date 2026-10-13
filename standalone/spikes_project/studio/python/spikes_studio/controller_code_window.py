# SPDX-License-Identifier: Apache-2.0
"""Compact controller-bound code window reusing the same draft editor."""
import wx
from .flat_controls import ActionButton
from .themes import apply_window


class ControllerCodeWindow(wx.Frame):
    def __init__(self,owner):
        super().__init__(owner,title='SPIKES · Sampled controller code',size=(760,520))
        self.owner=owner;self.panel=owner.controller_panel;self.editor=self.panel.code
        from .app_identity import set_window_icons
        set_window_icons(self);self.SetMinSize((550,380))
        self.original_sizer=self.editor.GetContainingSizer()
        self.slot=next(i for i,item in enumerate(self.original_sizer.GetChildren()) if item.GetWindow()==self.editor)
        self.original_sizer.Detach(self.editor)
        self.placeholder=wx.StaticText(self.panel,label='Code is in the controller-bound floating editor; close hides it, Return editor restores it.')
        self.original_sizer.Insert(self.slot,self.placeholder,0,wx.EXPAND|wx.ALL,8)
        self.editor.Reparent(self);box=wx.BoxSizer(wx.VERTICAL)
        row=wx.WrapSizer(wx.HORIZONTAL)
        for label,action in [('Pins…',self.pins),('Save setup',self.panel.apply),('Compile C/C++',self.panel.compile),('Return editor',self.restore)]:
            button=ActionButton(self,label=label);button.Bind(wx.EVT_BUTTON,lambda event,fn=action:owner.guarded(fn));row.Add(button,0,wx.ALL,3)
            if label=='Compile C/C++':self.compile_button=button
        box.Add(row,0,wx.EXPAND)
        note=wx.StaticText(self,label='Same sampled-controller code and pins · C/C++ only; HDL co-simulation is not connected.\nCompile requires explicit trust. Code runs with your permissions, not a hostile-code sandbox.')
        note.Wrap(700);box.Add(note,0,wx.ALL,8)
        self.trust=wx.CheckBox(self,label='I trust this controller source');self.trust.SetValue(self.panel.trust.GetValue())
        def approval(event):
            self.panel.trust.SetValue(event.IsChecked());self.compile_button.Enable(event.IsChecked())
        self.trust.Bind(wx.EVT_CHECKBOX,approval);box.Add(self.trust,0,wx.LEFT|wx.BOTTOM,8)
        self.compile_button.Enable(self.trust.GetValue());self.compile_button.SetToolTip('Compiles only explicitly trusted source; never compiled or executed by opening the editor')
        box.Add(self.editor,1,wx.EXPAND|wx.ALL,6);self.SetSizer(box);self.editor.Show();self.panel.Layout();apply_window(self,owner.palette)
        self.Bind(wx.EVT_CLOSE,self.close);self.Bind(wx.EVT_MOVE,lambda event:(owner.canvas.Refresh(),event.Skip()))
        def resize(event):note.Wrap(max(300,self.GetClientSize().width-24));self.Layout();event.Skip()
        self.Bind(wx.EVT_SIZE,resize)
    def pins(self):
        from .controller_pin_dialog import edit_pins
        edit_pins(self.panel)
    def close(self,event):
        if event.CanVeto():event.Veto();self.Hide();self.owner.canvas.Refresh()
        else:event.Skip()
    def restore(self):
        self.GetSizer().Detach(self.editor);self.editor.Reparent(self.panel);self.original_sizer.Detach(self.placeholder);self.placeholder.Destroy()
        self.original_sizer.Insert(self.slot,self.editor,2,wx.EXPAND|wx.ALL,5);self.editor.Show();self.panel.Layout()
        self.owner.controller_code_window=None;self.owner.canvas.Refresh();self.Destroy()


def show(owner):
    window=getattr(owner,'controller_code_window',None)
    if not window:
        window=ControllerCodeWindow(owner);owner.controller_code_window=window
        if owner.canvas.controller_hit:
            rect=owner.canvas.controller_hit;at=owner.canvas.ClientToScreen(wx.Point(rect.GetRight()+25,rect.y))
            screen=wx.Display(wx.Display.GetFromWindow(owner)).GetClientArea()
            at=wx.Point(max(screen.x,min(at.x,screen.GetRight()-window.GetSize().width-12)),max(screen.y,min(at.y,screen.GetBottom()-window.GetSize().height-12)))
            window.SetPosition(at)
    window.trust.SetValue(owner.controller_panel.trust.GetValue());window.compile_button.Enable(window.trust.GetValue())
    window.Show();window.Raise();window.Layout();owner.canvas.Refresh()
    return window
