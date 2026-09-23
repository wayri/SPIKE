"""Bounded sine-injection FRA using independent native transient experiments."""
import math,re
from dataclasses import replace
import numpy as np
from .netlist import parse_netlist
from .contracts import ProbeDescriptor
from .native_runner import run_native_project


def fit_fundamental(time,signal,frequency):
    t=np.asarray(time,dtype=float);y=np.asarray(signal,dtype=float)
    if len(t)<16 or t.shape!=y.shape or not np.isfinite(t).all() or not np.isfinite(y).all() or np.any(np.diff(t)<=0):raise ValueError('FRA requires at least 16 finite ordered samples')
    phase=2*np.pi*frequency*(t-t[0])
    # Time weights prevent adaptive-step clusters from dominating the fit.
    weights=np.empty(len(t));weights[0]=(t[1]-t[0])/2;weights[-1]=(t[-1]-t[-2])/2;weights[1:-1]=(t[2:]-t[:-2])/2
    design=np.column_stack((np.sin(phase),np.cos(phase),np.ones(len(t))))
    coefficients,_,rank,_=np.linalg.lstsq(design*np.sqrt(weights[:,None]),y*np.sqrt(weights),rcond=None)
    if rank<3:raise ValueError('Singular FRA fit')
    # Return phase relative to absolute virtual time.
    phasor=complex(coefficients[0],coefficients[1])*np.exp(-1j*2*np.pi*frequency*t[0])
    residual=float(np.sqrt(np.average((y-design@coefficients)**2,weights=weights)))
    return phasor,residual


def analyze(source,library,excitation,output,frequencies,*,amplitude=.01,settle_cycles=8,measure_cycles=4,max_step_s=1e-5):
    if not math.isfinite(amplitude) or amplitude<=0 or not math.isfinite(max_step_s) or max_step_s<=0:raise ValueError('Positive finite amplitude/timestep required')
    if type(settle_cycles) is not int or type(measure_cycles) is not int or not 1<=settle_cycles<=100 or not 2<=measure_cycles<=100:raise ValueError('Invalid settling/acquisition cycles')
    frequencies=list(frequencies)
    if not 1<=len(frequencies)<=100 or any(not math.isfinite(f) or f<=0 for f in frequencies):raise ValueError('Specify 1..100 positive finite frequencies')
    project=parse_netlist(source,native_extensions=True,transient_capture='rolling')
    if project.steps:raise ValueError('Select one .step before transient FRA')
    element=next((e for e in project.elements if e.name==excitation.upper()),None)
    if element is None or element.kind!='voltage_source' or element.waveform or ':' in element.name:raise ValueError('Injection requires a top-level independent DC voltage source')
    probe=ProbeDescriptor.parse(output)
    if probe.quantity!='node_voltage':raise ValueError('Transient FRA currently measures voltage probes only')
    from .native_runner import _nodes
    if any(n not in _nodes(project) for n in probe.targets):raise ValueError('FRA probe references a missing node')
    pattern=re.compile(r'(?im)^\s*'+re.escape(element.name)+r'\s+[^\r\n]+$')
    if len(pattern.findall(source))!=1:raise ValueError('Injection source must have exactly one top-level source record')
    rows=[]
    for frequency in frequencies:
        stop=(settle_cycles+measure_cycles)/frequency;dt=min(max_step_s,1/(64*frequency))
        count=math.ceil(stop/dt)
        if count>100000:raise ValueError('Transient FRA exceeds 100000 samples per frequency; narrow the experiment')
        times=np.linspace(0,stop,count+1)
        points=' '.join(f'{t:.17g} {element.value+amplitude*math.sin(2*math.pi*frequency*t):.17g}' for t in times)
        deck=pattern.sub(lambda m:f'{element.name} {element.positive_node} {element.negative_node} PWL({points})',source)
        deck=re.sub(r'(?im)^\s*\.(?:tran|op|ac|dc)\b[^\r\n]*','',deck)
        deck=re.sub(r'(?im)^\s*\.end\s*$',f'.tran {dt:.17g} {stop:.17g}\n.end',deck)
        p=parse_netlist(deck,native_extensions=True)
        result=run_native_project(p,library,integration_method='backward_euler').to_dict()
        if result['status']!='completed':raise ValueError('Native FRA experiment failed')
        data=result['data'];t=np.asarray(data['time_s']);mask=t>=settle_cycles/frequency
        def voltage(node):return np.zeros(len(t)) if node=='0' else np.asarray(data['node_voltage_v'][node])
        y=voltage(probe.targets[0])-(voltage(probe.targets[1]) if len(probe.targets)>1 else 0)
        phasor,residual=fit_fundamental(t[mask],y[mask],frequency);gain=phasor/amplitude
        rows.append(dict(frequency_hz=frequency,real=gain.real,imaginary=gain.imag,gain_db=20*math.log10(max(abs(gain),1e-300)),phase_deg=math.degrees(math.atan2(gain.imag,gain.real)),nonfundamental_residual_rms_v=residual,effective_source_sha256=p.source_sha256))
    return dict(contract='spikes/transient-fra/v1',status='completed',rows=rows,source=excitation,output=output,amplitude_v=amplitude,
                method='native backward Euler sine injection; weighted fundamental fit',
                limitations=['Independent cold-start experiment per frequency; settling is user-assumed, not proven',
                             'Transfer response, not automatically loop gain or a stability certificate',
                             'No compiled controller attachment or periodic operating-point solver'])
