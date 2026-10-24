# SPDX-License-Identifier: Apache-2.0
"""Run compiled controller + conservative magnetic ports + retained CFD loads.

This headless runner never substitutes BEM, fitted motor constants or synthetic
loads. Input representation checks do not establish source/grid/material
qualification; retain the separate convergence receipts with the result.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from python.spike_core.propulsion_pod_geometry_run import execute_geometry_run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--magnetic-table',required=True,type=Path)
    parser.add_argument('--cfd-table',required=True,type=Path)
    parser.add_argument('--request',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Choose a new output path; retained results are not overwritten')
    sources={name:path.read_bytes() for name,path in (
        ('magnetic_table',args.magnetic_table),('cfd_table',args.cfd_table),('request',args.request))}
    inputs={name:json.loads(data) for name,data in sources.items()}
    r=inputs['request']
    expected={'initial_currents_a','initial_angle_rad','initial_speed_rad_s','thermal','drive','shaft','transient'}
    if set(r)!=expected:raise ValueError('Explicit initial conditions, thermal, drive, shaft and transient required')
    canonical=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()
    params={**inputs,'expected_field_sha256':canonical(inputs['magnetic_table']),
            'expected_fluid_sha256':canonical(inputs['cfd_table'])}
    scratch=ROOT/'output/.tmp';scratch.mkdir(parents=True,exist_ok=True)
    old_temp=tempfile.tempdir;old_env={key:os.environ.get(key) for key in ('TMP','TEMP')}
    try:
        tempfile.tempdir=str(scratch)
        for key in old_env:os.environ[key]=str(scratch)
        out=execute_geometry_run(params)
    finally:
        tempfile.tempdir=old_temp
        for key,value in old_env.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
    out['input_file_sha256']={name:hashlib.sha256(data).hexdigest() for name,data in sources.items()}
    out['source_qualifications']={'magnetic':inputs['magnetic_table'].get('qualification',{}),
        'fluid':inputs['cfd_table']['evidence']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'result':str(args.output.resolve()),'accepted_steps':out['accepted_steps'],
        'controller_ticks':out['controller_ticks'],'energy_defect_j':out['energy']['defect_j'],
        'physical_load_qualified':False}))


if __name__=='__main__':main()
