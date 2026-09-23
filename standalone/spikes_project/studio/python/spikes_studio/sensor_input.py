"""Bounded recorded sensor input, evaluated by native PWL in simulation time.

This module never opens physical devices or plays sound.
"""
from pathlib import Path
import csv
import hashlib
import io
import wave
import numpy as np

MAX_BYTES=16*1024*1024
MAX_SAMPLES=20000


def load_recording(path,*,channel=0,gain=1.0,offset=0.0,unit='normalized'):
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise ValueError('Recording exceeds 16 MiB; crop it first')
    raw=path.read_bytes()
    if len(raw)>MAX_BYTES:raise ValueError('Recording exceeds 16 MiB')
    if type(channel) is not int or channel<0:raise ValueError('Channel must be a nonnegative integer')
    gain=float(gain);offset=float(offset)
    if not np.isfinite([gain,offset]).all():raise ValueError('Gain and offset must be finite')
    if not isinstance(unit,str) or not unit.strip() or len(unit)>80:raise ValueError('Provide a short input unit label')
    if path.suffix.lower()=='.wav':
        with wave.open(io.BytesIO(raw),'rb') as wav:
            n=wav.getnframes();channels=wav.getnchannels();width=wav.getsampwidth();rate=wav.getframerate()
            if not 2<=n<=MAX_SAMPLES:raise ValueError('Use 2..20000 frames; crop the file (no silent decimation)')
            if channel>=channels:raise ValueError('Selected channel is absent')
            if width not in (1,2,3,4) or wav.getcomptype()!='NONE':raise ValueError('Use uncompressed integer PCM WAV')
            data=wav.readframes(n)
            if len(data)!=n*channels*width:raise ValueError('Truncated WAV data')
        if width==1:values=(np.frombuffer(data,dtype=np.uint8).astype(float)-128)/128
        elif width==3:
            b=np.frombuffer(data,dtype=np.uint8).reshape(-1,3).astype(np.int32)
            v=b[:,0]|(b[:,1]<<8)|(b[:,2]<<16);values=np.where(v & 0x800000,v-0x1000000,v)/8388608
        else:values=np.frombuffer(data,dtype='<i'+str(width)).astype(float)/float(2**(8*width-1))
        values=values.reshape(-1,channels)[:,channel];times=np.arange(n,dtype=float)/rate
        encoding=f'PCM{8*width}; normalized full scale, not acoustic pressure'
    elif path.suffix.lower()=='.csv':
        rows=csv.reader(io.StringIO(raw.decode('utf-8-sig')))
        header=next(rows,None)
        if not header or header[0].strip()!='time_s':raise ValueError('CSV header must be time_s,<channel>,...')
        if channel+1>=len(header):raise ValueError('Selected channel is absent')
        points=[]
        for row in rows:
            if not row:continue
            if len(points)>=MAX_SAMPLES:raise ValueError('CSV exceeds 20000 samples')
            if len(row)!=len(header):raise ValueError('CSV row does not match header')
            points.append((float(row[0]),float(row[channel+1])))
        if len(points)<2:raise ValueError('At least two samples are required')
        times,values=np.asarray(points,dtype=float).T;encoding='CSV SI time; user-declared amplitude units'
    else:raise ValueError('Choose PCM .wav or timestamped .csv')
    with np.errstate(over='ignore',invalid='ignore'):scaled=values*gain+offset
    if not np.isfinite(times).all() or not np.isfinite(scaled).all():raise ValueError('Recording and scaled output must be finite')
    if times[0]!=0 or np.any(np.diff(times)<=0):raise ValueError('Times must start at zero and increase strictly')
    return {'time_s':times.tolist(),'values':scaled.tolist(),'provenance':{
        'file_name':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'channel':channel,
        'gain':gain,'offset':offset,'input_unit':unit,'encoding':encoding,
        'samples':len(times),'duration_s':float(times[-1]),
        'interpolation':'linear; last value held after recording end','physical_device_io':False}}


def apply_recording(source,ref,recording):
    from .part_properties import rewrite
    points='\n'.join(f'{t:.17g} {v:.17g}' for t,v in zip(recording['time_s'],recording['values']))
    return rewrite(source,ref,{},model={'mode':'pwl','fields':{'points':points}})
