# SPDX-License-Identifier: Apache-2.0
"""Bounded derived views of recorded samples, independent of solver capability."""
import math
import numpy as np
from .plotting import extrema_indices

VIEWS = ('XY / phase portrait', 'FFT peak amplitude', 'Power spectral density',
         'Eye diagram', 'Histogram', 'Cumulative integral')
MAX_SAMPLES = 262144


def derive(engine, expression, view, *, x_expression='t', period_s=1e-6,
           start_s=None, stop_s=None, window='Hann', bins=64):
    if view not in VIEWS:raise ValueError('Unknown derived plot view')
    time=engine.time
    start=time[0] if start_s is None else start_s;stop=time[-1] if stop_s is None else stop_s
    if not np.isfinite([start,stop]).all() or not time[0]<=start<stop<=time[-1]:
        raise ValueError('Select a finite interval inside the retained timestamps')
    select=(time>=start)&(time<=stop);t=time[select]
    if not 3<=len(t)<=MAX_SAMPLES:raise ValueError(f'Select 3..{MAX_SAMPLES:,} samples; shorten the interval')
    quantity=engine.evaluate(expression);full=np.broadcast_to(quantity.values,time.shape)
    if np.iscomplexobj(full):raise ValueError('Select real(...), imag(...) or abs(...) for transient derived views')
    y=np.asarray(full[select],dtype=float);unit=str(quantity.unit)
    if not np.isfinite(y).all():raise ValueError('Samples must be finite')
    duration=t[-1]-t[0]
    scale=float(np.max(abs(y)))
    normalized=y/scale if scale else y
    mean=float(np.trapezoid(normalized,t)/duration*scale)
    rms=float(np.sqrt(np.trapezoid(normalized*normalized,t)/duration)*scale)
    report={'source_samples':len(t),'start_s':float(t[0]),'stop_s':float(t[-1]),
            'mean':mean,'rms':rms,'minimum':float(y.min()),'maximum':float(y.max()),
            'unit':unit,'sample_policy':'retained original samples; no silent resampling'}
    result={'view':view,'report':report,'curves':[],'x_label':'','y_label':unit}
    if view=='XY / phase portrait':
        xq=engine.evaluate(x_expression);x=np.broadcast_to(xq.values,time.shape)[select]
        if np.iscomplexobj(x):raise ValueError('XY coordinates must be real')
        # Order is retained; time extrema reduction is not suitable for a phase portrait.
        idx=np.unique(np.linspace(0,len(y)-1,min(4096,len(y)),dtype=int))
        result.update(curves=[(x[idx],y[idx])],x_label=f'{x_expression} [{xq.unit}]')
        report['display_policy']='ordered stride sampling, at most 4096 points; small loops may be hidden'
    elif view in ('FFT peak amplitude','Power spectral density'):
        dt=np.diff(t);step=float(np.mean(dt))
        if np.max(abs(dt-step))>step*1e-6:
            raise ValueError('FFT/PSD requires a uniform recording grid (1 ppm tolerance); no implicit resampling')
        if window not in ('Hann','Rectangular'):raise ValueError('Window must be Hann or Rectangular')
        w=np.hanning(len(y)) if window=='Hann' else np.ones(len(y))
        transformed=np.fft.rfft(y*w);frequency=np.fft.rfftfreq(len(y),step)
        factor=np.full(len(frequency),2.);factor[0]=1.
        if len(y)%2==0:factor[-1]=1.
        if view=='FFT peak amplitude':
            value=abs(transformed)/np.sum(w)*factor
            label=f'Peak amplitude [{unit}]'
        else:
            value=abs(transformed)**2*step/np.sum(w*w)*factor
            label=f'PSD [{unit}^2/Hz]'
        idx=extrema_indices(value)
        result.update(curves=[(frequency[idx],value[idx])],x_label='Frequency [Hz]',y_label=label)
        report.update(window=window,frequency_resolution_hz=float(frequency[1]),
                      nyquist_hz=.5/step,dc_removed=False,
                      spectral_policy='one-sided spectrum; DC/Nyquist not doubled; no ENOB/jitter claim')
        peak=int(np.argmax(value));report.update(peak_frequency_hz=float(frequency[peak]),peak_value=float(value[peak]))
        if view=='Power spectral density':report['integrated_psd']=float(np.sum(value)*frequency[1])
    elif view=='Eye diagram':
        if type(period_s) not in (float,int) or not math.isfinite(period_s) or period_s<=0:
            raise ValueError('Symbol period must be finite and positive')
        if np.max(np.diff(t))>period_s/8:raise ValueError('Eye diagram requires at least 8 retained samples per symbol')
        windows=int(duration/period_s)-1
        if windows<1:raise ValueError('Record at least two complete symbol periods')
        starts=np.unique(np.linspace(0,windows-1,min(windows,256),dtype=int))
        offset=np.linspace(0,2*period_s,256)
        curves=[(offset,np.interp(t[0]+index*period_s+offset,t,y)) for index in starts]
        result.update(curves=curves,x_label='Time within two symbols [s]')
        report.update(symbol_period_s=period_s,total_windows=windows,display_windows=len(starts),
                      eye_policy='piecewise-linear interpolation, caller-supplied clock; no clock recovery or BER certification')
    elif view=='Histogram':
        if type(bins) is not int or not 2<=bins<=256:raise ValueError('Histogram bins must be 2..256')
        counts,edges=np.histogram(y,bins=bins)
        result.update(curves=[((edges[:-1]+edges[1:])/2,counts)],x_label=f'{expression} [{unit}]',y_label='Sample count')
        report.update(histogram_total=int(counts.sum()),histogram_policy='sample-weighted, not duration-weighted on adaptive grids')
    else:
        integral=np.r_[0,np.cumsum((y[1:]+y[:-1])*.5*np.diff(t))]
        idx=extrema_indices(integral)
        from .signal_math import SECOND
        result.update(curves=[(t[idx],integral[idx])],x_label='Simulation time [s]',
                      y_label=f'Integral [{quantity.unit.mul(SECOND)}]')
        report.update(final_integral=float(integral[-1]),integration_policy='trapezoidal integration of selected original samples')
    if any(not np.isfinite(x).all() or not np.isfinite(v).all() for x,v in result['curves']):
        raise ValueError('Derived values exceed the finite numeric range')
    if any(isinstance(v,(float,int)) and not math.isfinite(v) for v in report.values()):
        raise ValueError('Measurement exceeds the finite numeric range')
    return result


def render(figure, data):
    figure.clear();figure.set_layout_engine('constrained');axis=figure.add_subplot()
    for x,y in data['curves']:
        if data['view']=='Histogram':axis.step(x,y,where='mid')
        else:axis.plot(x,y,linewidth=.8 if data['view']=='Eye diagram' else 1.2,
                       alpha=.2 if data['view']=='Eye diagram' else 1.)
    axis.set(xlabel=data['x_label'],ylabel=data['y_label'],title=data['view'])
    axis.grid(True,alpha=.2)
    return axis


def describe(report):
    unit=report['unit']
    lines=[f"{report['source_samples']:,} original samples | {report['start_s']:.9g} to {report['stop_s']:.9g} s",
           f"Time-weighted mean: {report['mean']:.9g} {unit} | RMS: {report['rms']:.9g} {unit}",
           f"Minimum: {report['minimum']:.9g} {unit} | Maximum: {report['maximum']:.9g} {unit}"]
    if 'window' in report:
        lines += [f"Window: {report['window']} | Bin spacing: {report['frequency_resolution_hz']:.9g} Hz | Nyquist: {report['nyquist_hz']:.9g} Hz",
                  f"Largest spectral bin: {report['peak_frequency_hz']:.9g} Hz; value {report['peak_value']:.9g} (plot units)"]
    if 'display_windows' in report:lines.append(f"Eye: {report['display_windows']} displayed / {report['total_windows']} complete windows | symbol period {report['symbol_period_s']:.9g} s")
    if 'final_integral' in report:lines.append(f"Final signed integral: {report['final_integral']:.9g} {unit} s")
    if 'histogram_total' in report:lines.append(f"Histogram total: {report['histogram_total']:,} samples (not time-weighted)")
    lines.extend(str(v) for k,v in report.items() if k.endswith('policy'))
    return '\n'.join(lines)
