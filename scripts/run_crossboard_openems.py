# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Execute a four-port, two-substrate field example with explicit air separation.

This is an experimental box-geometry benchmark, not an arbitrary PCB importer.
Every external port is excited in a separate FDTD run. No coupling terms are
invented from a network cascade. Existing output directories are refused.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.openems_assembly_geometry import compile_assembly_geometry
from python.spike_core.external_engines import _run_isolated_python
from python.spike_core.runtime_locations import openems_python, openems_install_root
from python.spike_core.crossboard_mesh import plan_crossboard_mesh


def fixture(gap_mm):
    identity = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]
    def box(name, kind, start, stop):
        return {"id":name,"kind":kind,"start_mm":start,"stop_mm":stop,
                "epsilon_r":3.4 if kind=="dielectric" else 1.,
                "conductivity_s_m":0. if kind=="dielectric" else 5.8e7}
    boards=[]
    for name, bottom, top, trace0, trace1, ground0, ground1 in (
        ("A",-1.,0.,0.,.1,-1.1,-1.),
        ("B",gap_mm,gap_mm+1,gap_mm-.1,gap_mm,gap_mm+1,gap_mm+1.1)):
        boards.append({"id":name,"world_from_local_mm":identity,
            "boxes":[box("substrate","dielectric",[-20,-10,bottom],[20,10,top]),
                     box("signal","conductor",[-15,-1,trace0],[15,1,trace1]),
                     box("return","conductor",[-20,-10,ground0],[20,10,ground1])]})
    return {"contract":"spike/openems-box-assembly/v1","air_margin_mm":35.,"boards":boards}


WORKER = r'''
import json, math
from pathlib import Path
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from importlib.metadata import version

root=Path(OUTPUT)
raw=RAW
compiled=compile_assembly_geometry(raw)
gap=GAP
frequencies=np.linspace(.2e9,3e9,101)
incidents=[];reflections=[];mesh_records=[]
for excited in range(4):
    csx=ContinuousStructure()
    fdtd=openEMS(NrTS=MAX_STEPS,EndCriteria=END_CRITERIA)
    fdtd.SetCSX(csx);fdtd.SetGaussExcite(1.5e9,1.5e9)
    fdtd.SetBoundaryCond(["PML_8"]*6)
    emit_csxcad_geometry(csx,raw)
    grid=csx.GetGrid();grid.SetDeltaUnit(1e-3)
    # Ports connect signal and its own reference conductor, never two boards.
    definitions=[([-15,-1,-1],[-15,1,0]),([15,-1,-1],[15,1,0]),
                 ([-15,-1,gap],[-15,1,gap+1]),([15,-1,gap],[15,1,gap+1])]
    plan=plan_crossboard_mesh(compiled,definitions,base_spacing_mm=MESH,level=MESH_LEVEL)
    for axis in range(3):grid.AddLine(axis,plan['lines_mm'][axis])
    ports=[]
    for index,(start,stop) in enumerate(definitions):
        for axis in range(3):
            grid.AddLine(axis,[(start[axis]+stop[axis])/2])
        ports.append(fdtd.AddLumpedPort(index+1,50.,start,stop,'z',
                     1. if index==excited else 0.,priority=50,edges2grid='all'))
    inner=[]
    for axis in range(3):
        lines=grid.GetLines(axis,do_sort=True)
        low=min(box['start_mm'][axis] for box in compiled['boxes'])
        high=max(box['stop_mm'][axis] for box in compiled['boxes'])
        if len(lines)<19 or not lines[8]<low or not lines[-9]>high:
            raise ValueError('Eight-cell PML overlaps or touches assembly material')
        inner.append([float(lines[8]),float(lines[-9])])
    dimensions=[len(grid.GetLines(axis,do_sort=True))-1 for axis in range(3)]
    cells=math.prod(dimensions)
    if cells>1500000:raise ValueError('Cross-board fixture exceeds 1.5 million cells')
    mesh_records.append({'dimensions':dimensions,'cells':cells,'inner_pml_bounds_mm':inner,
                         'policy':plan['policy'],'level':MESH_LEVEL,'lines_mm':plan['lines_mm']})
    case=root/('excitation-'+str(excited));case.mkdir()
    csx.Write2XML(str(case/'geometry.xml'))
    fdtd.Run(str(case/'simulation'),cleanup=True,verbose=0,numThreads=2)
    for port in ports:port.CalcPort(str(case/'simulation'),frequencies,ref_impedance=50.)
    incident=np.asarray(ports[excited].uf_inc)
    if not np.isfinite(incident).all() or np.any(np.abs(incident)<1e-10*max(np.max(np.abs(incident)),1e-30)):
        raise ValueError('Insufficient incident spectrum')
    incidents.append(np.stack([np.asarray(port.uf_inc) for port in ports],axis=1))
    reflections.append(np.stack([np.asarray(port.uf_ref) for port in ports],axis=1))
a=np.stack(incidents,axis=2);b=np.stack(reflections,axis=2)
s,normalization=solve_multi_excitation(a,b)
if not np.isfinite(s).all():raise ValueError('Nonfinite field response')
result={'contract':'spike/crossboard-box-field-example/v1','status':'executed',
        'solver':'openEMS','solver_version':version('openEMS'),'frequency_hz':frequencies.tolist(),
        's_real':s.real.tolist(),'s_imag':s.imag.tolist(),'reference_impedance_ohm':50.,
        'excitation_normalization':normalization,
        'incident_real':a.real.tolist(),'incident_imag':a.imag.tolist(),
        'reflected_real':b.real.tolist(),'reflected_imag':b.imag.tolist(),
        'ports':['A.near','A.far','B.near','B.far'],'gap_mm':gap,'mesh_resolution_mm':MESH/2**MESH_LEVEL,
        'mesh_policy':plan['policy'],'mesh_level':MESH_LEVEL,'base_mesh_spacing_mm':MESH,
        'end_criteria':END_CRITERIA,'max_timesteps':MAX_STEPS,
        'meshes':mesh_records,'maximum_singular_value':float(np.linalg.svd(s,compute_uv=False).max()),
        'maximum_reciprocity_absolute_error':float(np.abs(s-s.transpose(0,2,1)).max()),
        'crossboard_s31_peak_magnitude':float(np.abs(s[:,2,0]).max()),
        'crossboard_s41_peak_magnitude':float(np.abs(s[:,3,0]).max()),
        'field_coupling_executed':True,'production_qualified':False,
        'limitations':['Explicit box geometry only; not arbitrary DesignIR import.',
        'Finite-conductivity Cartesian FDTD requires mesh, PML and duration convergence; coarse copper cells do not resolve RF skin loss.',
        'All port polarities are +z; board B is opposite its signal-to-return voltage polarity.',
        'Four field excitations, not a cascade or inferred missing S-parameters.']}
(root/'field-result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
print(json.dumps({k:result[k] for k in ('status','maximum_singular_value','maximum_reciprocity_absolute_error','crossboard_s31_peak_magnitude')}))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gap-mm',type=float,default=4.)
    parser.add_argument('--mesh-mm',type=float,default=2.)
    parser.add_argument('--mesh-level',type=int,choices=(0,1,2),default=0)
    parser.add_argument('--plan-only',action='store_true',help='Print bounded mesh plan without launching a solver')
    parser.add_argument('--timeout',type=int,default=240)
    parser.add_argument('--end-criteria',type=float,default=1e-7)
    parser.add_argument('--max-timesteps',type=int,default=120000)
    args=parser.parse_args()
    if not 1<=args.gap_mm<=20 or not .5<=args.mesh_mm<=3 or not 10<=args.timeout<=1800:
        parser.error('Require gap 1..20 mm, mesh .5..3 mm, timeout 10..1800 s')
    if not 1e-8<=args.end_criteria<=1e-3 or not 10000<=args.max_timesteps<=200000:
        parser.error('Require end criterion 1e-8..1e-3 and 10000..200000 timesteps')
    raw=fixture(args.gap_mm);compiled=compile_assembly_geometry(raw)
    definitions=[([-15,-1,-1],[-15,1,0]),([15,-1,-1],[15,1,0]),
                 ([-15,-1,args.gap_mm],[-15,1,args.gap_mm+1]),([15,-1,args.gap_mm],[15,1,args.gap_mm+1])]
    plan=plan_crossboard_mesh(compiled,definitions,base_spacing_mm=args.mesh_mm,level=args.mesh_level)
    if args.plan_only:
        print(json.dumps(plan,indent=2));return 0
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    module=ROOT/'python/spike_core/openems_assembly_geometry.py'
    normalization_module=ROOT/'python/spike_core/multi_excitation_network.py'
    mesh_module=ROOT/'python/spike_core/crossboard_mesh.py'
    source='\n'.join(p.read_text(encoding='utf-8') for p in (module,normalization_module,mesh_module))
    before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (module,normalization_module,mesh_module,Path(__file__))}
    # Trusted source snapshot plus serialized data; never execute user text.
    payload=(source+'\nOUTPUT='+repr(str(output))+'\nRAW='+repr(raw)+
             '\nGAP='+repr(args.gap_mm)+'\nMESH='+repr(args.mesh_mm)+'\nMESH_LEVEL='+repr(args.mesh_level)+
             '\nEND_CRITERIA='+repr(args.end_criteria)+'\nMAX_STEPS='+repr(args.max_timesteps)+'\n'+WORKER).encode()
    (output/'geometry.json').write_text(json.dumps(raw,indent=2,allow_nan=False),encoding='utf-8')
    (output/'compiled.json').write_text(json.dumps(compiled,indent=2,allow_nan=False),encoding='utf-8')
    environment={key:os.environ[key] for key in ('PATH','SYSTEMROOT','WINDIR','USERPROFILE','LD_LIBRARY_PATH') if key in os.environ}
    environment.update(OPENEMS_INSTALL_PATH=openems_install_root(),TEMP=str(output),TMP=str(output))
    begin=time.perf_counter()
    execution=_run_isolated_python(openems_python(),payload,[],cwd=output,environment=environment,
        log_path=output/'solver.log',output_root=output,timeout_seconds=args.timeout,output_limit_bytes=512*1024**2)
    after={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in before}
    report={'status':'executed' if execution['returncode']==0 and before==after else 'failed',
            'execution':execution,'elapsed_s':time.perf_counter()-begin,'machine':platform.platform(),
            'source_sha256':before,'sources_unchanged':before==after,'worker_sha256':hashlib.sha256(payload).hexdigest(),
            'artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*.json')},
            'production_qualified':False}
    (output/'execution.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(report,indent=2));return 0 if report['status']=='executed' else 1


if __name__=='__main__':raise SystemExit(main())
