# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Illustrative matched/unequal-load timings, not an equivalent-work speedup."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.si_impedance import analyze_impedance
from python.spike_core.sparameters import NetworkData


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be new")
    source = ROOT / "python/spike_core/si_impedance.py"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    f = np.linspace(0, 8e9, 1025)
    matrix = np.array([[0,.05,.6,.02],[.05,0,.02,.6],[.6,.02,0,.05],[.02,.6,.05,0]])
    s = np.exp(-2j*np.pi*f*1e-9)[:,None,None]*matrix
    network = NetworkData(f,s,np.ones(4)*50)
    report = {"frequency_count":len(f),"port_count":4,"warmups":1,"measured_runs":5,
        "python":sys.version,"machine":platform.platform(),"numpy":np.__version__,"source_sha256":before,"cases":{},
        "limitation":"Different physical loads require different arithmetic; timings are illustrative, not a general solver speedup or regression gate."}
    for label, loads in (("matched",None),("unequal_loads",[25,75,100,40])):
        analyze_impedance(network,termination_ohm=loads)
        elapsed=[]
        for _ in range(5):
            start=time.perf_counter()
            result=analyze_impedance(network,termination_ohm=loads)
            elapsed.append(time.perf_counter()-start)
        report["cases"][label]={"median_seconds":statistics.median(elapsed),"samples_seconds":elapsed,"status":result["status"]}
    report["source_unchanged"] = before == hashlib.sha256(source.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report,indent=2))
    return 0 if report["source_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
