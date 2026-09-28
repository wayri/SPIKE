# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Ask actual OpenFOAM to evaluate t=0 fields in an input-only isolated clone."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.openfoam_multiregion_execution import load_verified_runnable_case,_bounded_command
from python.spike_core.openfoam_runtime import detect_openfoam_runtime
from python.spike_core.sparselizard_process import run_adapter_process
from scripts.fan_wsl_scratch import ScratchRunner


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    original,manifest=load_verified_runnable_case(args.case)
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    clone=root/"case";clone.mkdir()
    for name in [*manifest["input_files"],"spike_multiregion_runnable_case.json"]:
        target=clone/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original/name,target)
    load_verified_runnable_case(clone)
    runtime=detect_openfoam_runtime()
    def runner(command,**kwargs):
        result=run_adapter_process(command,**kwargs)
        (root/"command.json").write_text(json.dumps({"argv":command,**result},indent=2),encoding="utf-8")
        return result
    scratch=ScratchRunner(clone,runner)
    command=_bounded_command(runtime,"chtMultiRegionFoam",clone,"-postProcess","-time","0",timeout_s=120,memory_limit_mb=4096,output_limit_bytes=8*1024**3)
    result=scratch(command,cwd=clone,timeout_s=120,memory_limit_mb=4096,output_limit_bytes=8*1024**3,stream_limit_bytes=32*1024**2,windows_active_process_limit=64)
    histories={}
    for path in (clone/"postProcessing").rglob("volFieldValue.dat"):
        histories[path.relative_to(clone).as_posix()]={"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"text":path.read_text(encoding="ascii")}
    report={"contract":"spike/openfoam-startup-baseline/v1","source_case":str(original),"source_manifest_digest":manifest["manifest_digest"],
        "runtime":runtime,"return_code":result["return_code"],"retained_linux_scratch":scratch.remote,
        "histories":histories,"status":"observed" if result["return_code"]==0 and histories else "failed",
        "production_qualified":False,"command_sha256":hashlib.sha256((root/"command.json").read_bytes()).hexdigest()}
    (root/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="observed" else 1


if __name__=="__main__":
    raise SystemExit(main())
