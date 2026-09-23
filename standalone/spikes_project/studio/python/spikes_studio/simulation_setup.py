"""Project environment and run-profile contracts. Geometry is not a thermal solver."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import math
import re
import time
import uuid


def default_thermal():
    return {'contract':'spikes/thermal-setup/v1','solver_binding':'not_coupled',
        'board':{'length_mm':100.,'width_mm':80.,'thickness_mm':1.6,'material':'FR4 (assumption)',
                 'orientation':'horizontal','layers':[{'name':f'L{i+1}','copper_um':35.,'coverage_pct':50.} for i in range(4)]},
        'enclosure':{'type':'open_air','material':'Unspecified','length_mm':150.,'width_mm':120.,'height_mm':50.,
                     'wall_mm':2.,'vent_area_mm2':0.},
        'environment':{'ambient_c':25.,'airflow':'natural','air_speed_m_s':0.,'direction':'parallel_to_board',
                       'convection_w_m2k':None,'altitude_m':0.},
        'notes':'Initial authoring assumptions; replace with actual board/environment data.'}


def default_profile():
    return {'contract':'spikes/run-profile/v1','name':'Default','execution':'batch','analysis':'from_netlist',
            'time_step':'10u','stop_time':'5m','uic':True,'method':'hybrid_trapezoidal',
            'capture_samples':20000,'speed_ratio':1.,'electrical_temperature_c':None}


def finite(value,label,low=None,high=None,exclusive=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(f'{label} must be a finite number')
    if low is not None and (value<=low if exclusive else value<low):raise ValueError(f'{label} is below its allowed range')
    if high is not None and value>high:raise ValueError(f'{label} exceeds {high}')


def choice(value,allowed,label):
    if value not in allowed:raise ValueError(f'Unsupported {label}: {value}')


def validate_thermal(setup):
    if setup.get('contract')!='spikes/thermal-setup/v1' or setup.get('solver_binding')!='not_coupled':raise ValueError('Unsupported thermal setup / solver binding')
    board,enclosure,environment=setup['board'],setup['enclosure'],setup['environment']
    for key in ('length_mm','width_mm','thickness_mm'):finite(board[key],f'Board {key}',0,100000,True)
    choice(board['orientation'],('horizontal','vertical'),'board orientation')
    layers=board['layers']
    if not isinstance(layers,list) or not 1<=len(layers)<=64:raise ValueError('Board needs 1..64 copper layers')
    if len({l['name'].strip().lower() for l in layers})!=len(layers):raise ValueError('Layer names must be unique')
    for layer in layers:
        if not layer['name'].strip():raise ValueError('Layer name cannot be empty')
        finite(layer['copper_um'],'Copper thickness [µm]',0,10000,True)
        finite(layer['coverage_pct'],'Copper coverage [%]',0,100)
    if sum(l['copper_um'] for l in layers)/1000>=board['thickness_mm']:raise ValueError('Total copper thickness must be less than total board thickness')
    choice(enclosure['type'],('open_air','ventilated','sealed'),'enclosure type')
    for key in ('length_mm','width_mm','height_mm','wall_mm'):finite(enclosure[key],f'Enclosure {key}',0,100000,True)
    finite(enclosure['vent_area_mm2'],'Vent area',0,1e10)
    if enclosure['type']!='open_air' and 2*enclosure['wall_mm']>=min(enclosure[k] for k in ('length_mm','width_mm','height_mm')):raise ValueError('Enclosure walls consume its entire interior')
    finite(environment['ambient_c'],'Ambient temperature [°C]',-273.15,2000,True)
    finite(environment['air_speed_m_s'],'Air speed [m/s]',0,1000)
    finite(environment['altitude_m'],'Altitude [m]',-500,100000)
    choice(environment['airflow'],('still','natural','forced'),'airflow mode')
    choice(environment['direction'],('parallel_to_board','normal_to_board','unspecified'),'airflow direction')
    if environment['airflow']=='forced' and environment['air_speed_m_s']<=0:raise ValueError('Forced airflow requires a positive air speed')
    if environment['airflow']!='forced' and environment['air_speed_m_s']!=0:raise ValueError('Set airflow to forced when specifying an imposed air speed')
    if environment['convection_w_m2k'] is not None:finite(environment['convection_w_m2k'],'Convection coefficient',0,1e6,True)
    for value in (board['material'],enclosure['material'],setup['notes']):
        if not isinstance(value,str) or len(value)>8192:raise ValueError('Material/notes must be bounded text')


def validate_profile(profile):
    from python.spikes.netlist import parse_spice_number
    if profile.get('contract')!='spikes/run-profile/v1':raise ValueError('Unsupported run profile')
    if not isinstance(profile['name'],str) or not profile['name'].strip() or len(profile['name'])>128:raise ValueError('Profile name must be 1..128 characters')
    choice(profile['execution'],('batch','continuous'),'execution mode')
    choice(profile['analysis'],('from_netlist','transient','operating_point'),'analysis')
    choice(profile['method'],('hybrid_trapezoidal','backward_euler','bdf2'),'integration method')
    if not isinstance(profile['uic'],bool):raise ValueError('UIC must be boolean')
    step=parse_spice_number(profile['time_step'],'time');stop=parse_spice_number(profile['stop_time'],'time')
    if step<=0 or stop<step:raise ValueError('Require 0 < timestep <= stop time')
    capacity=profile['capture_samples']
    if isinstance(capacity,bool) or not isinstance(capacity,int) or not 2<=capacity<=200000:raise ValueError('Capture window must be 2..200000 samples')
    finite(profile['speed_ratio'],'Simulated seconds / wall second',0,1e6,True)
    if profile['electrical_temperature_c'] is not None:finite(profile['electrical_temperature_c'],'Electrical .TEMP [°C]',-273.15,2000,True)
    if profile['execution']=='continuous' and profile['analysis']=='operating_point':raise ValueError('Continuous mode requires transient analysis')


def effective_source(source,profile):
    """Apply explicit run-only overrides, leaving the schematic source untouched."""
    validate_profile(profile)
    lines=source.splitlines()
    def replace_directive(pattern,replacement):
        matches=[i for i,line in enumerate(lines) if re.match(pattern,line,re.I)]
        if len(matches)>1:raise ValueError('Multiple analysis/temperature directives require Circuit text editing')
        if matches:
            i=matches[0]
            if i+1<len(lines) and lines[i+1].lstrip().startswith('+'):raise ValueError('Continued analysis directives require Circuit text editing')
            lines[i]=replacement
        else:
            i=next((i for i,line in enumerate(lines) if re.match(r'^\s*\.end\s*(?:;.*)?$',line,re.I)),len(lines))
            lines.insert(i,replacement)
    if profile['analysis']!='from_netlist':
        text='.op' if profile['analysis']=='operating_point' else f'.tran {profile["time_step"]} {profile["stop_time"]}'+(' uic' if profile['uic'] else '')
        replace_directive(r'^\s*\.(?:op|tran|ac|dc)\b',text)
    if profile['electrical_temperature_c'] is not None:replace_directive(r'^\s*\.temp\b',f'.temp {profile["electrical_temperature_c"]:.12g}')
    return '\n'.join(lines)+'\n'


class RunHistory:
    """Bounded metadata history, not an unbounded in-memory waveform archive."""
    def __init__(self,capacity=50):
        self.capacity=capacity;self.records=[];self._starts={}

    def start(self,snapshot,library):
        record={'contract':'spikes/run-record/v1','id':uuid.uuid4().hex,'project_id':snapshot['id'],
                'title':snapshot['title'],'revision':snapshot['revision'],'profile':deepcopy(snapshot['run_profile']),
                'thermal_setup':deepcopy(snapshot['thermal_setup']),
                'resolved_models':deepcopy(snapshot.get('resolved_models')),
                'source_sha256':hashlib.sha256(snapshot['source'].encode()).hexdigest(),
                'library':str(library),'started_utc':datetime.now(timezone.utc).isoformat(),
                'state':'starting','wall_seconds':0.,'samples':0,'simulation_time_s':None,
                'capture_archive':None,'error':None,'thermal_solver_binding':'not_coupled'}
        self.records.append(record);self._starts[record['id']]=time.monotonic()
        while len(self.records)>self.capacity:self._starts.pop(self.records.pop(0)['id'],None)
        return record['id']

    def get(self,ident):return next((r for r in self.records if r['id']==ident),None)

    def update(self,ident,state,*,data=None,error=None):
        record=self.get(ident)
        if record is None:return
        record.update(state=state,error=error,wall_seconds=time.monotonic()-self._starts[ident])
        if data:
            times=data.get('time_s',[])
            record['samples']=len(times) if times else len(data['frequency_hz']) if 'frequency_hz' in data else (1 if data.get('node_voltage_v') else 0)
            record['simulation_time_s']=times[-1] if times else None
        if state in ('completed','stopped','failed'):record['ended_utc']=datetime.now(timezone.utc).isoformat()
