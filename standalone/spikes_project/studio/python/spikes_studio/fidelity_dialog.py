"""Scoped model policy editor and transparent preflight preview."""
from copy import deepcopy
import wx
from .model_fidelity import TIERS, descriptor, inherited, resolve


def show(owner, ref=None):
    policy = deepcopy(owner.doc.data['model_policy'])
    parts = owner.doc.data['components']
    scopes = ['schematic'] + sorted({':'.join(p['ref'].upper().split(':')[:i])
        for p in parts for i in range(1, len(p['ref'].split(':')))}) + [p['ref'].upper() for p in parts]
    with wx.Dialog(owner, title='Model fidelity and inheritance', size=(850,760), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
        dialog.SetMinSize((600,560))
        box = wx.BoxSizer(wx.VERTICAL)
        choice = wx.Choice(dialog, choices=scopes); choice.SetSelection(scopes.index(ref.upper()) if ref and ref.upper() in scopes else 0)
        box.Add(choice,0,wx.EXPAND|wx.ALL,8)
        reason = wx.StaticText(dialog); box.Add(reason,0,wx.ALL,8)
        radios = []
        row = wx.WrapSizer(wx.HORIZONTAL)
        labels=dict(source='Source-defined',ideal='Ideal',simplified='Simplified',
                    behavioral='Behavioral',physics='Physics-based',validated='Validated (evidence required)')
        for i, tier in enumerate(TIERS):
            control = wx.RadioButton(dialog,label=labels[tier],style=wx.RB_GROUP if i==0 else 0)
            radios.append(control); row.Add(control,0,wx.ALL,5)
        box.Add(row)
        enforce = wx.CheckBox(dialog,label='Enforce on children'); box.Add(enforce,0,wx.ALL,8)
        box.Add(wx.StaticText(dialog,label='Required implicit parasitics (comma separated; unavailable bindings block the run):'),0,wx.ALL,8)
        parasitics = wx.TextCtrl(dialog); box.Add(parasitics,0,wx.EXPAND|wx.ALL,8)
        parameter_row=wx.FlexGridSizer(cols=2,hgap=8,vgap=6);parameter_row.AddGrowableCol(1);parameter_fields={}
        for key,label in (('esr_ohm','ESR [ohm]'),('esl_h','ESL [H]'),('leakage_ohm','Leakage [ohm]')):
            parameter_row.Add(wx.StaticText(dialog,label=label),0,wx.ALIGN_CENTER_VERTICAL)
            control=wx.TextCtrl(dialog);parameter_fields[key]=control;parameter_row.Add(control,1,wx.EXPAND)
        box.Add(parameter_row,0,wx.EXPAND|wx.ALL,8)
        from .model_preview import ModelPreview
        graph=ModelPreview(dialog);box.Add(graph,1,wx.EXPAND|wx.ALL,5)
        preview = wx.TextCtrl(dialog,style=wx.TE_MULTILINE|wx.TE_READONLY); box.Add(preview,1,wx.EXPAND|wx.ALL,8)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        apply = wx.Button(dialog,label='Apply scope'); clear = wx.Button(dialog,label='Remove override / inherit')
        buttons.Add(apply);buttons.Add(clear);buttons.Add(wx.Button(dialog,wx.ID_CLOSE));box.Add(buttons,0,wx.ALL,8)
        dialog.SetSizer(box)
        def target():
            scope=choice.GetStringSelection()
            section='components' if any(p['ref'].upper()==scope for p in parts) else 'subsheets'
            return scope, section
        def refresh(event=None):
            scope, section=target()
            entry=policy['schematic'] if scope=='schematic' else policy[section].get(scope,inherited(policy,scope)[0])
            affected=parts if scope=='schematic' else [p for p in parts if p['ref'].upper()==scope or p['ref'].upper().startswith(scope+':')]
            # Remove this scope while determining whether a parent enforces it.
            parent=deepcopy(policy)
            if scope!='schematic': parent[section].pop(scope,None)
            lock=inherited(parent,scope)[2] if scope!='schematic' else None
            available=set.intersection(*(set(descriptor(p)['available_tiers']) for p in affected)) if affected else {'source'}
            for tier,control in zip(TIERS,radios):
                control.SetValue(tier==entry['tier']);control.Enable(not lock and tier in available)
                control.SetToolTip('Supported by current source model' if tier in available else 'Unavailable: no executable qualified binding')
            reason.SetLabel(f'Locked by enforced parent: {lock}' if lock else 'Source preserves the explicit deck model. No silent approximation.')
            enforce.SetValue(entry['enforce']);enforce.Enable(not lock)
            parasitics.SetValue(', '.join(entry.get('required_parasitics',[])));parasitics.Enable(not lock)
            effective=inherited(policy,scope)[0] if scope!='schematic' else entry
            single=affected[0] if len(affected)==1 else None
            for key,control in parameter_fields.items():
                control.SetValue(str(effective.get('parasitic_values',{}).get(key,'')))
                control.Enable(not lock and single is not None and single['kind']=='capacitor' and ':' not in single['ref'])
            graph.update_model(single,effective.get('parasitic_values',{}),owner.doc.data['source'])
            apply.Enable(not lock);clear.Enable(not lock and scope!='schematic')
            doc=deepcopy(owner.doc.data);doc['model_policy']=policy
            report=resolve(doc)
            lines=[f"Analysis: {report['analysis']}", 'Resolved component models', '']
            for item in report['components']:
                lines.extend([f"{item['ref']} — {labels[item['selection']['tier']]}",
                              f"  Defined by: {item['origin']}",
                              f"  Pins: {', '.join(item['model']['pins'])}",
                              f"  Qualification: {item['model']['qualification']}"])
                for key,value in item['model']['parasitics'].items():
                    lines.append(f"  {dict(esr_ohm='ESR [ohm]',esl_h='ESL [H]',leakage_ohm='Leakage [ohm]').get(key,key)}: {value:.8g}")
                if item['locked_by']:lines.append(f"  Enforced by: {item['locked_by']}")
            if report['errors']:lines.extend(['','Cannot run:',*report['errors']])
            if report['warnings']:lines.extend(['','Model assumptions:',*report['warnings']])
            preview.SetValue('\n'.join(lines))
        def save(event):
            scope, section=target()
            entry=dict(tier=next(t for t,c in zip(TIERS,radios) if c.GetValue()),enforce=enforce.GetValue(),
                       required_parasitics=[p.strip() for p in parasitics.GetValue().split(',') if p.strip()])
            from python.spikes.netlist import parse_spice_number
            entry['parasitic_values']={key:parse_spice_number(control.GetValue(),'scalar') for key,control in parameter_fields.items() if control.IsEnabled() and control.GetValue().strip()}
            if scope=='schematic':policy['schematic']=entry
            else:policy[section][scope]=entry
            owner.doc.commit(lambda data:data.__setitem__('model_policy',deepcopy(policy)))
            owner.refresh_document();refresh()
        def remove(event):
            scope,section=target();policy[section].pop(scope,None)
            owner.doc.commit(lambda data:data.__setitem__('model_policy',deepcopy(policy)))
            owner.refresh_document();refresh()
        choice.Bind(wx.EVT_CHOICE,refresh);apply.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(lambda:save(e)))
        clear.Bind(wx.EVT_BUTTON,remove);dialog.Bind(wx.EVT_BUTTON,lambda e:dialog.EndModal(wx.ID_CLOSE),id=wx.ID_CLOSE)
        refresh();dialog.ShowModal()
