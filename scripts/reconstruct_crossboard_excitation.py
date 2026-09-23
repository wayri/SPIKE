# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Independent direct-Fourier reconstruction; preserves original field result."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from python.spike_core.multi_excitation_network import solve_multi_excitation


def run(case):
    case=Path(case);hashes={}
    def read(name):
        path=case/name
        if not path.is_file() or path.stat().st_size>16*1024**2:raise ValueError("Missing or oversized history")
        blob=path.read_bytes();hashes[name]=hashlib.sha256(blob).hexdigest();return blob
    raw=json.loads(read("field-result.json"));frequency=np.asarray(raw["frequency_hz"])
    if not 2<=len(frequency)<=8193 or raw["reference_impedance_ohm"]!=50:raise ValueError("Unsupported fixture")
    a=np.empty((len(frequency),4,4),complex);b=a.copy()
    for experiment in range(4):
        for port in range(4):
            spectra=[]
            for kind in ("ut","it"):
                values=np.loadtxt(io.BytesIO(read(f"excitation-{experiment}/simulation/port_{kind}_{port+1}")),comments="%")
                if values.ndim!=2 or values.shape[1]!=2 or not 2<=len(values)<=200000 or not np.isfinite(values).all():raise ValueError("Invalid terminal history")
                dt=values[1,0]-values[0,0]
                if dt<=0 or not np.allclose(np.diff(values[:,0]),dt,rtol=1e-7,atol=1e-23):raise ValueError("Nonuniform history")
                # Use recorded E/H timestamps separately, retaining Yee staggering.
                spectra.append(np.array([np.sum(values[:,1]*np.exp(-2j*np.pi*f*values[:,0]))*dt for f in frequency]))
            a[:,port,experiment]=(spectra[0]+50*spectra[1])/2
            b[:,port,experiment]=(spectra[0]-50*spectra[1])/2
    reconstructed,evidence=solve_multi_excitation(a,b)
    diagonal=np.diagonal(a,axis1=1,axis2=2)[:,None,:]
    legacy=b/diagonal;stored=np.asarray(raw["s_real"])+1j*np.asarray(raw["s_imag"])
    off=a.copy()
    for p in range(4):off[:,p,p]=0
    sigma=float(np.linalg.svd(reconstructed,compute_uv=False).max())
    reciprocal=float(abs(reconstructed-reconstructed.transpose(0,2,1)).max())
    for name,digest in hashes.items():
        if hashlib.sha256((case/name).read_bytes()).hexdigest()!=digest:raise ValueError("Evidence changed")
    report={"contract":"spike/crossboard-excitation-reconstruction/v1","artifact_sha256":hashes,
        "legacy_column_reconstruction_max_error":float(abs(legacy-stored).max()),
        "maximum_relative_inactive_incident":float(abs(off/diagonal).max()),
        "maximum_singular_value":sigma,"maximum_reciprocity_absolute_error":reciprocal,
        "screen_passed":sigma<=1.02 and reciprocal<=.02,"thresholds":{"passivity_excess":.02,"reciprocity_absolute":.02},
        "normalization":evidence,"s_real":reconstructed.real.tolist(),"s_imag":reconstructed.imag.tolist(),
        "frequency_hz":frequency.tolist(),"physical_accuracy_qualified":False,
        "scope":"Independent direct Fourier quadrature and full excitation normalization; original field-result untouched."}
    with (case/"excitation-reconstruction.json").open("x",encoding="utf-8") as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    return {k:v for k,v in report.items() if k not in ("artifact_sha256","s_real","s_imag","frequency_hz")}


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("case",type=Path)
    print(json.dumps(run(parser.parse_args().case),indent=2))
