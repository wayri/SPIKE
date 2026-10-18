# SPDX-License-Identifier: Apache-2.0
"""Bounded native CLI STEP exports; default excludes copper and fusion."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument('--output-root',type=Path,default=Path(__file__).resolve().parent)
p.add_argument('--cli',default='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe')
a=p.parse_args()
root=a.output_root.resolve()
jobs=[(c['name'],c['name'],[]) for c in json.loads((root/'inputs.json').read_text())['cases']]
for side in ['front','back']:
    jobs.append((side+'-90-no-extra',side+'-90',['--no-extra-pad-thickness']))
    jobs.append((side+'-90-copper',side+'-90',['--no-extra-pad-thickness','--include-pads','--include-tracks']))
for name,board_name,flags in jobs:
    cmd=[a.cli,'pcb','export','step','--force']+flags+['--user-origin','0x0mm','--output',str(root/(name+'.step')),str(root/(board_name+'.kicad_pcb'))]
    start=time.monotonic()
    result={'command':cmd,'timeout_s':30}
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        result.update(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
    except subprocess.TimeoutExpired as exc:
        result.update(returncode=None,timed_out=True,stdout=str(exc.stdout),stderr=str(exc.stderr))
    result['elapsed_s']=time.monotonic()-start
    out=root/(name+'.step')
    if out.is_file():result['output_sha256']=hashlib.sha256(out.read_bytes()).hexdigest()
    (root/(name+'-export.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(name,result['returncode'],result['elapsed_s'],flush=True)
    assert result['returncode']==0 and out.is_file(), result
