# SPDX-License-Identifier: Apache-2.0
"""Execute an explicitly synthetic coherent-wave multiport calibration study."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from python.spike_core.solvers.signal_integrity.networks.multiport_calibration import calibrate_multiport, input_basis


def demonstration():
    n, count = 3, 2
    ports = ['connector-left','connector-right','auxiliary-port']
    d = np.array([.02+.01j,-.03+.02j,.01-.015j])
    v = np.array([.06-.025j,-.07+.015j,.08+.02j])
    u = np.array([.8+.05j,.9-.12j,.75+.11j])
    w = np.array([.85-.08j,.82+.07j,.92-.03j])
    known = np.array([[.1,.32+.03j,.28-.02j],[.32+.03j,-.05,.23+.01j],[.28-.02j,.23+.01j,.02]])
    wanted = np.array([[.1+.02j,.2-.03j,-.12+.07j],[.35+.04j,.15-.01j,.22j],[-.08j,.18+.06j,-.1]])
    def ri(z): return {'real':float(z.real),'imag':float(z.imag)}
    def record(a): return [[ri(z) for z in row] for row in a]
    def forward(s):
        # Full simultaneous internal-wave system, not the calibration inverse.
        matrix = np.block([[np.eye(n),-np.diag(v)],[-s,np.eye(n)]])
        rhs = np.vstack([np.diag(w),np.zeros((n,n))])
        waves = np.linalg.solve(matrix,rhs)
        return np.diag(d)+np.diag(u)@waves[n:]
    standards = [{'id':label,'provenance':'SPIKE synthetic lumped per-port standard v1; not a certificate',
                  'reflection':[],'measured':[]} for label in ('open-C','short-L','load-R')]
    for f in (1e8,1e9):
        omega = 2*np.pi*f
        zs = [[1/(1j*omega*(30+p*5)*1e-15) for p in range(n)],
              [1j*omega*(20+p*4)*1e-12 for p in range(n)], [50.1+p*.2 for p in range(n)]]
        for j,row in enumerate(zs):
            g = (np.asarray(row)-50)/(np.asarray(row)+50)
            measured = d+u*w*g/(1-v*g)
            standards[j]['reflection'].append([ri(z) for z in g])
            standards[j]['measured'].append([ri(z) for z in measured])
    size = 2*count*(6*n+3*n*n)
    shared = 1e-5*np.sin(np.arange(size)*.7)
    cov = np.diag(np.full(size,1e-10))+np.outer(shared,shared)
    return {'contract':'spike/multiport-calibration-request/v1','id':'synthetic-three-port-calibration-v1',
            'port_names':ports,'reference_impedance_ohm':50.,'frequencies_hz':[1e8,1e9],
            'measurement_basis':'coherent_wave_matrix_ratio','gain_reference_port':ports[0],
            'reflection_standards':standards,
            'coupling_standard':{'id':'known-synthetic-coupler','provenance':'SPIKE synthetic known coupling matrix v1',
                                 's_parameters':[record(known) for _ in range(count)],
                                 'measured':[record(forward(known)) for _ in range(count)]},
            'dut':{'id':'synthetic-dut','provenance':'SPIKE independent synthetic nonreciprocal DUT matrix v1',
                   'measured':[record(forward(wanted)) for _ in range(count)]},
            'covariance':{'basis':input_basis(ports,count),'matrix':cov.tolist(),
                          'provenance':'SPIKE synthetic diagonal noise plus one shared cross-port/cross-frequency mode v1'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8')) if args.request else demonstration()
    capture = {'source':request,'result':calibrate_multiport(request)}
    with args.output.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(capture,allow_nan=False,indent=2)+'\n')
    print('Experimental multiport source/result retained; no physical or release qualification.')


if __name__ == '__main__': main()
