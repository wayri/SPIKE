# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded 0.05s experiments: startup energy with four/sixteen outer iterations."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.openfoam_fan_fixture import build_fan_heated_fixture
from python.spike_core.openfoam_multiregion import prepare_runnable_multiregion_case
from python.spike_core.openfoam_multiregion_execution import run_multiregion_case
from python.spike_core.openfoam_flow_energy_validation import validate_flow_energy
from python.spike_core.sparselizard_process import run_adapter_process
from scripts.fan_wsl_scratch import ScratchRunner


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--dpdt-disabled",action="store_true",help="Explicit experimental constant-density enthalpy policy without pressure-derivative work")
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    report={"contract":"spike/fan-startup-corrector-probe/v1","cases":{},"production_qualified":False,
        "dpdt_enabled":not args.dpdt_disabled,"policy":"Explicit environment.dpdt_enabled=false selects constant_density_no_dpdt via normal request API" if args.dpdt_disabled else "Original pressure-derivative enthalpy equation"}
    for correctors in (4,16):
        target=root/f"outer{correctors}"
        template=build_fan_heated_fixture(target/"template",divisions=4,delta_t_s=.001,end_time_s=.05,write_interval_steps=50)
        request=copy.deepcopy(template["request"]);request["numerics"]["outer_correctors"]=correctors
        if args.dpdt_disabled:
            request["environment"]["dpdt_enabled"]=False
        prepared=prepare_runnable_multiregion_case(request,target/"case",target/"template/meshes")
        if prepared["status"]!="prepared_runnable_case":
            raise ValueError("Probe case preparation failed")
        count=0
        def runner(command,**kwargs):
            nonlocal count
            count+=1
            result=run_adapter_process(command,**kwargs)
            (target/f"command-{count:02d}.json").write_text(json.dumps({"argv":command,**result},indent=2),encoding="utf-8")
            return result
        result=run_multiregion_case(target/"case",timeout_s=120,runner=ScratchRunner(target/"case",runner))
        (target/"result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        if result["status"]!="completed":
            raise ValueError(f"Probe solver failed: {result.get('message')}")
        subprocess.run([sys.executable,str(ROOT/"scripts/read_fan_startup_baseline.py"),str(target/"case"),"--output",str(target/"baseline")],check=True,capture_output=True,text=True)
        energy=validate_flow_energy(target/"case",dpdt_enabled=not args.dpdt_disabled,orthogonal_constant_k=True,relative_tolerance=.001,include_startup=True,startup_baseline=target/"baseline/report.json")
        report["cases"][str(correctors)]=energy
        (root/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
        print(correctors,energy["passed"],energy["first_step_audit"]["relative_residual"],flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
