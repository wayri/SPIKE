# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Run the analytical board A -> connector -> board B reduced-network example."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tests.python.test_si_multiboard import fixture
from python.spike_core.si_multiboard import build_multiboard_network
from python.spike_core.sparameters import touchstone_text


def run_example(output):
    request=fixture();network,evidence=build_multiboard_network(request)
    expected_delay=.08*np.sqrt(250e-9*100e-12)
    expected=np.exp(-2j*np.pi*network.frequencies_hz*expected_delay)
    error=float(np.max(np.abs(network.parameters[:,1,0]-expected)))
    report={"contract":"spike/si-multiboard-analytical-benchmark/v1","passed":error<1e-12,
        "analytic_delay_s":float(expected_delay),"transmission_complex_max_error":error,
        "maximum_reflection":float(np.max(np.abs(network.parameters[:,0,0]))),"evidence":evidence,
        "production_qualified":False}
    output.mkdir(parents=True,exist_ok=True)
    (output/"channel.json").write_text(json.dumps(request,indent=2)+"\n",encoding="utf-8")
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    (output/"chain.s2p").write_text(touchstone_text(network.frequencies_hz,network.parameters,50.),encoding="ascii")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    report=run_example(parser.parse_args().output)
    print(json.dumps(report,indent=2));raise SystemExit(0 if report["passed"] else 1)
