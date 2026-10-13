# SPDX-License-Identifier: Apache-2.0
"""Atomic trace-expression edits and an original-sample waveform picker."""
from copy import deepcopy
import numpy as np
from .fuzzy_search import ranked


def evaluated_trace(engine,expression):
    if not isinstance(expression,str) or not expression.strip() or len(expression)>8192:raise ValueError('Enter a signal or expression (at most 8192 characters)')
    expression=expression.strip();answer=engine.evaluate(expression)
    values=np.broadcast_to(answer.values,engine.time.shape)
    if np.iscomplexobj(values):raise ValueError('Choose real(), imag(), abs() or angle() for complex results')
    if not np.isfinite(values).all():raise ValueError('Expression contains nonfinite values')
    return expression,values,str(answer.unit)


def replace_trace(owner,old,expression):
    """Validate all affected run/cursor bindings before changing any UI state."""
    if owner.math is None:raise ValueError('Acquire or load a run first')
    index=next((i for i,t in enumerate(owner.traces) if t[0]==old),None)
    if index is None:raise ValueError('This waveform is no longer plotted')
    trace=evaluated_trace(owner.math,expression);new=trace[0]
    if any(t[0].casefold()==new.casefold() and i!=index for i,t in enumerate(owner.traces)):raise ValueError('That expression is already plotted')
    bindings=deepcopy(owner.cursor_bindings)
    from .plot_workspace import sample
    overlay=getattr(owner,'overlay_runs',None)
    if overlay is not None and overlay.GetValue():
        for run,engine in enumerate(owner.run_engines):
            if engine is None or run==owner.selected_run or owner.visible_runs is not None and run not in owner.visible_runs:continue
            if evaluated_trace(engine,new)[2]!=trace[2]:raise ValueError(f'Run {run+1} has incompatible expression units')
    for i in range(len(owner.cursors)):
        descriptor=owner.cursor_descriptor(i)
        if descriptor['expression']==old:
            sample(owner.run_engines[descriptor['run']],new,descriptor['time'])
            while len(bindings)<=i:bindings.append(dict(run=descriptor['run'],expression=descriptor['expression']))
            bindings[i]=dict(run=descriptor['run'],expression=new)
    traces=list(owner.traces);traces[index]=trace
    layout=deepcopy(owner.doc.data['plot_layout'])
    if old in layout['panes']:layout['panes'][new]=layout['panes'].pop(old)
    from .plot_panes import groups
    if layout['mode']=='custom' and trace[2]!=owner.traces[index][2]:
        other=groups([t for i,t in enumerate(traces) if i!=index],layout)
        target=next((pane for pane,items,_ in other if items[0][2]==trace[2]),None)
        if target is None:target=next((p for p in range(1,17) if p not in {v[0] for v in other}),None)
        if target is None:raise ValueError('No free compatible pane; combine traces first')
        layout['panes'][new]=target
    groups(traces,layout)
    expressions=[new if e==old else e for e in owner.doc.data['expressions']]
    if new not in expressions:expressions.append(new)
    owner.doc.commit(lambda data:data.update(expressions=expressions,plot_layout=layout))
    owner.traces=traces;owner.cursor_bindings=bindings
    owner.hidden_traces={new if name==old else new+name[len(old):] if name.startswith(old+' · run ') else name for name in owner.hidden_traces}
    owner.expression.SetValue(new)
    owner.draw_plot();owner.update_title()


def show(owner,expression=None):
    import wx
    from .flat_controls import ActionButton
    from .signal_math import FUNCTION_HELP
    from .themes import apply_window
    if owner.math is None:raise ValueError('Run or load recorded data first')
    with wx.Dialog(owner,title='Edit waveform' if expression else 'Add waveform',size=(760,590),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
        dialog.SetMinSize((600,470));outer=wx.BoxSizer(wx.VERTICAL);dialog.SetSizer(outer)
        message='Select a recorded signal or write a dimension-checked expression. Editing also rebinds this trace’s cursors; source samples remain unchanged.'
        heading=wx.StaticText(dialog,label=message);heading.Wrap(700);outer.Add(heading,0,wx.EXPAND|wx.ALL,12)
        field=wx.TextCtrl(dialog,value=expression or owner.expression.GetValue(),style=wx.TE_PROCESS_ENTER);field.SetName('Waveform expression');outer.Add(field,0,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        body=wx.BoxSizer(wx.HORIZONTAL);outer.Add(body,1,wx.EXPAND|wx.ALL,12)
        left=wx.BoxSizer(wx.VERTICAL);body.Add(left,1,wx.EXPAND|wx.RIGHT,10)
        search=wx.SearchCtrl(dialog);search.SetDescriptiveText('Filter voltage, current, power or net');left.Add(search,0,wx.EXPAND|wx.BOTTOM,6)
        signals=wx.ListBox(dialog);signals.SetName('Recorded signals and nets');left.Add(signals,1,wx.EXPAND)
        available=sorted(owner.math.signals)
        def filter_signals(event=None):signals.Set(ranked(available,search.GetValue()))
        search.Bind(wx.EVT_TEXT,filter_signals);filter_signals()
        def choose(event):
            if signals.GetSelection()>=0:field.SetValue(signals.GetStringSelection());field.SetFocus();field.SetInsertionPointEnd()
        signals.Bind(wx.EVT_LISTBOX,choose)
        help_text=wx.TextCtrl(dialog,value=FUNCTION_HELP,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(360,-1));body.Add(help_text,1,wx.EXPAND)
        tools=wx.WrapSizer(wx.HORIZONTAL);outer.Add(tools,0,wx.EXPAND|wx.LEFT|wx.RIGHT,10)
        for label in ('+','-','*','/','**','(',')'):
            button=ActionButton(dialog,label=label);button.SetToolTip('Insert '+label+' at the expression caret')
            button.Bind(wx.EVT_BUTTON,lambda event,value=label:(field.WriteText(value),field.SetFocus()));tools.Add(button,0,wx.ALL,2)
        functions=wx.Choice(dialog,choices=['Function…','abs','sqrt','sin','cos','tan','log','exp','derivative','integral','rms','mean']);functions.SetSelection(0);tools.Add(functions,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
        def wrap(event):
            if functions.GetSelection()>0:
                field.SetValue(functions.GetStringSelection()+'('+field.GetValue()+')');field.SetFocus();functions.SetSelection(0)
        functions.Bind(wx.EVT_CHOICE,wrap)
        error=wx.StaticText(dialog,label='Examples: v(in)-v(out) · v(out)*i(R1) · derivative(v(out)) · sin(v(out)/V)')
        outer.Add(error,0,wx.EXPAND|wx.ALL,12)
        actions=wx.BoxSizer(wx.HORIZONTAL);outer.Add(actions,0,wx.ALIGN_RIGHT|wx.ALL,10)
        def validate(event=None):
            try:
                name,values,unit=evaluated_trace(owner.math,field.GetValue())
                error.SetLabel(f'{len(values):,} original samples · [{unit}] · min {np.min(values):.6g}, max {np.max(values):.6g}')
                return True
            except Exception as exc:error.SetLabel(str(exc));error.Wrap(680);dialog.Layout();return False
        def apply(event=None):
            try:
                if expression is None:
                    evaluated_trace(owner.math,field.GetValue())
                    owner.add_trace(field.GetValue().strip())
                else:replace_trace(owner,expression,field.GetValue())
                dialog.EndModal(wx.ID_OK)
            except Exception as exc:error.SetLabel(str(exc));error.Wrap(680);dialog.Layout()
        for label,handler in [('Validate',validate),('Cancel',lambda e:dialog.EndModal(wx.ID_CANCEL)),('Apply waveform',apply)]:
            button=ActionButton(dialog,label=label);button.Bind(wx.EVT_BUTTON,handler);actions.Add(button,0,wx.LEFT,6)
        field.Bind(wx.EVT_TEXT_ENTER,apply);apply_window(dialog,owner.palette)
        field.SetFocus();dialog.ShowModal()
