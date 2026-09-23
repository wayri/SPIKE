"""Validated complex-frequency data, explicit RF conversions and scientific views."""
import ast
import gzip
import json
import re
from pathlib import Path
import numpy as np
from .signal_math import SignalMath,Quantity,ExpressionError,ONE,VOLT,AMP,SECOND

CONTRACT='spikes/studio-frequency/v1'
VIEWS=('Bode dB / phase','Bode magnitude / phase','Real / imaginary','Nyquist','Polar','Nichols',
       'Group delay','Smith impedance','Smith admittance','Return loss','VSWR','Pole-zero')


def parse_hz(text):
    from python.spikes.netlist import parse_spice_number
    text=text.strip()
    match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([kMGTmu]?)Hz',text)
    if match:return float(match[1])*{'':1,'k':1e3,'M':1e6,'G':1e9,'T':1e12,'m':1e-3,'u':1e-6}[match[2]]
    return parse_spice_number(text,'scalar')


class FrequencyMath(SignalMath):
    def _visit(self,node,variables):
        if isinstance(node,ast.Name):
            if node.id=='f':return Quantity(self.time,SECOND.pow(-1))
            if node.id=='t':raise ExpressionError('Frequency data uses f [Hz], not t')
        return super()._visit(node,variables)

    def _call(self,name,args):
        if name in ('integral','derivative','mean','rms'):raise ExpressionError('Time-domain reductions are unavailable on frequency data')
        return super()._call(name,args)

    @classmethod
    def from_frequency(cls,result):
        data=result['data'];signals={}
        for key,prefix,unit in (('node_voltage_v','v',VOLT),('element_current_a','i',AMP)):
            for name,series in data.get(key,{}).items():signals[f'{prefix}({name})']=Quantity(complex_values(series),unit)
        if not signals:raise ValueError('No complex voltage/current data')
        return cls(data['frequency_hz'],signals)


def complex_values(series):
    real=np.asarray(series['real'],dtype=float);imag=np.asarray(series['imaginary'],dtype=float)
    if real.ndim!=1 or real.shape!=imag.shape or not np.isfinite(real).all() or not np.isfinite(imag).all():raise ValueError('Invalid complex arrays')
    return real+1j*imag


def validate_result(result):
    if result.get('contract')!=CONTRACT or result.get('status')!='completed':raise ValueError('Not a completed SPIKES frequency result')
    engine=FrequencyMath.from_frequency(result)
    if np.any(engine.time<=0) or len(engine.time)>10000:raise ValueError('Require 2..10000 positive increasing frequencies')
    pz=result.get('pole_zero')
    if pz is not None:
        if pz.get('contract')!='spikes/pole-zero-result/v1' or pz.get('status')!='completed':raise ValueError('Invalid pole-zero report')
        for key in ('poles_rad_s','zeros_rad_s'):complex_values(pz['data'][key])
    setup=result.get('plot_setup')
    if setup is not None:
        if setup['view'] not in VIEWS or setup['rf_kind'] not in ('Impedance','Admittance','Reflection coefficient'):raise ValueError('Invalid saved plot view')
        if not isinstance(setup['expression'],str) or len(setup['expression'])>8192:raise ValueError('Invalid saved expression')
        if not isinstance(setup['mirror'],bool) or not np.isfinite(setup['z0']) or setup['z0']<=0:raise ValueError('Invalid saved plot options')
    return engine


def analyze(source,settings):
    from python.spikes.netlist import parse_netlist
    from python.spikes.analyses import AcSweep,AcExcitation,run_ac_analysis
    from python.spikes.advanced_analyses import run_linear_pole_zero
    from python.spikes.contracts import ProbeDescriptor
    points=settings['points']
    if isinstance(points,bool) or not isinstance(points,int) or not 2<=points<=10000:raise ValueError('Frequency sweep requires 2..10000 points')
    if settings['stop_hz']<=settings['start_hz']:raise ValueError('Stop frequency must exceed start')
    project=parse_netlist(source,native_extensions=True,transient_capture='rolling')
    if project.steps:raise ValueError('Frequency workspace does not execute .step sweeps')
    # Bound dense descriptor work BEFORE assembly, including control-only nodes.
    nodes={n for e in project.elements for n in (e.positive_node,e.negative_node,e.control_positive_node,e.control_negative_node) if n not in (None,'0')}
    branches=sum(e.kind in ('inductor','voltage_source','vcvs','ccvs') for e in project.elements)
    if len(nodes)+branches>256:raise ValueError('Interactive frequency workspace is limited to 256 linear MNA unknowns')
    excitation=AcExcitation(settings['source'])
    result=run_ac_analysis(project,AcSweep(settings['start_hz'],settings['stop_hz'],points,settings['scale']),excitation)
    if result['status']!='completed':raise ValueError('AC solve failed: '+str(result.get('issues',result)))
    result['contract']=CONTRACT;result['settings']=dict(settings)
    selected=next(e for e in project.elements if e.name.upper()==excitation.source)
    result['settings']['input_voltage']=f'V({selected.positive_node},{selected.negative_node})'
    result['settings']['input_current']=f'-I({selected.name})'
    result['provenance'].update(backend='Python/SciPy linear MNA; not owned C++ AC',
        circuit_source_sha256=project.source_sha256,
        ignored_deck_settings='Time-domain analysis, .measure and source DC levels do not define this explicit single-source AC sweep')
    if settings.get('pole_zero',True):
        probe=ProbeDescriptor.parse(settings['output'])
        if probe.quantity!='node_voltage' or any(node not in nodes|{'0'} for node in probe.targets):raise ValueError('Pole-zero output must reference existing voltage nodes')
        result['pole_zero']=run_linear_pole_zero(project,excitation,probe)
    validate_result(result);return result


def reflection(values,unit,kind,z0):
    if not np.isfinite(z0) or z0<=0:raise ValueError('Reference impedance must be positive real ohms')
    ohm=VOLT.mul(AMP.pow(-1))
    if kind=='Reflection coefficient':
        if unit!=ONE:raise ValueError('Reflection coefficient must be dimensionless (not an arbitrary voltage/impedance)')
        return np.asarray(values,dtype=complex)
    expected=ohm if kind=='Impedance' else ohm.pow(-1)
    if unit!=expected:raise ValueError(f'{kind} requires units {expected}; use a voltage/current ratio')
    normalized=values/z0 if kind=='Impedance' else values*z0
    if np.any(np.abs(normalized+1)<1e-14):raise ValueError('Reflection coefficient is singular at normalized impedance/admittance −1')
    return (normalized-1)/(normalized+1) if kind=='Impedance' else (1-normalized)/(1+normalized)


def series(engine,expression):
    answer=engine.evaluate(expression);values=np.asarray(np.broadcast_to(answer.values,engine.time.shape),dtype=complex)
    return values,answer.unit


def db(values):return 20*np.log10(np.maximum(np.abs(values),1e-15))


def smith_grid(ax,admittance=False):
    angle=np.linspace(0,2*np.pi,361);ax.plot(np.cos(angle),np.sin(angle),color='#506477',lw=.8)
    sign=-1 if admittance else 1
    x=np.linspace(-1000,1000,10001)
    for r in (0,.2,.5,1,2,5):
        z=r+1j*x;g=sign*(z-1)/(z+1);ax.plot(g.real,g.imag,color='#c6d2dd',lw=.55)
        ax.text(sign*(r-1)/(r+1),.018,str(r),fontsize=7,color='#52687b')
    r=np.r_[np.linspace(0,10,1200),np.geomspace(10,10000,300)]
    for reactance in (.2,.5,1,2,5):
        for polarity in (-1,1):
            z=r+1j*polarity*reactance;g=sign*(z-1)/(z+1);ax.plot(g.real,g.imag,color='#c6d2dd',lw=.55)
            edge=sign*(1j*polarity*reactance-1)/(1j*polarity*reactance+1)
            ax.text(edge.real*1.025,edge.imag*1.025,f'{polarity*reactance:g}j',fontsize=7,color='#52687b',ha='center',va='center')
    ax.axhline(0,color='#b7c6d5',lw=.6);ax.set_aspect('equal',adjustable='box')
    ax.set_xlabel('Re(Γ)');ax.set_ylabel('Im(Γ)')


def render(figure,result,expression,view,*,rf_kind='Impedance',z0=50.,mirror=False):
    if view not in VIEWS:raise ValueError('Unknown frequency plot view')
    engine=validate_result(result);frequency=engine.time
    values,unit=series(engine,expression) if view!='Pole-zero' else (None,ONE)
    # Validate view-specific requirements before replacing the visible graph.
    if view=='Pole-zero' and result.get('pole_zero') is None:raise ValueError('No calculated pole-zero data; rerun with pole-zero enabled')
    if view in ('Bode dB / phase','Nichols') and unit!=ONE:raise ValueError('dB gain requires a dimensionless ratio, e.g. V(out)/V(in)')
    if view=='Group delay' and np.any(abs(values)<1e-15):raise ValueError('Group delay is undefined at a transfer zero')
    if view.startswith('Smith') or view in ('Return loss','VSWR'):
        checked_gamma=reflection(values,unit,rf_kind,z0)
        if view=='VSWR' and np.all(abs(checked_gamma)>=1):raise ValueError('VSWR is undefined for all samples with |Γ|≥1')
    for old in figure.axes:
        if old.name=='rectilinear':old.set_xscale('linear')
    figure.clear();plotted=[];phase=None
    if values is not None:phase=np.degrees(np.unwrap(np.angle(values)))
    if view=='Pole-zero':
        pz=result.get('pole_zero')
        if pz is None:raise ValueError('This result has no calculated pole-zero data; rerun with pole-zero enabled')
        ax=figure.add_subplot();data=pz['data'];poles=complex_values(data['poles_rad_s']);zeros=complex_values(data['zeros_rad_s'])
        ax.scatter(poles.real,poles.imag,marker='x',s=70,label='Poles')
        ax.scatter(zeros.real,zeros.imag,marker='o',facecolors='none',edgecolors='#e07b24',s=65,label='Transmission zeros')
        ax.axhline(0,color='gray',lw=.6);ax.axvline(0,color='gray',lw=.6)
        ax.set_xlabel('Re(s) [rad/s]');ax.set_ylabel('Im(s) [rad/s]');ax.grid(alpha=.25);ax.legend()
        ax.set_title('Linear descriptor poles / SISO zeros · no cancellation reduction')
        figure.set_layout_engine('constrained');return []
    def line(ax,x,y,label):
        ax.plot(x,y,lw=1.3,label=label);plotted.append((ax,np.asarray(x),np.asarray(y),frequency))
    def freq_axis(ax,ylabel):
        ax.set_xscale('log');ax.set_xlabel('Frequency [Hz]');ax.set_ylabel(ylabel);ax.grid(True,which='both',alpha=.22)
    if view.startswith('Bode'):
        if view=='Bode dB / phase' and unit!=ONE:raise ValueError('dB gain requires a dimensionless ratio, e.g. V(out)/V(in); use magnitude for dimensioned signals')
        top=figure.add_subplot(211);bottom=figure.add_subplot(212,sharex=top)
        line(top,frequency,db(values) if view=='Bode dB / phase' else abs(values),expression)
        line(bottom,frequency,phase,expression);freq_axis(top,'Magnitude [dB]' if view=='Bode dB / phase' else f'Magnitude [{unit}]');freq_axis(bottom,'Unwrapped phase [°]')
    elif view=='Real / imaginary':
        ax=figure.add_subplot();line(ax,frequency,values.real,'Real');line(ax,frequency,values.imag,'Imaginary');freq_axis(ax,str(unit));ax.legend()
    elif view=='Nyquist':
        ax=figure.add_subplot();line(ax,values.real,values.imag,expression+' (+f)')
        if mirror:ax.plot(values.real,-values.imag,'--',alpha=.5,label='Conjugate mirror (assumes real LTI)')
        if unit==ONE:ax.plot([-1],[0],'+',color='red',label='−1 reference (not stability proof)')
        ax.axhline(0,color='gray',lw=.6);ax.axvline(0,color='gray',lw=.6);ax.set_aspect('equal',adjustable='datalim')
        ax.set_xlabel(f'Re [{unit}]');ax.set_ylabel(f'Im [{unit}]');ax.legend();ax.grid(alpha=.25)
    elif view=='Polar':
        ax=figure.add_subplot(projection='polar');line(ax,np.angle(values),abs(values),expression);ax.set_title(f'Magnitude [{unit}] / phase [°]')
    elif view=='Nichols':
        if unit!=ONE:raise ValueError('Nichols gain requires a dimensionless transfer ratio')
        ax=figure.add_subplot();line(ax,phase,db(values),expression);ax.set_xlabel('Unwrapped phase [°]');ax.set_ylabel('Gain [dB]');ax.grid(alpha=.25)
    elif view=='Group delay':
        if np.any(abs(values)<1e-15):raise ValueError('Group delay is undefined at a transfer zero; restrict the sweep')
        ax=figure.add_subplot();delay=-np.gradient(np.unwrap(np.angle(values)),2*np.pi*frequency,edge_order=2 if len(frequency)>2 else 1)
        line(ax,frequency,delay,expression);freq_axis(ax,'Group delay [s] (sample derivative)')
    else:
        gamma=reflection(values,unit,rf_kind,z0)
        if view.startswith('Smith'):
            ax=figure.add_subplot();smith_grid(ax,view=='Smith admittance');line(ax,gamma.real,gamma.imag,expression)
            extent=max(1.08,float(np.max(abs(gamma)))*1.08);ax.set_xlim(-extent,extent);ax.set_ylim(-extent,extent)
            ax.set_title(f'{view} · Z₀={z0:g} Ω · normalized grid')
        else:
            ax=figure.add_subplot();mag=abs(gamma)
            if view=='Return loss':y=-db(gamma);label='Return loss [dB] (ceiling 300 dB)'
            else:
                y=np.full(mag.shape,np.nan);mask=mag<1;y[mask]=(1+mag[mask])/(1-mag[mask]);label='VSWR (|Γ|≥1 undefined / masked)'
                if not mask.any():raise ValueError('VSWR is undefined for all samples with |Γ|≥1; use Smith to inspect active loads')
            line(ax,frequency,y,expression);freq_axis(ax,label)
    for ax,x,y,f in plotted:
        if len(x):ax.plot(x[0],y[0],'o',ms=4);ax.plot(x[-1],y[-1],'s',ms=4)
    figure.suptitle(view+' · '+expression);figure.set_layout_engine('constrained');return plotted


def save_frequency(path,result):
    validate_result(result);raw=json.dumps(result,allow_nan=False).encode()
    if len(raw)>64*1024*1024:raise ValueError('Frequency archive exceeds 64 MiB expanded budget')
    with gzip.open(path,'xb',compresslevel=5) as stream:stream.write(raw)


def load_frequency(path):
    if Path(path).stat().st_size>64*1024*1024:raise ValueError('Frequency archive exceeds read budget')
    with gzip.open(path,'rb') as stream:raw=stream.read(64*1024*1024+1)
    if len(raw)>64*1024*1024:raise ValueError('Expanded frequency archive exceeds read budget')
    result=json.loads(raw);validate_result(result);return result
