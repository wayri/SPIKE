# SPDX-License-Identifier: Apache-2.0
"""Re-solve actual magnetic fields at selected accepted loop states, headlessly.

Snapshots are a separate spatial reconstruction of the retained planar model,
not new controller steps, a temporal interpolation, or an unsteady fluid solve.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from python.spike_core.propulsion_pod_separated_motor import SeparatedMotor
from examples.promo_showcase.propulsion_pod.coupled.package_geometry_loop import canonical_hash,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('domains','result','magnetic-table','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--count',type=int,default=9)
    p.add_argument('--wall-budget-s',type=float,default=180.)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Choose a new retained result path')
    if not 2<=a.count<=25 or not 10<=a.wall_budget_s<=600:raise ValueError('Bounded frame count/wall budget required')
    result=json.loads(a.result.read_bytes());table=json.loads(a.magnetic_table.read_bytes())
    if result.get('contract')!='spike/geometry-propulsion-loop-result/v1' or result.get('status')!='completed':
        raise ValueError('Completed geometry loop required')
    if result.get('field_table_sha256')!=canonical_hash(table):raise ValueError('Magnetic table differs from executed loop')
    if table.get('source_domains_sha256')!=digest(a.domains):raise ValueError('Exact retained domain-file binding required')
    depth=table['stack_depth_m'];mode=table['maximum_fourier_mode']
    if type(depth) not in (int,float) or not math.isfinite(depth) or depth<=0 or type(mode) is not int:
        raise ValueError('Explicit positive stack depth and integer Fourier cutoff required')
    domains=json.loads(a.domains.read_bytes())
    if not isinstance(table.get('source_field_evidence'),list) or not table['source_field_evidence']:
        raise ValueError('Retained angular source evidence required')
    for evidence in table['source_field_evidence']:
        for key in ('source_sha256','geometry_sha256','spec_sha256'):
            if evidence.get(key)!=domains.get(key):raise ValueError('Field source binding differs: '+key)
        if evidence['mesh_diagnostics']['fourier_maximum_mode']!=mode:raise ValueError('Field Fourier cutoff differs')
    started=time.monotonic();model=SeparatedMotor(domains,stack_depth_m=depth,maximum_mode=mode)
    history=result['history'];frames=[]
    for index in sorted(set(np.linspace(0,len(history)-1,a.count,dtype=int).tolist())):
        if time.monotonic()-started>a.wall_budget_s:raise ValueError('Snapshot wall budget exceeded; incomplete capture refused')
        state=history[index]
        frames.append({'history_index':index,'snapshot':model.field_snapshot(state['currents_a'],state['angle_rad'],grid_nodes=33)})
    if time.monotonic()-started>a.wall_budget_s:raise ValueError('Snapshot wall budget exceeded; incomplete capture refused')
    result['field_snapshots']=frames
    result['field_snapshot_derivation']={'input_result_file_sha256':digest(a.result),
        'domain_file_sha256':digest(a.domains),'magnetic_table_file_sha256':digest(a.magnetic_table),
        'source_sha256':model.source_sha256,'geometry_sha256':model.geometry_sha256,
        'stack_depth_m':depth,'maximum_fourier_mode':mode,
        'script_sha256':digest(Path(__file__)),'operator_sha256':digest(ROOT/'python/spike_core/propulsion_pod_separated_motor.py'),
        'wall_s':time.monotonic()-started,'physical_qualified':False,
        'scope':'Actual discrete P2/Fourier field re-solves at saved endpoint currents/angles; sampled display patches, no temporal interpolation.'}
    data=json.dumps(result,indent=2,allow_nan=False)
    if len(json.dumps(result,allow_nan=False))>14*1024*1024:raise ValueError('Enriched result exceeds GUI capture budget; reduce count')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(data,encoding='utf-8')
    print(json.dumps({'result':str(a.output.resolve()),'saved_field_states':len(frames),'gui_verified':False}))


if __name__=='__main__':main()
