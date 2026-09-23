"""Display-only extrema decimation. Measurements keep the unmodified samples."""
import numpy as np


def extrema_indices(values, budget=4000):
    values=np.asarray(values)
    if values.ndim!=1 or budget<4:raise ValueError('Need a vector and a budget >=4')
    count=len(values)
    if count<=budget:return np.arange(count)
    bins=(budget-2)//2
    edges=np.linspace(1,count-1,bins+1,dtype=int)
    picked=[0,count-1]
    for left,right in zip(edges[:-1],edges[1:]):
        if right>left:
            segment=values[left:right]
            picked.extend((left+int(np.argmin(segment)),left+int(np.argmax(segment))))
    return np.unique(picked)


def viewport_indices(time, values, limits=None, budget=4000):
    """Keep boundary neighbours and extrema from the *visible* original samples."""
    time=np.asarray(time);values=np.asarray(values)
    if time.ndim!=1 or values.shape!=time.shape:raise ValueError('Time and signal must be equally sized vectors')
    if not len(time):return np.array([],dtype=int)
    if limits is None:return extrema_indices(values,budget)
    low,high=sorted(limits)
    if not np.isfinite([low,high]).all():raise ValueError('Viewport must be finite')
    left=max(0,int(np.searchsorted(time,low))-1)
    right=min(len(time),int(np.searchsorted(time,high,side='right'))+1)
    return left+extrema_indices(values[left:right],budget)


def add_waveform(axis,time,values,**style):
    """Plot bounded display data while retaining an immutable-by-convention source."""
    time=np.asarray(time);values=np.asarray(values)
    from .waveform_index import WaveformIndex
    index=WaveformIndex(time,values)
    indices=index.indices()
    line,=axis.plot(time[indices],values[indices],**style)
    line._spikes_samples=(time,values)
    line._spikes_index=index
    return line


def refresh_viewport(axis):
    for line in axis.lines:
        source=getattr(line,'_spikes_samples',None)
        if source is None:continue
        time,values=source
        index=getattr(line,'_spikes_index',None)
        indices=index.indices(axis.get_xlim()) if index is not None else viewport_indices(time,values,axis.get_xlim())
        line.set_data(time[indices],values[indices])


def fit_visible_y(axes):
    """Fit visible signals, excluding cursor lines and hidden traces."""
    for axis in axes:
        bounds=[]
        for line in axis.lines:
            source=getattr(line,'_spikes_samples',None)
            if source is None or not line.get_visible():continue
            time,values=source;low,high=sorted(axis.get_xlim())
            left=int(np.searchsorted(time,low));right=int(np.searchsorted(time,high,side='right'))
            window=values[left:right]
            if len(time) and low<=time[-1] and high>=time[0]:
                window=np.r_[window,np.interp([max(low,time[0]),min(high,time[-1])],time,values)]
            finite=window[np.isfinite(window)]
            if len(finite):bounds.extend((float(np.min(finite)),float(np.max(finite))))
        if bounds:
            low,high=min(bounds),max(bounds);pad=(high-low)*.05 if high!=low else max(abs(low)*.05,1e-12)
            axis.set_ylim(low-pad,high+pad)


def wheel_target(event,axes):
    """Resolve plot interior and axis gutters in display pixels, not data units."""
    if event.inaxes in axes:
        return event.inaxes, 'y' if event.key=='shift' else 'x'
    for axis in axes:
        box=axis.bbox
        if box.y0<=event.y<=box.y1 and box.x0-80<=event.x<box.x0:
            return axis,'y'
        if box.x0<=event.x<=box.x1 and box.y0-45<=event.y<box.y0:
            return axis,'x'
    return None,None


def zoom_limits(limits,anchor,factor,scale='linear'):
    values=np.array([limits[0],limits[1],anchor],dtype=float)
    if scale=='log':
        if np.any(values<=0):return limits
        values=np.log(values)
    low,high,anchor=values
    result=anchor+(np.array([low,high])-anchor)*factor
    if scale=='log':result=np.exp(result)
    if not np.isfinite(result).all() or result[0]==result[1]:return limits
    return tuple(result)


def install_navigation(canvas,axes):
    """Reconnect after figure rebuild: wheel zooms linked time; Shift zooms Y."""
    old=getattr(canvas,'_spikes_scroll_connection',None)
    if old is not None:canvas.mpl_disconnect(old)
    for axis in axes:
        previous=getattr(axis,'_spikes_limits_connection',None)
        if previous is not None:axis.callbacks.disconnect(previous)
        axis._spikes_limits_connection=axis.callbacks.connect('xlim_changed',refresh_viewport)
        refresh_viewport(axis)
    def scroll(event):
        axis,dimension=wheel_target(event,axes)
        if axis is None:return
        factor=1.25**(-max(-5,min(5,event.step)))
        x,y=axis.transData.inverted().transform((event.x,event.y))
        if dimension=='y':
            axis.set_ylim(zoom_limits(axis.get_ylim(),y,factor,axis.get_yscale()))
        else:
            axis.set_xlim(zoom_limits(axis.get_xlim(),x,factor,axis.get_xscale()))
        canvas.draw_idle()
    canvas._spikes_scroll_connection=canvas.mpl_connect('scroll_event',scroll)
