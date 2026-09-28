# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Local development CLI for owned Huygens postprocessing, not a field solver."""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.huygens_far_field import huygens_far_field,FarFieldError

LIMIT=8*1024*1024

def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value: raise ValueError("Duplicate JSON key")
        value[key]=item
    return value

def solve(request):
    keys={"contract","bounds_m","divisions","electric_fields","magnetic_fields","directions",
          "frequency_hz","permittivity_f_per_m","permeability_h_per_m","homogeneous_lossless_exterior"}
    try:
        if not isinstance(request,dict) or set(request)!=keys or request["contract"]!="spike/huygens-far-field/v1":
            raise FarFieldError("Expected exact spike/huygens-far-field/v1 input")
        args={key:value for key,value in request.items() if key!="contract"}
        for name in ("electric_fields","magnetic_fields"):
            if not isinstance(args[name],dict): raise FarFieldError("Six face arrays required")
            parsed={}
            for face,value in args[name].items():
                raw=np.asarray(value)
                if raw.ndim!=4 or raw.shape[-2:]!=(3,2) or raw.dtype.kind not in "iuf" or not np.all(np.isfinite(raw)):
                    raise FarFieldError("Fields require finite numeric [nu,nv,xyz,real_imag] arrays")
                parsed[face]=raw[...,0]+1j*raw[...,1]
            args[name]=parsed
        result=huygens_far_field(**args)
        amplitude=result.pop("electric_amplitude_v")
        result["electric_amplitude_v_real_imag"]=np.stack((amplitude.real,amplitude.imag),axis=-1).tolist()
        result["radiation_intensity_w_per_sr"]=result["radiation_intensity_w_per_sr"].tolist()
        return {"contract":"spike/huygens-far-field-result/v1","status":"completed",**result,"issues":[]}
    except (FarFieldError,ValueError,TypeError,OverflowError) as exc:
        return {"contract":"spike/huygens-far-field-result/v1","status":"blocked","production_qualified":False,
                "issues":[{"code":"HUYGENS_INPUT_REJECTED","message":str(exc)}]}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request",required=True);parser.add_argument("--result",required=True)
    args=parser.parse_args()
    source,target=Path(args.request).resolve(),Path(args.result).resolve()
    if source==target or not source.is_file() or source.stat().st_size>LIMIT:
        parser.error("Invalid input/output path or input exceeds8MiB")
    try: request=json.loads(source.read_text(encoding="utf-8"),object_pairs_hook=unique)
    except (ValueError,OSError,UnicodeError) as exc: parser.error(str(exc))
    result=solve(request)
    payload=json.dumps(result,allow_nan=False,separators=(",",":"))
    if len(payload.encode())>LIMIT: parser.error("Output exceeds8MiB")
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_text(payload,encoding="utf-8");os.replace(temporary,target)
    return 0 if result["status"]=="completed" else 2

if __name__=="__main__":raise SystemExit(main())
