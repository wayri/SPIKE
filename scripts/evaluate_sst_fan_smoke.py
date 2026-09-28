# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Audit retained SST fields and explicit Prt; not a turbulence accuracy gate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.openfoam_multiregion_execution import _latest_time, _parse_internal_field, load_verified_runnable_case


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.input=args.input.resolve()
    expected=json.loads((args.input/'artifact-sha256.json').read_text())
    observed={}
    def verify(path):
        if path.is_symlink() or not path.is_file() or path.stat().st_size>32*1024**2:
            raise ValueError('Missing or oversized SST artifact')
        key=str(path.relative_to(args.input))
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if expected.get(key)!=digest: raise ValueError('SST artifact hash mismatch')
        observed[key]=digest
    fixture_path=args.input/'fixture.json'
    verify(fixture_path)
    fixture=json.loads(fixture_path.read_text())
    request=fixture['request']
    model=request['environment']['turbulence_model']
    case,manifest=load_verified_runnable_case(args.input/'case')
    directory=_latest_time(case)/'air'
    fields={}
    for name in ('k','omega','nut','alphat'):
        path=directory/name
        verify(path)
        fields[name]=np.asarray(_parse_internal_field(path,expected_count=64))
        if fields[name].shape!=(64,) or not np.all(np.isfinite(fields[name])) or np.any(fields[name]<=0):
            raise ValueError('Expected finite positive SST smoke fields')
    density=next(m['density_kg_m3'] for m in request['materials'] if m['phase']=='fluid')
    ratios=density*fields['nut']/fields['alphat']
    error=float(np.max(np.abs(ratios-model['turbulent_prandtl'])))
    if error>1e-8: raise ValueError('Retained turbulent diffusivity does not match explicit Prt')
    report={'contract':'spike/sst-smoke-field-audit/v1','status':'passed','input_hashes':observed,
        'manifest_digest':manifest['manifest_digest'],'model':'kOmegaSST','explicit_prt':model['turbulent_prandtl'],
        'maximum_absolute_prt_error':error,'ranges':{name:[float(v.min()),float(v.max())] for name,v in fields.items()},
        'production_qualified':False,'wall_resolution_qualified':False,
        'scope':'64-cell forced-fan runtime and constitutive identity smoke, not turbulence correlation'}
    with args.output.open('x',encoding='utf-8') as stream: json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report))


if __name__=='__main__': raise SystemExit(main())
