# SPDX-License-Identifier: Apache-2.0
"""Native analysis form selection, labeled edits and raw round-trip checks."""
from pathlib import Path
import wx
from .directive_manager import DirectiveEditor
from .document import write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    try:
        frame.set_theme('Light',save=False)
        ident=next(v['id'] for v in frame.doc.data['directives'] if v['text'].startswith('.tran'))
        with DirectiveEditor(frame,ident) as dialog:
            def edit():
                try:
                    check(dialog.template.GetStringSelection()=='Transient','existing .tran selects Transient rather than Parameter')
                    check(len(dialog.form_controls)==5 and dialog.form_controls[1].GetValue()=='5m','transient fields load actual saved values')
                    dialog.form_controls[1].SetValue('8m');dialog.Layout();wx.Yield();capture_window(dialog,directory/'transient-form.png')
                    dialog.SetSize((620,500));dialog.Layout();wx.Yield();capture_window(dialog,directory/'transient-form-narrow.png')
                    dialog.SetSize((760,630))
                    dialog.template.SetStringSelection('AC sweep');dialog.type_changed()
                    check(len(dialog.form_controls)==4 and dialog.text.GetValue()=='.ac dec 20 1 1meg','type dropdown replaces fields with an AC sweep form')
                    dialog.Layout();wx.Yield();capture_window(dialog,directory/'ac-form.png')
                    dialog.text.SetValue('.tran 10u 8m uic')
                    check(dialog.template.GetStringSelection()=='Transient' and dialog.form_controls[1].GetValue()=='8m','raw command input synchronizes the selected type and form')
                    dialog.apply()
                    if hasattr(dialog,'last_error'):raise AssertionError(dialog.last_error)
                except Exception as error:
                    frame._form_error=error
                    if dialog.IsModal():dialog.EndModal(wx.ID_CANCEL)
            wx.CallLater(100,edit);dialog.ShowModal()
        if hasattr(frame,'_form_error'):raise frame._form_error
        check('.tran 10u 8m uic' in frame.doc.data['source'],'form edits commit real simulation directive parameters')
        write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
