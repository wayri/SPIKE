# SPDX-License-Identifier: Apache-2.0
"""Trusted isolated FDTD driver for admitted material polyhedra."""

WORKER = r'''
import json, math
from importlib.metadata import version
from pathlib import Path
import numpy as np
import h5py
from CSXCAD import ContinuousStructure
from openEMS import openEMS

root=Path.cwd()
compiled=INPUT['compiled']; settings=INPUT['settings']
csx=ContinuousStructure()
fdtd=openEMS(NrTS=settings['max_timesteps'],EndCriteria=settings['end_criteria'])
fdtd.SetCSX(csx)
frequencies=np.asarray(settings['frequency_hz'])
f0=(frequencies[0]+frequencies[-1])/2
fc=max((frequencies[-1]-frequencies[0])/2,f0/2)
fdtd.SetGaussExcite(float(f0),float(fc))
fdtd.SetBoundaryCond(['PML_8']*6)
emit_retained_volume_geometry(csx,compiled)
grid=csx.GetGrid(); grid.SetDeltaUnit(1.)
vertices=np.asarray([p for primitive in compiled['primitives'] for p in primitive['vertices_m']])
edge=settings['mesh_resolution_m']; margin=settings['air_margin_m']
ports=[]
for i,p in enumerate(compiled['ports']):
    ports.append(fdtd.AddLumpedPort(i+1,p['reference_impedance_ohm'],p['start_m'],p['stop_m'],p['direction'],
                 1. if p['excite'] else 0.,priority=50))
for axis,values in enumerate(retained_em_grid_axes(compiled,settings)):
    grid.AddLine(axis,values)
lines={axis:np.asarray(grid.GetLines(i,do_sort=True)).tolist() for i,axis in enumerate('xyz')}
metrics=actual_grid_report({a:[v*1000 for v in values] for a,values in lines.items()},
                          1000000,512*1024**2)
metrics.update(require_time_window(metrics,settings['max_timesteps'],float(frequencies[0]),float(frequencies[-1])))
for axis,values in enumerate(lines.values()):
    if values[8]>=vertices[:,axis].min() or values[-9]<=vertices[:,axis].max():
        raise ValueError('PML overlaps admitted material')
sub=max(1,math.ceil((metrics['cell_count']/50000)**(1/3)))
for name,kind in [('electric-field',10),('magnetic-field',11)]:
    dump=csx.AddDump(name,dump_type=kind,dump_mode=2,file_type=1,
                     frequency=[float(frequencies[-1])],sub_sampling=[sub,sub,sub])
    dump.AddBox(vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist())
csx.Write2XML(str(root/'geometry.xml'))
fdtd.Run(str(root/'simulation'),cleanup=False,verbose=0,numThreads=settings['threads'],max_time=settings['timeout_s'])
excited=next(i for i,p in enumerate(compiled['ports']) if p['excite'])
for p in ports:p.CalcPort(str(root/'simulation'),frequencies)
incident=np.asarray(ports[excited].uf_inc)
if not np.all(np.isfinite(incident)) or np.min(np.abs(incident))<=1e-12*np.max(np.abs(incident)):
    raise ValueError('Incident port spectrum is unresolved')
columns=[]
for definition,p in zip(compiled['ports'],ports):
    values=np.asarray(p.uf_ref)/incident*math.sqrt(compiled['ports'][excited]['reference_impedance_ohm']/definition['reference_impedance_ohm'])
    if not np.all(np.isfinite(values)):raise ValueError('Nonfinite normalized response')
    columns.append({'port_id':definition['id'],'real':values.real.tolist(),'imag':values.imag.tolist()})
captures={}
previews={}
for name in ('electric-field','magnetic-field'):
    path=root/'simulation'/(name+'.h5')
    with h5py.File(path) as data:
        real=data['FieldData/FD/f0_real'][...]; imag=data['FieldData/FD/f0_imag'][...]
        axes={a:data['Mesh/'+a][...].tolist() for a in 'xyz'}
        if (real.shape!=imag.shape or real.ndim!=4 or real.shape[0]!=3 or
                not np.all(np.isfinite(real)) or not np.all(np.isfinite(imag)) or
                not all(np.all(np.isfinite(values)) for values in axes.values())):
            raise ValueError('Malformed/nonfinite retained field capture')
        expected=(len(axes['z']),len(axes['y']),len(axes['x']))
        if real.shape[1:]!=expected:raise ValueError('Retained field axes do not match z/y/x storage shape')
        total=math.prod(expected); stride=max(1,math.ceil(total/8000)); ids=np.arange(0,total,stride,dtype=int)
        iz,iy,ix=np.unravel_index(ids,expected)
        normalized=(real+1j*imag).reshape(3,-1)[:,ids]/incident[-1]
        if not np.all(np.isfinite(normalized)):raise ValueError('Nonfinite incident-normalized field')
        previews[name]={'positions_m':[[axes['x'][int(x)],axes['y'][int(y)],axes['z'][int(z)]] for z,y,x in zip(iz,iy,ix)],
            'vectors':np.stack((normalized.real.T,normalized.imag.T),axis=2).tolist(),
            'native_indices':ids.tolist(),'source_sample_count':total,'sample_stride':stride,
            'units':'V/m' if name=='electric-field' else 'A/m'}
        captures[name]={'file':'simulation/'+name+'.h5','shape':list(real.shape),
                       'maximum_raw_complex_vector_norm':float(np.sqrt(np.sum(real**2+imag**2,axis=0)).max()),
                       'mesh_axes_m':axes}
result={'contract':'spike/assembly-em-result/v1','status':'completed','solver_executed':True,
        'model_status':'unvalidated','production_qualified':False,
        'execution_status':'completed',
        'request_digest':INPUT['request_digest'],'run_id':INPUT['run_id'],
        'compiled_digest':compiled['compiled_digest'],'frequency_hz':frequencies.tolist(),
        'excited_port_id':compiled['ports'][excited]['id'],'s_parameter_column':columns,
        'mesh':{'actual_grid':metrics,'lines_m':lines},
        'field_capture':{'frequency_hz':float(frequencies[-1]),'normalization':'raw_gaussian_pulse_dft',
                         'electric_units':'V*s/m pulse DFT','magnetic_units':'A*s/m pulse DFT',
                         'transform_convention':'2*dt*sum(value*exp(-j*omega*t))',
                         'incident_voltage_dft':{'real':incident.real.tolist(),'imag':incident.imag.tolist(),'units':'V*s'},
                         'preview':{'contract':'spike/assembly-em-preview/v1','frequency_hz':float(frequencies[-1]),
                             'normalization':'1V_peak_incident','coordinate_frame':'assembly','coordinate_units':'m',
                             'datasets':previews},
                         'interpolation':'cell','sub_sampling':sub,'datasets':captures},
        'mesh_policy':settings.get('mesh_policy','all_material_extrema'),
        'runtime_identity':{'engine':'openEMS','python_package_version':version('openEMS'),
                            'adapter':'SPIKE retained-volume driver'},
        'observable_sensitivity':{'status':'not_assessed',
            'reason':'A single execution cannot establish observable sensitivity; compare explicitly paired runs.'},
        'limitations':(['XY geometry is sampled on a Cartesian grid without contour alignment; thin copper connectivity and spatial accuracy are unqualified.'] if settings.get('mesh_policy')=='cartesian_sampling_v1' else [])+['One explicitly excited port column, not a complete S matrix.',
            'Cartesian voxelization requires mesh, PML and duration refinement; no accuracy qualification.',
            'A normal process exit alone does not establish energy-decay or duration convergence.',
            'Finite-conductivity bulk material does not qualify thin-metal skin/roughness losses.',
            'Field dumps retain raw pulse DFT; not calibrated 1 V or 1 W steady-state fields.',
            'No inferred PCB/connector/harness geometry, material values or excitations.']}
(root/'result.json').write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
'''
