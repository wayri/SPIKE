"""Measured electrical limit markers, not a physical damage/failure simulator."""
import numpy as np


def evaluate_limits(snapshot,result):
    data=result.get('data',{});alerts={}
    def channel(table,name):
        value=data.get(table,{}).get(name)
        if value is None:raise ValueError('channel unavailable')
        return np.asarray(value,dtype=float)
    for part in snapshot.get('components',[]):
        findings=[]
        for key,limit in part.get('limits',{}).items():
            try:
                if key=='voltage_v':value=float(np.max(np.abs(channel('node_voltage_v',part['nodes'][0])-channel('node_voltage_v',part['nodes'][1]))))
                elif key=='current_a':value=float(np.max(np.abs(channel('element_current_a',part['ref']))))
                elif key=='power_w':value=max(0.,float(np.max(channel('element_power_w',part['ref']))))
                else:findings.append({'limit':key,'severity':'unavailable','message':'No qualified solver binding for this limit'});continue
                if not np.isfinite(value):raise ValueError('nonfinite capture')
                ratio=value/limit
                if ratio>=.8:findings.append({'limit':key,'measured':value,'declared':limit,'ratio':ratio,'severity':'exceeded' if ratio>=1 else 'warning','message':'Captured-window electrical threshold; not a prediction of physical damage'})
            except (ValueError,KeyError,IndexError):findings.append({'limit':key,'severity':'unavailable','message':'Measured channel unavailable'})
        if findings:alerts[part['id']]={'ref':part['ref'],'findings':findings}
    from .thermal_report import report
    for row in report(snapshot,result)['parts']:
        if row['status'] in ('warning','exceeded'):
            entry=alerts.setdefault(row['id'],{'ref':row['ref'],'findings':[]})
            entry['findings'].append({'limit':'junction_temperature_c','severity':row['status'],
                'measured':row['peak_junction_c'],'declared':row['max_junction_c'],'headroom_c':row['headroom_c'],
                'message':row['basis']+'; thermal margin screening, not a lifetime prediction'})
    return alerts
