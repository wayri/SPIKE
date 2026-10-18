# SPDX-License-Identifier: Apache-2.0
"""Relocatable, bounded native placement reproduction using installed tools."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

p=argparse.ArgumentParser()
p.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[2])
p.add_argument('--output-root',type=Path,default=Path(__file__).resolve().parent)
p.add_argument('--kicad-python',default='C:/Program Files/KiCad/10.0/bin/python.exe')
p.add_argument('--cli',default='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe')
p.add_argument('--freecad-python',default='C:/Users/yawar/AppData/Local/Programs/FreeCAD 1.1/bin/python.exe')
a=p.parse_args();source=Path(__file__).resolve().parent;root=a.output_root.resolve();repo=a.repo_root.resolve()
root.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,SPIKE_STEP_REFERENCE_ROOT=str(root),SPIKE_STEP_REFERENCE_REPO=str(repo))

def run(name,cmd,timeout):
    start=time.monotonic();record={'command':cmd,'timeout_s':timeout}
    try:
        done=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,env=env)
        record.update(returncode=done.returncode,stdout=done.stdout,stderr=done.stderr)
    except subprocess.TimeoutExpired as exc:
        record.update(returncode=None,timed_out=True,stdout=str(exc.stdout),stderr=str(exc.stderr))
    record['elapsed_s']=time.monotonic()-start
    (root/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    print(name,record['returncode'],round(record['elapsed_s'],3),flush=True)
    assert record['returncode']==0,record

run('step-help',[a.cli,'pcb','export','step','--help'],15)
run('version',[a.cli,'--version'],15)
run('prepare-log',[a.kicad_python,str(source/'prepare.py'),'--repo-root',str(repo),'--output-root',str(root)],30)
run('export-log',[sys.executable,str(source/'export.py'),'--cli',a.cli,'--output-root',str(root)],260)
run('inspect-log',[a.freecad_python,str(source/'inspect_solids.py')],30)
# Checker stdout is retained separately and intentionally excluded from its own hash report.
run('check-log',[sys.executable,str(source/'check_reference.py'),'--repo-root',str(repo),'--output-root',str(root)],15)
