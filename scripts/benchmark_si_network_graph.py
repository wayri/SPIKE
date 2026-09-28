# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Execute a coupled board-A -> board-B wave-network graph example."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tests.python.test_si_network_graph import graph_fixture
from python.spike_core.si_network_graph import build_network_graph
from python.spike_core.si_network_workflow import line_network
from python.spike_core.si_crosstalk import analyze_crosstalk
from python.spike_core.sparameters import touchstone_text


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    raw=graph_fixture();network,evidence=build_network_graph(raw)
    expected=line_network({**raw["nodes"][0]["channel"],"length_m":.07})
    error=float(np.max(np.abs(network.parameters-expected.parameters)))
    reciprocity=float(np.max(np.abs(network.parameters-network.parameters.transpose(0,2,1))))
    singular=float(np.max(np.linalg.svd(network.parameters,compute_uv=False)))
    loaded=analyze_crosstalk(network,port_map={"aggressor_near":0,"victim_near":1,"aggressor_far":2,"victim_far":3},
        termination_ohm=[50.]*4,waveform_v=[0.]*16+[1.]*32+[0.]*32)
    report={"contract":"spike/si-network-graph-benchmark/v1","passed":error<1e-12 and reciprocity<1e-12 and singular<=1+1e-12,
        "equivalent_coupled_line_max_error":error,"reciprocity_max_error":reciprocity,
        "maximum_singular_value":singular,"evidence":evidence,"production_qualified":False}
    for name,data in (("channel.json",raw),("report.json",report),("loaded-example.json",loaded)):
        (output/name).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    (output/"graph.s4p").write_text(touchstone_text(network.frequencies_hz,network.parameters,50.),encoding="ascii")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True,type=Path)
    result=run(parser.parse_args().output);print(json.dumps(result,indent=2));raise SystemExit(0 if result["passed"] else 1)
