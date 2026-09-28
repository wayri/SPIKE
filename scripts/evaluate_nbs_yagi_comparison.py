# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Evaluate an existing immutable Yagi run without replaying the solver."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from python.spike_core.antenna_measured_comparison import evaluate_temporal_admission

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',type=Path,required=True)
    args=parser.parse_args()
    data=(args.case/'solver-result.json').read_bytes()
    log=(args.case/'solver.log').read_bytes()
    report=evaluate_temporal_admission(log.decode(errors='replace'),json.loads(data)['radiated_to_accepted_ratio'])
    report['input_sha256']={'solver-result.json':hashlib.sha256(data).hexdigest(),'solver.log':hashlib.sha256(log).hexdigest()}
    with (args.case/'numerical-admission.json').open('x') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report))
    return 0 if report['status']=='exploratory_only' else 1

if __name__=='__main__':
    raise SystemExit(main())
