# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Execute three PEC cavity meshes with uniform conductive loss, not PCB modes."""
import argparse
import hashlib
import json
import math
import os
import platform
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from python.spike_core.external_engines import _run_isolated_python
from python.spike_core.runtime_locations import openems_python, openems_install_root
from python.spike_core.si_ringdown import qualify_ringdown, qualify_ringdown_convergence

WORKER = r'''
import json, sys
from pathlib import Path
import numpy as np
from importlib.metadata import version
from CSXCAD import ContinuousStructure
from openEMS import openEMS
root=Path(sys.argv[1]); n=int(sys.argv[2])
csx=ContinuousStructure(); grid=csx.GetGrid(); grid.SetDeltaUnit(1)
for axis,length in zip('xyz',[.1,.06,.1]):
    grid.AddLine(axis,np.linspace(0,length,n+1))
fdtd=openEMS(NrTS=20000,EndCriteria=1e-12,MaxTime=40e-9)
fdtd.SetCSX(csx); fdtd.SetBoundaryCond(['PEC']*6); fdtd.SetDiracExcite(10e9)
medium=csx.AddMaterial('conductive_vacuum',epsilon=1,kappa=.001)
medium.AddBox([0,0,0],[.1,.06,.1])
exc=csx.AddExcitation('mode_impulse',exc_type=0,exc_val=[0,1,0])
exc.SetWeightFunction(['0','sin(pi*x/0.1)*sin(pi*z/0.1)','0'])
exc.AddBox([0,0,0],[.1,.06,.1])
probe=csx.AddProbe('probe',p_type=0)
probe.AddBox([.05,0,.05],[.05,.06,.05])
fdtd.Run(str(root),cleanup=False,verbose=0,numThreads=2)
(root/'runtime.json').write_text(json.dumps({'openems_version':version('openEMS'),'n':n}))
'''


def reference_checks(errors, convergence, sources_unchanged):
    """Fixed acceptance for this reference geometry only, never a general gate."""
    checks={'sources_unchanged':sources_unchanged is True,
            'numerical_stability':convergence.get('status')=='numerically_stable_observed_mode'}
    for key in ('frequency_hz','q_factor','amplitude_decay_per_s'):
        values=[row.get(key) for row in errors]
        valid=len(values)==3 and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 for v in values)
        checks[key+'_error_within_0_1_percent']=valid and all(v<=.001 for v in values)
        if key != 'amplitude_decay_per_s':
            checks[key+'_error_decreases']=bool(valid and values[2]<values[1]<values[0])
    return {'status':'qualified_reference_case' if all(checks.values()) else 'not_qualified',
            'reference_checks':checks,'exit_code':0 if all(checks.values()) else 1,
            'decay_convergence_limitation':'Decay-rate errors are bounded but nonmonotonic; no asymptotic decay-rate order is established.'}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True)
    args=parser.parse_args(); root=Path(args.output).resolve(); root.mkdir(parents=True,exist_ok=False)
    source_paths=[Path(__file__),Path(__file__).resolve().parents[1]/'python/spike_core/si_ringdown.py']
    source_hashes={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    (root/'worker.py').write_bytes(WORKER.encode())
    env=os.environ.copy(); env['OPENEMS_INSTALL_PATH']=openems_install_root()
    reports=[]; runs=[]
    for n in (16,24,32):
        case=root/f'mesh-{n}'; case.mkdir()
        execution=_run_isolated_python(openems_python(),WORKER.encode(),[str(case),str(n)],cwd=root,
            environment=env,log_path=case/'solver.log',output_root=case,timeout_seconds=180)
        run={'n':n,'execution':execution}; runs.append(run)
        if execution['returncode'] != 0 or execution['timed_out'] or execution['quota_exceeded'] or not (case/'probe').is_file():
            (root/'report.json').write_text(json.dumps({'status':'solver_failed','runs':runs},indent=2)); return 1
        data=np.loadtxt(case/'probe',comments='%'); selected=data[:,0]>2e-9
        report=qualify_ringdown(data[selected,0],data[selected,1],source_off_time_s=2e-9)
        reports.append(report); run['ringdown']=report
        run['artifacts']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in case.iterdir() if p.is_file()}
    eps=8.8541878128e-12; c=299792458.; alpha=.001/(2*eps)
    omega0=np.pi*c*np.sqrt(2)/.1; frequency=np.sqrt(omega0**2-alpha**2)/(2*np.pi)
    analytic={'frequency_hz':frequency,'q_factor':np.pi*frequency/alpha,'amplitude_decay_per_s':alpha}
    convergence=qualify_ringdown_convergence(reports,[.1/n for n in (16,24,32)])
    errors=[{key:abs(report['mode'][key]/value-1) if 'mode' in report else None for key,value in analytic.items()} for report in reports]
    output={'status':convergence['status'],'production_qualified':False,'physical_eigenmode_qualified':False,
       'scope':'PEC 0.1 x 0.06 x 0.1 m cavity, Ey sin(pi*x/a)sin(pi*z/d), uniform sigma=.001 S/m, epsilon0, mu0; no ports',
       'source':'Spatial modal Dirac excitation, observing only t>2 ns. No forced harmonic drive during observation.',
       'analytic':analytic,'relative_errors':errors,'convergence':convergence,'runs':runs,
       'machine':platform.platform(),'worker_sha256':hashlib.sha256(WORKER.encode()).hexdigest(),
       'source_hashes':source_hashes,
       'sources_unchanged':all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in source_hashes.items()),
       'runtime_executable_sha256':hashlib.sha256((Path(openems_install_root())/'openEMS.exe').read_bytes()).hexdigest(),
       'analytic_derivation':'Maxwell modal amplitude satisfies a_ddot+(sigma/epsilon0)*a_dot+omega0^2*a=0; alpha=sigma/(2*epsilon0), omega0=c*pi*sqrt(1/a^2+1/d^2), omega_d=sqrt(omega0^2-alpha^2), Q=omega_d/(2*alpha).',
       'references':['https://docs.openems.de/python/CSXCAD/CSProperties/CSPropExcitation.html',
                     'https://docs.openems.de/python/CSXCAD/CSProperties/CSPropProbeBox.html',
                     'https://github.com/NanoComp/harminv']}
    admission=reference_checks(errors,convergence,output['sources_unchanged'])
    output.update(admission)
    (root/'report.json').write_text(json.dumps(output,indent=2,allow_nan=False))
    print(json.dumps({'status':output['status'],'relative_errors':errors,'reference_checks':admission['reference_checks']}))
    return admission['exit_code']


if __name__=='__main__':
    raise SystemExit(main())
