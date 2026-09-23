"""Recorded-signal analytics and non-executable user expression extensions."""
import json
from pathlib import Path
import numpy as np
from .signal_math import SignalMath,Quantity,SECOND

EXTENSION_CONTRACT='spikes/analytics-extension/v1'

def statistics(engine,expression):
    q=engine.evaluate(expression);y=np.asarray(np.broadcast_to(q.values,engine.time.shape))
    if np.iscomplexobj(y):raise ValueError('Choose a real time signal for waveform analytics')
    time=engine.time;dt=np.diff(time)
    mean=float(engine.evaluate(f'mean({expression})').values);rms=float(engine.evaluate(f'rms({expression})').values)
    return {'expression':expression,'unit':str(q.unit),'samples':len(time),'duration_s':float(np.ptp(time)),
        'minimum':float(y.min()),'maximum':float(y.max()),'peak_to_peak':float(np.ptp(y)),
        'mean':mean,'rms':rms,'standard_deviation':float(np.sqrt(max(0,rms*rms-mean*mean))),
        'start':float(y[0]),'end':float(y[-1]),'time_integral':float(np.sum((y[1:]+y[:-1])*dt/2)),
        'integral_unit':str(q.unit.mul(SECOND)),
        'maximum_abs_slew_per_s':float(np.max(abs(np.diff(y)/dt))),
        'min_timestep_s':float(dt.min()),'max_timestep_s':float(dt.max()),
        'basis':'Trapezoidal time-weighted statistics of recorded samples; not a device qualification'}

def spectrum(engine,expression,resample=False):
    q=engine.evaluate(expression);y=np.asarray(np.broadcast_to(q.values,engine.time.shape))
    if np.iscomplexobj(y) or not 8<=len(y)<=262144:raise ValueError('Spectrum requires 8..262144 real samples; capture a smaller window')
    t=engine.time;dt=np.diff(t);uniform=np.allclose(dt,np.mean(dt),rtol=1e-6,atol=abs(np.mean(dt))*1e-9)
    if not uniform:
        if not resample:raise ValueError('Nonuniform timestamps: explicitly allow linear resampling or use a uniform capture')
        grid=np.linspace(t[0],t[-1],len(t));y=np.interp(grid,t,y);t=grid
    window=np.hanning(len(y));fs=1/(t[1]-t[0]);transform=np.fft.rfft(y*window)
    amplitude=2*abs(transform)/window.sum();psd=2*abs(transform)**2/(fs*np.sum(window**2));amplitude[0]/=2;psd[0]/=2
    if len(y)%2==0:amplitude[-1]/=2;psd[-1]/=2
    return {'frequency_hz':np.fft.rfftfreq(len(y),1/fs),'amplitude':amplitude,'psd':psd,'unit':str(q.unit),
        'resampled':not uniform,'window':'Hann','note':'Single-record spectrum; no implicit detrending. Resampling can alter high-frequency content.'}

def validate_extension(data):
    if data.get('contract')!=EXTENSION_CONTRACT:raise ValueError('Unsupported analytics extension contract')
    for key in ('id','name'):
        if not isinstance(data[key],str) or not data[key].strip() or len(data[key])>128:raise ValueError('Extension id/name must be 1..128 characters')
    for kind in ('measurements','traces'):
        if not isinstance(data.get(kind),list) or len(data[kind])>32:raise ValueError('Extensions allow up to 32 measurements and 32 traces')
        for item in data[kind]:
            if set(item)!={'name','expression'} or not all(isinstance(item[k],str) and item[k].strip() and len(item[k])<8192 for k in item):raise ValueError('Each recipe needs a name and expression')
            if len(item['name'])>128:raise ValueError('Recipe name exceeds 128 characters')
        if len({item['name'] for item in data[kind]})!=len(data[kind]):raise ValueError('Recipe names must be unique within each category')
    if set(data)-{'contract','id','name','measurements','traces'}:raise ValueError('Executable entrypoints and unknown extension fields are not accepted')

def load_extension(path):
    if Path(path).stat().st_size>65536:raise ValueError('Analytics extension exceeds 64 KiB')
    data=json.loads(Path(path).read_text(encoding='utf-8'));validate_extension(data);return data

def evaluate_extension(engine,expression,extension):
    validate_extension(extension)
    if len(engine.time)*(len(extension['measurements'])+len(extension['traces']))>2000000:raise ValueError('Extension work exceeds 2 million sample-recipe pairs; use a smaller capture or fewer recipes')
    x=engine.evaluate(expression);result={'id':extension['id'],'measurements':{},'traces':{}}
    for kind in ('measurements','traces'):
        for item in extension[kind]:
            answer=engine.evaluate(item['expression'],variables={'x':x})
            if np.iscomplexobj(answer.values):raise ValueError('Analytics recipes must explicitly choose real, imaginary or magnitude outputs')
            if kind=='measurements' and np.ndim(answer.values):raise ValueError('A measurement recipe must reduce to a scalar')
            result[kind][item['name']]=answer
    return result
