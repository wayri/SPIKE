"""Thermal margin screening; never a lifetime or physical-damage prediction."""
import math
import numpy as np


def number(value,label):
    if isinstance(value,bool):raise ValueError(label+' must be finite numeric data')
    value=float(value)
    if not math.isfinite(value):raise ValueError(label+' must be finite')
    return value


def report(snapshot,result):
    rows=[];data=result.get('data',{})
    for part in snapshot.get('components',[]):
        row={'ref':part['ref'],'id':part['id'],'status':'unavailable'}
        setup=part.get('parameters',{}).get('thermal_assessment',{})
        try:
            if not isinstance(setup,dict):raise ValueError('thermal_assessment must be an object')
            if 'max_junction_c' not in setup:raise ValueError('Maximum junction rating not supplied')
            limit=number(setup['max_junction_c'],'Maximum junction temperature')
            margin=number(setup.get('warning_margin_c',20),'Warning margin')
            if limit<=-273.15 or margin<0:raise ValueError('Invalid temperature rating or warning margin')
            trace=data.get('element_temperature_k',{}).get(part['ref'])
            if trace is not None:
                values=np.asarray(trace,dtype=float)-273.15;basis='recorded element_temperature_k channel'
            elif 'supplied_temperature_c' in setup:
                values=np.asarray([number(setup['supplied_temperature_c'],'Supplied junction temperature')]);basis='user-supplied junction temperature; not solver-derived'
            elif all(k in setup for k in ('theta_ja_k_w','steady_power_w','ambient_c')):
                theta=number(setup['theta_ja_k_w'],'Effective junction-to-ambient resistance');power=number(setup['steady_power_w'],'Steady dissipated power');ambient=number(setup['ambient_c'],'Ambient')
                if theta<=0 or power<0 or ambient<=-273.15:raise ValueError('Invalid steady-state thermal assumptions')
                if not setup.get('conditions_evidence'):raise ValueError('Provide conditions_evidence for effective thermal resistance and steady power')
                values=np.asarray([ambient+theta*power]);basis='steady-state estimate from explicitly supplied effective theta_JA and dissipated power'
            else:raise ValueError('No temperature channel or explicit temperature/steady-state inputs')
            if values.ndim>1 or values.size==0 or not np.isfinite(values).all() or np.any(values<=-273.15):raise ValueError('Invalid temperature channel')
            peak=float(np.max(values));headroom=limit-peak
            row.update(status='exceeded' if headroom<=0 else 'warning' if headroom<=margin else 'within_declared_margin',
                       peak_junction_c=peak,max_junction_c=limit,headroom_c=headroom,warning_margin_c=margin,basis=basis,
                       assumptions=setup,recommendation='Review cooling, load and rating evidence; check temperature-dependent specifications. No service-life conclusion follows from this margin alone.')
        except (ValueError,TypeError,OverflowError) as exc:row['reason']=str(exc)
        rows.append(row)
    return {'contract':'spikes/thermal-margin-report/v1','parts':rows,
            'counts':{s:sum(r['status']==s for r in rows) for s in ('exceeded','warning','within_declared_margin','unavailable')},
            'provenance':result.get('provenance',{}),
            'limitations':['Captured window only; discarded continuous history is not evaluated.',
                'Declared part temperature metadata is not assumed to be solved junction temperature.',
                'Electrical terminal power is not automatically treated as heat, especially in energy-storing or multiport devices.',
                'Effective theta_JA depends on board, airflow and enclosure; no thermal geometry is solved here.',
                'No lifetime, aging, thermal cycling or degradation prediction without a calibrated device-specific model.']}
