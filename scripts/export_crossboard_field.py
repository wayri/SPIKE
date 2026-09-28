# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Export screened field S data and explicitly terminated cross-board SI."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.crossboard_field_screen import screen_case
from python.spike_core.sparameters import NetworkData,touchstone_text
from python.spike_core.si_crosstalk import analyze_crosstalk


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    screen=screen_case(args.case)
    payload=(args.case/'field-result.json').read_bytes()
    if hashlib.sha256(payload).hexdigest()!=screen['artifact_sha256']['field-result.json']:
        raise ValueError('Field result changed after screening')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    (root/'screening.json').write_text(json.dumps(screen,indent=2,allow_nan=False),encoding='utf-8')
    if not screen['screen_passed']:
        print('Numerical screen failed; no downstream SI export published.');return 1
    raw=json.loads(payload)
    frequencies=np.asarray(raw['frequency_hz']);s=np.asarray(raw['s_real'])+1j*np.asarray(raw['s_imag'])
    network=NetworkData(frequencies,s,np.repeat(50.,4),source='field-result:'+hashlib.sha256(payload).hexdigest())
    loaded=analyze_crosstalk(network,
        port_map={'aggressor_near':0,'aggressor_far':1,'victim_near':2,'victim_far':3},termination_ohm=[50.]*4)
    loaded['field_provenance']={'source_sha256':hashlib.sha256(payload).hexdigest(),
        'port_order':raw['ports'],'numerical_screen':True,'physical_accuracy_qualified':False,
        'limitations':raw['limitations']+['2% numerical screening is not exact passivity or physical accuracy qualification.']}
    (root/'loaded-crosstalk.json').write_text(json.dumps(loaded,indent=2,allow_nan=False),encoding='utf-8')
    (root/'network.s4p').write_text(touchstone_text(frequencies,s,50.,comments=[
        'Experimental two-board box FDTD; ports A.near A.far B.near B.far, +z polarity.',
        'Numerical screening only; not production or physical accuracy qualification.']),encoding='ascii')
    manifest={'source_sha256':hashlib.sha256(payload).hexdigest(),'production_qualified':False,
        'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'status':'exported_experimental','screen_passed':True}));return 0


if __name__=='__main__':raise SystemExit(main())
