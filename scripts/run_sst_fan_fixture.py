# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Local SST forced-flow smoke; coarse mesh, no wall or turbulence qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core import openfoam_fan_fixture as fixture
from python.spike_core.openfoam_multiregion_execution import run_multiregion_case
from python.spike_core.sparselizard_process import run_adapter_process
from scripts.fan_wsl_scratch import ScratchRunner


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--laminar-control',action='store_true')
    args=parser.parse_args()
    original=fixture.prepare_runnable_multiregion_case
    def prepare(request,*pos,**kw):
        if not args.laminar_control:
            request['environment']['turbulence_model']={'type':'kOmegaSST','initial_k_m2_s2':.1,
                'inlet_k_m2_s2':.1,'initial_omega_per_s':1000,'inlet_omega_per_s':1000,'turbulent_prandtl':.85}
        request['fans'][0]['flow_rate_m3_s']=.001
        return original(request,*pos,**kw)
    with patch.object(fixture,'prepare_runnable_multiregion_case',side_effect=prepare):
        prepared=fixture.build_fan_heated_fixture(args.output,divisions=4,delta_t_s=.00001,
                                                 end_time_s=.02,write_interval_steps=2000)
    (args.output/'fixture.json').write_text(json.dumps(prepared,indent=2),encoding='utf-8')
    count=0
    def runner(command,**kw):
        nonlocal count
        count+=1
        kw['stream_limit_bytes']=128*1024**2
        result=run_adapter_process(command,**kw)
        (args.output/f'command-{count:02d}.json').write_text(json.dumps({'argv':command,**result}),encoding='utf-8')
        return result
    active=ScratchRunner(args.output/'case',runner)
    result=run_multiregion_case(args.output/'case',timeout_s=900,runner=active)
    result['retained_linux_scratch']=active.remote
    result['turbulence_qualified']=False
    result['wall_resolution_qualified']=False
    (args.output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    artifacts={str(p.relative_to(args.output)):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(args.output.rglob('*')) if p.is_file()}
    (args.output/'artifact-sha256.json').write_text(json.dumps(artifacts,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'summary':result.get('summary'),'message':result.get('message')}))
    return 0 if result['status']=='completed' else 1


if __name__=='__main__': raise SystemExit(main())
