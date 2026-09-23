# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""One warmup/five measured native SI postprocessing runs on pinned real data."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.admit_cambridge_measured_si import FILES,admit_blob
from python.spike_core.sparameters import analyze_network


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    admission=json.loads((args.input/'admission.json').read_text())
    payloads={name:(args.input/name).read_bytes() for name in FILES}
    for name,payload in payloads.items():
        if hashlib.sha256(payload).hexdigest()!=admission['files'][name]['sha256']:
            raise ValueError('Pinned measured data SHA256 mismatch')
    timings=[]; result_hashes=[]
    for iteration in range(6):
        started=time.perf_counter()
        reports={name:analyze_network(admit_blob(name,payload)[0],trace_limit=None) for name,payload in payloads.items()}
        elapsed=time.perf_counter()-started
        result_hashes.append(hashlib.sha256(json.dumps(reports,sort_keys=True,allow_nan=False).encode()).hexdigest())
        if iteration: timings.append(elapsed)
    if len(set(result_hashes))!=1: raise ValueError('Nonrepeatable measured-data postprocessing')
    report={'contract':'spike/measured-si-postprocessing-benchmark/v1','status':'passed','machine':platform.platform(),
            'warmup_runs':1,'measured_runs':5,'seconds':timings,'median_seconds':statistics.median(timings),
            'input_sha256':{name:hashlib.sha256(payload).hexdigest() for name,payload in payloads.items()},
            'repeatable_result_sha256':result_hashes[0],'production_qualified':False,'geometry_correlation_qualified':False,
            'scope':'Measured file admission, full retained network analysis and repeatability; not measurement uncertainty or solver correlation'}
    with args.output.open('x',encoding='utf-8') as stream: json.dump(report,stream,indent=2)
    print(json.dumps(report))


if __name__=='__main__': raise SystemExit(main())
