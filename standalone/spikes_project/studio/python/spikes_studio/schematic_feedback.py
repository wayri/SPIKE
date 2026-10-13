# SPDX-License-Identifier: Apache-2.0
"""Captured-limit glyphs and opt-in simulation-only symbol interaction."""
import math
from .dashboard import reconcile_control


def badge(findings):
    active=[f for f in findings if f.get('severity') in ('warning','exceeded')]
    if not active:return None
    keys={f.get('limit') for f in active}
    return dict(severity='exceeded' if any(f['severity']=='exceeded' for f in active) else 'warning',
                temperature='junction_temperature_c' in keys,
                text=' '.join(tag for tag,key in [('V!', 'voltage_v'),('I!', 'current_a'),('P!', 'power_w')]
                              if key in keys))


def send_symbol_control(owner, part):
    from .run_control import InteractiveRun
    session=owner.active_run
    if not isinstance(session,InteractiveRun):raise ValueError('Start Continuous simulation to interact')
    config=part.get('parameters',{}).get('canvas_control')
    if not config:raise ValueError('Configure this symbol for direct click control first')
    name=config.get('source',part['ref']);values=[float(config[k]) for k in ('low','high')]
    if not all(math.isfinite(v) for v in values) or values[0]>=values[1]:raise ValueError('Invalid finite click-control range')
    if name not in session.controls:raise ValueError('Only exposed independent DC sources support direct control')
    snapshot=session.snapshot() or {};events=snapshot.get('provenance',{}).get('control_events',[])
    pending=owner.symbol_controls.get(part['id'])
    if pending and pending.get('session')==id(session) and not reconcile_control(pending,events):
        raise ValueError('Previous click is still queued; wait for native-step acknowledgement')
    current=session.controls[name]
    for event in events:
        if event.get('source')==name:current=event['value']
    value=values[1] if abs(current-values[0])<=abs(current-values[1]) else values[0]
    session.set_source(name,value)
    owner.symbol_controls[part['id']]=dict(source=name,value=value,session=id(session),event_index=len(events),
        event_cursor=None if not events else tuple(events[-1].get(k) for k in ('time_s','source','value','origin')))
    owner.SetStatusText(f'{name}: {value:g} queued for the next native step; not yet acknowledged')


def configure_control(owner, part):
    import wx
    if owner.job_running:raise ValueError('Stop simulation before editing controls')
    old=part.get('parameters',{}).get('canvas_control',dict(low=0.,high=1.))
    source=old.get('source',part['ref'] if part['kind'] in ('voltage_source','current_source') else '')
    with wx.TextEntryDialog(owner,'Controlling independent DC source, low, high (SI), comma-separated.\nThe symbol commands that source; it does not create a hidden physical connection.\nStart Continuous and enable Interact before clicking.',
                            'Direct symbol control',f"{source},{old['low']},{old['high']}") as dialog:
        if dialog.ShowModal()!=wx.ID_OK:return
        fields=dialog.GetValue().split(',')
        if len(fields)!=3:raise ValueError('Enter source, low, high')
        source=fields[0].strip().upper();values=[float(v.strip()) for v in fields[1:]]
        sources={p['ref'] for p in owner.doc.data['components'] if p['kind'] in ('voltage_source','current_source')}
        if source not in sources or not all(math.isfinite(v) for v in values) or values[0]>=values[1]:raise ValueError('Choose a circuit source and two ordered finite values; continuous admission checks DC eligibility')
        owner.doc.commit(lambda d:next(p for p in d['components'] if p['id']==part['id'])['parameters'].__setitem__('canvas_control',dict(source=source,low=values[0],high=values[1])))
        owner.refresh_document()
