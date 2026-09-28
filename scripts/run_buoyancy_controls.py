# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Actual bounded CHT buoyancy/control runs; not a turbulence benchmark."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from python.spike_core.openfoam_multiregion_fixture import build_two_region_slab_fixture as build_slab_fixture
from python.spike_core.openfoam_multiregion import prepare_runnable_multiregion_case
from python.spike_core.openfoam_multiregion_execution import run_multiregion_case,load_verified_runnable_case
from python.spike_core.openfoam_flow_energy_validation import read_numeric_history
from python.spike_core.openfoam_buoyancy import density_at_temperature
from python.spike_core.sparselizard_process import run_adapter_process
from scripts.fan_wsl_scratch import ScratchRunner


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--end-time",type=float,default=.1);parser.add_argument("--divisions",type=int,default=4)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    source_paths=list((ROOT/"python/spike_core").glob("openfoam*.py"))+[Path(__file__),ROOT/"scripts/fan_wsl_scratch.py"]
    def hashes():return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    before=hashes();report={"contract":"spike/buoyancy-control-study/v1","cases":{},"production_qualified":False,
        "scope":"small variable-density laminar CHT slab with horizontal gravity, no turbulence or independent field correlation", "source_hashes":before}
    for name,power,gravity in (("isothermal_gravity",0.,[-9.81,0.,0.]),("heated_no_gravity",.1,[0.,0.,0.]),("heated_gravity",.1,[-9.81,0.,0.])):
        root=args.output/name;fixture=build_slab_fixture(root/"seed",divisions=args.divisions,end_time_s=args.end_time,delta_t_s=.001)
        request=copy.deepcopy(fixture["request"])
        # Wall-heat-flux output is not used by this buoyancy-only smoke test.
        # Keep its field writes at the final step; T/rho observers still run
        # every timestep independently, without thousands of unused files.
        request["numerics"]["validation_interval_steps"]=round(args.end_time/.001)
        model={"type":"Boussinesq","rho0_kg_m3":1.2,"T0_k":298.15,"beta_per_k":1/298.15,
            "temperature_min_k":290.,"temperature_max_k":315.}
        request["materials"][1]["density_model"]=model
        request["environment"]["gravity_m_s2"]=gravity
        request["heat_sources"][0]["power_w"]=power
        request["heat_sources"][0]["fv_option"]["volumetric_power_w_m3"]=power/(.01*.01*.0016)
        request["heat_sources"][0]["evidence"]["sha256"]=hashlib.sha256(f"bounded-slab-load-{power}".encode()).hexdigest()
        prepared=prepare_runnable_multiregion_case(request,root/"case",root/"seed/meshes")
        (root/"request.json").write_text(json.dumps(request,indent=2),encoding="utf-8")
        if prepared["status"]!="prepared_runnable_case":raise RuntimeError(str(prepared))
        count=0
        def runner(command,**kwargs):
            nonlocal count
            count+=1;kwargs["stream_limit_bytes"]=32*1024**2
            result=run_adapter_process(command,**kwargs)
            (root/f"command-{count:02d}.json").write_text(json.dumps({"argv":command,**result},indent=2),encoding="utf-8")
            return result
        print(f"Running {name}",flush=True)
        scratch=ScratchRunner(root/"case",runner)
        result=run_multiregion_case(root/"case",timeout_s=180,runner=scratch)
        (root/"result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        entry={"status":result["status"],"scratch":scratch.remote,"manifest_digest":load_verified_runnable_case(root/"case")[1]["manifest_digest"]}
        if result["status"]=="completed":
            velocity=np.asarray([v["value"] for v in result["fields"]["velocity_m_s"]["samples"]])
            entry["maximum_speed_m_s"]=float(np.max(np.linalg.norm(velocity,axis=1)))
            traces=[];digests={}
            for operation in ("min","max"):
                paths=list((root/"case/postProcessing/air"/f"spikeBuoyancy{operation}_air").glob("*/volFieldValue.dat"))
                if len(paths)!=1:raise ValueError("Missing buoyancy interval observer")
                values,digest=read_numeric_history(paths[0],3);traces.append(values)
                digests[str(paths[0].relative_to(root))]=digest
            if not np.array_equal(traces[0][:,0],traces[1][:,0]):raise ValueError("Misaligned density extrema")
            tmin=float(np.min(traces[0][:,1]));tmax=float(np.max(traces[1][:,1]))
            density_at_temperature(model,tmin);density_at_temperature(model,tmax)
            rho_min=float(np.min(traces[0][:,2]));rho_max=float(np.max(traces[1][:,2]))
            if rho_min<=0:raise ValueError("Nonpositive observed density")
            entry.update(temperature_min_k=tmin,temperature_max_k=tmax,density_min_kg_m3=rho_min,density_max_kg_m3=rho_max,
                density_interval_passed=True,diagnostic_sha256=digests)
        report["cases"][name]=entry
        (args.output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        if result["status"]!="completed":break
    after=hashes();report["sources_unchanged"]=after==before
    report["changed_sources"]=[name for name in set(before)|set(after) if before.get(name)!=after.get(name)]
    if len(report["cases"])==3 and all(v["status"]=="completed" for v in report["cases"].values()):
        cases=report["cases"]
        control=max(cases["isothermal_gravity"]["maximum_speed_m_s"],cases["heated_no_gravity"]["maximum_speed_m_s"],1e-12)
        report["heated_to_control_speed_ratio"]=cases["heated_gravity"]["maximum_speed_m_s"]/control
        report["buoyancy_smoke_passed"]=report["heated_to_control_speed_ratio"]>10 and cases["heated_gravity"]["maximum_speed_m_s"]>1e-7
    (args.output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
