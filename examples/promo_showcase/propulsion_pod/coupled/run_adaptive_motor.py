# SPDX-License-Identifier: Apache-2.0
"""Bounded actual-source, current-envelope guided interior refinement.

This runner records spatial differences; it never promotes them to certified
torque errors or admits a production field table automatically.
"""
import argparse
import gc
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from python.spike_core.propulsion_pod_real_motor_domains import build_real_motor_domains,refine_existing_domains
from python.spike_core.propulsion_pod_separated_motor import SeparatedMotor
from python.spike_core.propulsion_pod_magnetic_indicator import magnetic_refinement_indicator


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    base=ROOT/'output/promo-propulsion-pod-20261023/real_motor'
    parser.add_argument('--geometry',type=Path,default=base/'native-section-fine.json')
    parser.add_argument('--spec',type=Path,default=base/'p2-fine-material-request.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--levels',type=int,default=3)
    parser.add_argument('--angles',type=int,default=8)
    parser.add_argument('--mode',type=int,default=895)
    parser.add_argument('--trace',type=int,default=2016)
    parser.add_argument('--edge',type=float,default=.0006)
    parser.add_argument('--current-envelope',type=float,default=10.)
    parser.add_argument('--bulk',type=float,default=.5)
    parser.add_argument('--wall-budget',type=float,default=1200.)
    args=parser.parse_args()
    if not 1<=args.levels<=8 or not 2<=args.angles<=32 or not 0<args.bulk<1 or not 0<args.current_envelope<=100:
        raise ValueError('Bounded levels/angles/current/marking fraction required')
    if not math.isfinite(args.wall_budget) or not 10<=args.wall_budget<=3600:
        raise ValueError('Wall budget must be finite in10..3600seconds')
    if args.output.exists():raise ValueError('Choose a new retained output directory')
    args.output.mkdir(parents=True)
    started=time.monotonic()
    geometry=json.loads(args.geometry.read_bytes());spec=json.loads(args.spec.read_bytes())
    domains=build_real_motor_domains(geometry,spec,args.trace,args.edge,
        repeat_rotor_sector=True,vacuum_trace_layers_m=(25e-6,50e-6,75e-6))
    receipt={'contract':'spike/native-motor-adaptive-attempt/v1','levels':[],
        'source_files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            args.geometry,args.spec,ROOT/'python/spike_core/propulsion_pod_separated_motor.py',
            ROOT/'python/spike_core/propulsion_pod_real_motor_domains.py',ROOT/'python/spike_core/propulsion_pod_magnetic_indicator.py',
            ROOT/'python/spike_core/propulsion_pod_magnetic_p2.py',ROOT/'python/spike_core/propulsion_pod_annular_gap.py',Path(__file__).resolve())},
        'phase_current_envelope_a':args.current_envelope,'angles_count':args.angles,
        'spatial_converged':False,'physical_qualified':False,'complete_loop':False}
    currents=list(itertools.permutations((args.current_envelope,-args.current_envelope,0.)))
    def save():
        receipt['elapsed_s']=time.monotonic()-started
        (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False),encoding='utf-8')
    for level in range(args.levels):
        if time.monotonic()-started>args.wall_budget:
            receipt['stop_reason']='wall budget before next level';save();break
        (args.output/f'domains-{level}.json').write_text(json.dumps(domains,separators=(',',':')),encoding='utf-8')
        model=SeparatedMotor(domains,maximum_mode=args.mode)
        row={'level':level,'samples':[],'mesh':{name:{'nodes':len(domains[name]['nodes_m']),
            'triangles':len(domains[name]['triangles']),'mesh_sha256':domains[name]['mesh_sha256']}
            for name in ('rotor','stator')}}
        receipt['levels'].append(row)
        indicators={name:np.zeros(len(domains[name]['triangles'])) for name in ('rotor','stator')}
        # Low-discrepancy phases avoid sampling only one cogging phase when a
        # uniform angle count shares factors with the slot/pole harmonics.
        phases=np.mod(np.arange(args.angles)*(math.sqrt(5)-1)/2,1.)
        row['angle_selection']='golden-ratio phases within source-proved mechanical period'
        for theta in .002+phases*(2*math.pi/14):
            theta=float(theta);ports=model.linear_ports(theta);basis=model.basis_potentials(theta)
            sample={'angle_rad':theta,'ports':ports,'indicator_maximum_over_current_hexagon':{}}
            for name,domain in (('rotor',model.rotor),('stator',model.stator)):
                chi=np.asarray(domains[name]['winding_chi_per_m2'])
                envelope=np.zeros(len(chi))
                for current in currents:
                    potential=basis[name]@np.r_[1.,current]
                    indicator=magnetic_refinement_indicator(domain.op,potential,chi@current)
                    envelope=np.maximum(envelope,np.asarray(indicator['element_indicator_j']))
                indicators[name]=np.maximum(indicators[name],envelope)
                sample['indicator_maximum_over_current_hexagon'][name]=float(envelope.sum())
            row['samples'].append(sample);save()
        marks={}
        for name,values in indicators.items():
            order=np.argsort(values)[::-1];total=float(values.sum())
            count=0 if total==0 else int(np.searchsorted(np.cumsum(values[order]),args.bulk*total)+1)
            ids=order[:count].astype(int).tolist()
            marks[name]={'mesh_sha256':domains[name]['mesh_sha256'],'triangle_ids':ids}
            row.setdefault('marking',{})[name]={'requested_cells':count,'sum_envelope_indicator_j':total}
        (args.output/f'marks-{level}.json').write_text(json.dumps(marks),encoding='utf-8')
        row['elapsed_s']=time.monotonic()-started;save()
        print(json.dumps({'level':level,'mesh':row['mesh'],'marking':row['marking'],'elapsed_s':row['elapsed_s']}),flush=True)
        del model,basis,domain;gc.collect()
        if level+1<args.levels:
            try:domains=refine_existing_domains(domains,marks)
            except ValueError as error:
                receipt['stop_reason']='refinement rejected: '+str(error);save();break
    else:
        receipt['stop_reason']='declared level count completed; convergence assessment remains separate';save()


if __name__=='__main__':main()
