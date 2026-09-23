# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Execute an original analytical RLC channel through the public SI workflow."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.si_workflow import run_si_workflow,REQUEST
from python.spike_core.sparameters import touchstone_text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    sources=[ROOT/"python/spike_core"/name for name in ("si_resonance.py","si_workflow_resonance.py","si_workflow.py","si_impedance.py","sparameters.py")]+[Path(__file__)]
    def hashes():
        return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources}
    before=hashes();f=np.linspace(1e6,100e6,4097);omega=2*np.pi*f
    f0=10e6;q=10.;inductance=1e-6;capacitance=1/((2*np.pi*f0)**2*inductance);resistance=2*np.pi*f0*inductance/q
    z=resistance+1j*(omega*inductance-1/(omega*capacitance))
    matrix=np.zeros((len(f),2,2),complex);matrix[:,0,0]=(z-50)/(z+50)
    request={"contract":REQUEST,"channel":{"kind":"touchstone","name":"analytical-series-rlc.s2p","text":touchstone_text(f,matrix)},
        "sources":[{"port":0}],"receivers":[{"port":1}],"run_time_domain":False,
        "resonance_requests":[{"port":0,"model":"series_rlc","frequency_min_hz":1e6,"frequency_max_hz":100e6}]}
    result=run_si_workflow(request);fit=result["resonance_fits"][0]["fit"]
    if fit["status"]!="qualified_model_fit":
        raise ValueError(str(fit["reasons"]))
    expected={"resonance_hz":f0,"q_factor":q,"resistance_ohm":resistance,"inductance_h":inductance,"capacitance_f":capacitance}
    errors={key:abs(fit["parameters"][key]/value-1)for key,value in expected.items()}
    for name,payload in (("request.json",request),("result.json",result)):
        with (root/name).open("x",encoding="utf-8")as stream:
            json.dump(payload,stream,indent=2,allow_nan=False)
    report={"status":"passed" if max(errors.values())<1e-8 and before==hashes() else "failed",
        "scope":"Analytical single-series-RLC equivalent workflow, not measured PCB resonance qualification",
        "machine":platform.platform(),"python":sys.version,"numpy":np.__version__,"source_sha256":before,"sources_unchanged":before==hashes(),
        "artifact_sha256":{name:hashlib.sha256((root/name).read_bytes()).hexdigest()for name in ("request.json","result.json")},
        "expected":expected,"fit":fit["parameters"],"relative_parameter_errors":errors,"independent_half_power":fit["independent_half_power"],"production_qualified":False}
    with (root/"report.json").open("x",encoding="utf-8")as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report,indent=2));return 0 if report["status"]=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
