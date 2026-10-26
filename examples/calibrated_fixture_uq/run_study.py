# SPDX-License-Identifier: Apache-2.0
"""Explicit synthetic joint calibration/fixture covariance study."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from examples.multiport_calibration.run_calibration import demonstration as calibration_demo
from python.spike_core.solvers.signal_integrity.networks.calibrated_fixture_uq import compose_calibrated_fixture,input_basis


def demonstration():
    cal=calibration_demo();n=3;f=2
    d=np.array([.02+.01j,-.03+.02j,.01-.015j]);v=np.array([.06-.025j,-.07+.015j,.08+.02j])
    u=np.array([.8+.05j,.9-.12j,.75+.11j]);w=np.array([.85-.08j,.82+.07j,.92-.03j])
    dut=np.array([[.1+.02j,.2-.03j,-.12+.07j],[.35+.04j,.15-.01j,.22j],[-.08j,.18+.06j,-.1]])
    eye=np.eye(n);off=np.ones((n,n))-eye
    fixture_matrix=np.block([[.02*eye+.005j*off,.8*eye+.02*off],[.85*eye-.01j*off,.03*eye+.007*off]])
    def encode(z):return {'real':float(z.real),'imag':float(z.imag)} if np.ndim(z)==0 else [encode(x) for x in z]
    # Two independent forward wave systems synthesize physical fixture then
    # instrument measurements; neither calls an inverse calibration operation.
    fi=fixture_matrix[n:,n:];fe=fixture_matrix[n:,:n]
    waves=np.linalg.solve(np.block([[eye,-fi],[-dut,eye]]),np.vstack([fe,np.zeros((n,n))]))
    embedded=fixture_matrix[:n,:n]+fixture_matrix[:n,n:]@waves[n:]
    instrument_waves=np.linalg.solve(np.block([[eye,-np.diag(v)],[-embedded,eye]]),np.vstack([np.diag(w),np.zeros((n,n))]))
    measured=np.diag(d)+np.diag(u)@instrument_waves[n:]
    cal['dut']['measured']=[encode(measured) for _ in range(f)]
    fixture={'id':'synthetic-physical-fixture-v1','port_names':cal['port_names']+[f'board.p{i}' for i in range(n)],
             'reference_impedance_ohm':50.,'frequencies_hz':list(cal['frequencies_hz']),
             's_parameters':[encode(fixture_matrix) for _ in range(f)]}
    c=np.asarray(cal['covariance']['matrix']);m=len(c);tail=8*f*n*n
    common=1e-5*np.sin(np.arange(m)*.7);extra=8e-6*np.cos(np.arange(tail)*.3)
    full=np.zeros((m+tail,m+tail));full[:m,:m]=c
    full[:m,m:]=np.outer(common,extra);full[m:,:m]=full[:m,m:].T
    full[m:,m:]=np.diag(np.full(tail,5e-11))+np.outer(extra,extra)
    return {'contract':'spike/calibrated-fixture-uq-request/v1','calibration':cal,'fixture':fixture,
            'external_ports':list(cal['port_names']),'dut_ports':[f'board.p{i}' for i in range(n)],
            'covariance':{'basis':input_basis(cal,fixture),'matrix':full.tolist(),
                          'provenance':'SPIKE synthetic shared calibration/fixture mode plus independent component noise v1'}}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    request=json.loads(args.request.read_text(encoding='utf-8')) if args.request else demonstration()
    capture={'source':request,'result':compose_calibrated_fixture(request)}
    with args.output.open('x',encoding='utf-8') as stream:stream.write(json.dumps(capture,indent=2,allow_nan=False)+'\n')
    print('Experimental joint covariance capture retained; measurement and release qualification remain open.')


if __name__=='__main__':main()
