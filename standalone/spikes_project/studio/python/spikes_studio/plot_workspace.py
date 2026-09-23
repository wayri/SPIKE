"""Run-qualified cursor math and schematic instruments on actual recorded data."""
import ast
import math
import numpy as np
from .signal_math import SignalMath,Quantity,VOLT,AMP,SECOND,ExpressionError

FORMATS=('Engineering','Rectangular complex','Polar / degrees')


def run_label(result,index):
    parameters=result.get('provenance',{}).get('step_parameters',{})
    return f'Run {index+1}'+(' · '+', '.join(f'{k}={v:g}' for k,v in parameters.items()) if parameters else '')


def sample(engine,expression,time):
    if not math.isfinite(time) or not engine.time[0]<=time<=engine.time[-1]:
        raise ValueError('Cursor is outside this run’s recorded interval')
    q=engine.evaluate(expression);values=np.broadcast_to(q.values,engine.time.shape)
    return Quantity(np.interp(time,engine.time,values),q.unit)


def cursor_math(engines,left,right,expression='b-a'):
    """Each cursor owns its run, expression and coordinate. Never clamp silently."""
    a=sample(engines[left['run']],left['expression'],left['time'])
    b=sample(engines[right['run']],right['expression'],right['time'])
    dt=Quantity(right['time']-left['time'],SECOND)
    answer=engines[left['run']].evaluate(expression,variables={'a':a,'b':b,'dt':dt})
    if np.ndim(answer.values):raise ValueError('Cursor math must produce a scalar; use a, b and dt')
    return answer


class OperatingPointMath(SignalMath):
    def __init__(self,result):
        self.time=np.array([]);self.signals={}
        for table,prefix,unit in (('node_voltage_v','v',VOLT),('element_current_a','i',AMP),('element_power_w','p',VOLT.mul(AMP))):
            for name,value in result['data'].get(table,{}).items():
                if np.ndim(value):raise ValueError('Not an operating-point scalar capture')
                self.signals[f'{prefix}({name})'.lower()]=Quantity(float(value),unit)

    def _visit(self,node,variables):
        if isinstance(node,ast.Name) and node.id=='t':raise ExpressionError('Operating points have no time axis')
        return super()._visit(node,variables)

    def _call(self,name,args):
        if name in ('integral','derivative','mean','rms'):raise ExpressionError('No time reductions on an operating point')
        return super()._call(name,args)


def format_value(q,style='Engineering'):
    value=complex(q.values)
    if not np.isfinite(value):raise ValueError('Non-finite instrument value')
    unit=str(q.unit)
    if style=='Polar / degrees':return f'{abs(value):.6g} ∠ {np.degrees(np.angle(value)):.4g}° {unit}'
    if style=='Rectangular complex' or value.imag:return f'{value.real:.6g} {value.imag:+.6g}j {unit}'
    from matplotlib.ticker import EngFormatter
    return EngFormatter(unit=unit,places=4)(value.real)


def validate_instruments(items,components):
    if not isinstance(items,list) or len(items)>64:raise ValueError('At most 64 schematic instruments')
    ids=set()
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or item['id'] in ids:raise ValueError('Instrument IDs must be unique')
        ids.add(item['id'])
        # Detached anchors are retained through circuit edits; rendered unavailable.
        if not isinstance(item.get('anchor'),str):raise ValueError('Instrument anchor is required')
        if item.get('kind') not in ('Readout','Mini plot') or item.get('source') not in ('Selected run','AC frequency'):raise ValueError('Unknown instrument type / source')
        if item.get('format') not in FORMATS:raise ValueError('Unknown readout format')
        if not isinstance(item.get('expression'),str) or not 0<len(item['expression'])<=8192:raise ValueError('Instrument expression is required')
        for key in ('x','y','frequency_hz'):
            if type(item.get(key)) not in (float,int) or not math.isfinite(item[key]) or abs(item[key])>1e12:raise ValueError('Invalid instrument position / frequency')
        if item['frequency_hz']<=0:raise ValueError('AC readout requires positive frequency')


def instrument_data(owner,item):
    expression=item['expression']
    if item['source']=='AC frequency':
        from .frequency import FrequencyMath
        result=owner.frequency.result
        if result is None:raise ValueError('Run AC first')
        cached=getattr(owner.frequency,'_instrument_engine',None)
        if cached is None or cached[0] is not result:
            cached=(result,FrequencyMath.from_frequency(result));owner.frequency._instrument_engine=cached
        engine=cached[1]
        q=sample(engine,expression,item['frequency_hz'])
        label=f"AC {item['frequency_hz']:g} Hz · complex excitation"
    else:
        if owner.result is None:raise ValueError('Run circuit first')
        label=run_label(owner.result,getattr(owner,'selected_run',0))
        if owner.math:
            engine=owner.math
            time=owner.cursors[-1] if owner.cursors else engine.time[-1]
            q=sample(engine,expression,time);label+=f' · t={time:.6g}s'
        else:
            engine=None;q=OperatingPointMath(owner.result).evaluate(expression);label+=' · DC OP'
    if np.ndim(q.values):raise ValueError('Readout must be scalar')
    stale=owner.result_source and owner.result_source.get('document_source',owner.result_source['source'])!=owner.doc.data['source']
    if item['source']=='AC frequency':
        from python.spikes.netlist import parse_netlist
        stale=result.get('provenance',{}).get('circuit_source_sha256')!=parse_netlist(owner.doc.data['source'],native_extensions=True,transient_capture='rolling').source_sha256
    if stale:label+=' · STALE circuit'
    if item['kind']=='Mini plot':
        if engine is None:raise ValueError('OP has no waveform')
        answer=engine.evaluate(expression);values=np.broadcast_to(answer.values,engine.time.shape)
        if np.iscomplexobj(values):raise ValueError('Mini plot: use real(), abs() or angle()')
        return label,format_value(q,item['format']),(engine.time,values)
    return label,format_value(q,item['format']),None
