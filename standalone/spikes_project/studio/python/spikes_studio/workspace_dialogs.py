"""Editable, run-qualified cursors and persistent schematic instrument manager."""
import uuid
import wx
from .plot_workspace import FORMATS,cursor_math,format_value
from .themes import apply_window as apply_widgets


def cursors_dialog(owner):
    if not owner.math:raise ValueError('Run a transient circuit first')
    with wx.Dialog(owner,title='Linked cursors · explicit run / trace / time',size=(850,580),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
        box=wx.BoxSizer(wx.VERTICAL);listing=wx.ListBox(dlg);box.Add(listing,1,wx.EXPAND|wx.ALL,6)
        row=wx.BoxSizer(wx.HORIZONTAL);run=wx.Choice(dlg,choices=owner.run_choice.GetStrings());run.SetSelection(owner.selected_run)
        expression=wx.TextCtrl(dlg,value=owner.expression.GetValue());time=wx.TextCtrl(dlg,value=str(owner.math.time[-1]))
        for label,control in [('Run',run),('Trace',expression),('Time [s]',time)]:
            row.Add(wx.StaticText(dlg,label=label),0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4);row.Add(control,1,wx.ALL,4)
        box.Add(row,0,wx.EXPAND)
        pairs=wx.BoxSizer(wx.HORIZONTAL);left=wx.Choice(dlg);right=wx.Choice(dlg);formula=wx.TextCtrl(dlg,value='b-a')
        for label,control in [('a',left),('b',right),('Math',formula)]:
            pairs.Add(wx.StaticText(dlg,label=label),0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4);pairs.Add(control,1,wx.ALL,4)
        output=wx.TextCtrl(dlg,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,90))
        def refresh(redraw=True):
            labels=[owner.cursor_label(i) for i in range(len(owner.cursors))]
            listing.Set(labels);left.Set(labels);right.Set(labels)
            if labels:left.SetSelection(0);right.SetSelection(min(1,len(labels)-1))
            if redraw:owner.draw_plot(preserve_view=True);owner.canvas.Refresh()
        def select(event):
            i=listing.GetSelection()
            if i<0:return
            c=owner.cursor_descriptor(i);run.SetSelection(c['run']);expression.SetValue(c['expression']);time.SetValue(str(c['time']))
        listing.Bind(wx.EVT_LISTBOX,select)
        def put(update=False):
            index=listing.GetSelection() if update else None
            if update and index<0:raise ValueError('Select a cursor to update')
            owner.put_cursor(float(time.GetValue()),run.GetSelection(),expression.GetValue(),index);refresh()
        def remove():
            i=listing.GetSelection()
            if i<0:raise ValueError('Select a cursor')
            owner.cursors.pop(i);owner.cursor_bindings.pop(i);refresh()
        def compute():
            if left.GetSelection()<0 or right.GetSelection()<0:raise ValueError('Choose two cursors')
            a=owner.cursor_descriptor(left.GetSelection());b=owner.cursor_descriptor(right.GetSelection())
            q=cursor_math(owner.run_engines,a,b,formula.GetValue())
            output.SetValue(f"a: {owner.cursor_label(left.GetSelection())}\nb: {owner.cursor_label(right.GetSelection())}\nΔt = {b['time']-a['time']:.9g} s\n{formula.GetValue()} = {format_value(q)}")
        buttons=wx.BoxSizer(wx.HORIZONTAL)
        for label,fn in [('Add cursor',put),('Update selected',lambda:put(True)),('Delete selected',remove),('Clear all',lambda:(owner.cursors.clear(),owner.cursor_bindings.clear(),refresh()))]:
            b=wx.Button(dlg,label=label);buttons.Add(b,0,wx.ALL,4);b.Bind(wx.EVT_BUTTON,lambda e,f=fn:owner.guarded(f))
        box.Add(buttons);box.Add(pairs,0,wx.EXPAND)
        b=wx.Button(dlg,label='Evaluate cursor math');b.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(compute));box.Add(b,0,wx.ALL,4)
        box.Add(wx.StaticText(dlg,label='a, b retain physical units; dt is seconds. Examples: b-a, b/a, (b-a)/dt, atan2(b,a). Up to 16 linked cursors.'))
        box.Add(output,0,wx.EXPAND|wx.ALL,6);box.Add(dlg.CreateButtonSizer(wx.CLOSE),0,wx.ALIGN_RIGHT|wx.ALL,6)
        dlg.SetSizer(box);refresh(False);apply_widgets(dlg,owner.palette);dlg.ShowModal()


def instruments_dialog(owner):
    with wx.Dialog(owner,title='Schematic instruments · saved with circuit',size=(850,660),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
        box=wx.BoxSizer(wx.VERTICAL);listing=wx.ListBox(dlg);box.Add(listing,1,wx.EXPAND|wx.ALL,6)
        parts=owner.doc.data['components'];fields={};grid=wx.FlexGridSizer(cols=2,hgap=8,vgap=5);grid.AddGrowableCol(1)
        specs=[('anchor','Attached component',[p['ref'] for p in parts]),('expression','Probe / expression','V(out)'),('kind','Display',['Readout','Mini plot']),
               ('source','Data source',['Selected run','AC frequency']),('format','Notation',list(FORMATS)),('frequency_hz','AC readout frequency [Hz]','1000'),('x','Canvas X','120'),('y','Canvas Y','360')]
        for key,label,value in specs:
            grid.Add(wx.StaticText(dlg,label=label),0,wx.ALIGN_CENTER_VERTICAL)
            c=wx.Choice(dlg,choices=value) if isinstance(value,list) else wx.TextCtrl(dlg,value=value)
            if isinstance(value,list) and value:c.SetSelection(0)
            fields[key]=c;grid.Add(c,1,wx.EXPAND)
        if owner.canvas.selected:
            index=next((i for i,p in enumerate(parts) if p['id'] in owner.canvas.selected),0);fields['anchor'].SetSelection(index)
            fields['expression'].SetValue(f"V({parts[index]['nodes'][0]})")
        box.Add(grid,0,wx.EXPAND|wx.ALL,8)
        def refresh():listing.Set([v['kind']+' · '+v['expression']+' · '+v['source'] for v in owner.doc.data['instruments']]);owner.canvas.Refresh()
        def select(event):
            index=listing.GetSelection()
            if index<0:return
            item=owner.doc.data['instruments'][index]
            for key,c in fields.items():
                if key=='anchor':c.SetSelection(next((i for i,p in enumerate(parts) if p['id']==item[key]),wx.NOT_FOUND))
                elif isinstance(c,wx.Choice):c.SetStringSelection(item[key])
                else:c.SetValue(str(item[key]))
        listing.Bind(wx.EVT_LISTBOX,select)
        def put(update=False):
            index=listing.GetSelection()
            if update and index<0:raise ValueError('Select an instrument to update')
            if fields['anchor'].GetSelection()<0:raise ValueError('Select an attached component')
            item={key:c.GetStringSelection() if isinstance(c,wx.Choice) else c.GetValue() for key,c in fields.items()}
            item['anchor']=parts[fields['anchor'].GetSelection()]['id']
            for key in ('x','y','frequency_hz'):item[key]=float(item[key])
            item['id']=owner.doc.data['instruments'][index]['id'] if update else uuid.uuid4().hex
            def mutate(d):
                if update:d['instruments'][index]=item
                else:d['instruments'].append(item)
            owner.doc.commit(mutate);owner.refresh_document();refresh()
        def remove():
            index=listing.GetSelection()
            if index<0:raise ValueError('Select an instrument')
            owner.doc.commit(lambda d:d['instruments'].pop(index));owner.refresh_document();refresh()
        row=wx.BoxSizer(wx.HORIZONTAL)
        for label,fn in [('Add instrument',put),('Update selected',lambda:put(True)),('Delete selected',remove)]:
            b=wx.Button(dlg,label=label);b.Bind(wx.EVT_BUTTON,lambda e,f=fn:owner.guarded(f));row.Add(b,0,wx.ALL,4)
        box.Add(row);note=wx.StaticText(dlg,label='Probe examples: V(out), V(out,ref), I(R1), P(R1). AC complex power: V(out)*conj(I(R1)) (excitation convention, no RMS inference).\nReadouts use selected run’s last sample or newest linked cursor time; unavailable data is shown explicitly. Drag instrument cards on canvas.\nFrequency plots need real(), abs() or angle(). Thermal / failure estimates are not fabricated.');note.Wrap(810);box.Add(note,0,wx.ALL,8)
        box.Add(dlg.CreateButtonSizer(wx.CLOSE),0,wx.ALIGN_RIGHT|wx.ALL,6);dlg.SetSizer(box);refresh();apply_widgets(dlg,owner.palette);dlg.ShowModal()
