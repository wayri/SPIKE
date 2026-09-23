# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Immutable full-workflow evidence from the executed graph crosstalk example."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tests.python.test_si_network_graph_workflow import compare_workflows


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source,output):
    inputs=[source/"channel.json",source/"loaded-example.json"]
    paths=sorted((ROOT/"python/spike_core").glob("*.py"))+sorted((ROOT/"schemas").glob("*.json"))
    paths += [Path(__file__).resolve(),ROOT/"tests/python/test_si_network_graph_workflow.py"]
    before={str(p.relative_to(ROOT)):digest(p) for p in paths}
    input_hashes={p.name:digest(p) for p in inputs}
    channel=json.loads(inputs[0].read_text(encoding="utf-8"))
    loaded=json.loads(inputs[1].read_text(encoding="utf-8"))
    if loaded["termination_ohm"] != [50.]*4:
        raise ValueError("This fixture requires four 50-ohm terminations")
    request,result,summary=compare_workflows(channel)
    errors={}
    for label,port in (("next",1),("fext",3)):
        actual=next(x for x in result["loaded_transfers"] if x["observed_port"]==port)["trace"]
        expected=loaded["frequency_response"][label]["trace"]
        if [x["frequency_hz"] for x in actual] != [x["frequency_hz"] for x in expected]:
            raise ValueError("Frequency grids differ")
        errors[label]=float(np.max(np.abs(np.asarray([complex(x["real"],x["imag"]) for x in actual])-
            np.asarray([complex(x["real"],x["imag"]) for x in expected]))))
    after={str(p.relative_to(ROOT)):digest(p) for p in paths}
    stable=before==after and input_hashes=={p.name:digest(p) for p in inputs}
    summary.update({"contract":"spike/si-network-graph-workflow-benchmark/v1",
        "loaded_example_transfer_max_errors":errors,"source_unchanged":stable,
        "input_sha256":input_hashes,"source_sha256":before,
        "scope":"Same graph and loading as standalone custom-pulse example; full workflow uses PRBS, not replay of the custom pulse.",
        "passed":stable and result["status"]=="completed" and result["time_domain"]["status"]=="completed"
            and max(errors.values())<1e-12 and summary["loaded_transfer_max_error"]<1e-12
            and summary["prbs_waveform_max_error_v"]<1e-12 and summary["thermal_noise_max_error_v"]<1e-15})
    output.mkdir(parents=True,exist_ok=False)
    for name,data in (("request.json",request),("result.json",result)):
        (output/name).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    summary["artifact_sha256"]={name:digest(output/name) for name in ("request.json","result.json")}
    (output/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return {k:v for k,v in summary.items() if k!="source_sha256"}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    report=run(**vars(parser.parse_args()))
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report["passed"] else 1)
