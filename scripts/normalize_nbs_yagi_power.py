# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Normalize an original NBS spectral result using retained port time traces.

Execute using the configured openEMS Python runtime; does not rerun FDTD.
Original artifacts are immutable. A hashed correction sidecar is published.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--case',type=Path,required=True)
args=parser.parse_args()
root=args.case.resolve()
raw=(root/'solver-result.json').read_bytes()
result=json.loads(raw)
if result.get('power_normalization'):
    raise ValueError('Already normalized')
csx=ContinuousStructure()
fdtd=openEMS(); fdtd.SetCSX(csx)
csx.GetGrid().SetDeltaUnit(.001)
port=fdtd.AddLumpedPort(1,50,[0,-2,0],[0,2,0],'y',1,priority=20)
port.CalcPort(str(root/'simulation'),[400e6])
incident=float((.5*np.abs(port.uf_inc)**2/50)[0])
if not np.isfinite(incident) or incident<=0:
    raise ValueError('Invalid incident spectrum')
report={'contract':'spike/antenna-power-normalization-correction/v1',
        'normalization':'one_watt_incident','radiated_power_w':result['radiated_power_w']/incident,
        'accepted_power_w':result['accepted_power_w']/incident,
        'gain_and_directivity_unchanged':True,
        'original_power_fields_are':'unnormalized Fourier spectral products, not steady-state watts',
        'input_sha256':{'solver-result.json':hashlib.sha256(raw).hexdigest()},
        'measured_qualification':False}
for name in ['port_it_1','port_ut_1']:
    report['input_sha256']['simulation/'+name]=hashlib.sha256((root/'simulation'/name).read_bytes()).hexdigest()
with (root/'power-normalization-correction.json').open('x') as stream:
    json.dump(report,stream,indent=2,allow_nan=False)
print(json.dumps(report))
