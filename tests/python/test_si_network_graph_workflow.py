# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Graph acquisition through the complete loaded SI workflow and local schema."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from jsonschema import Draft202012Validator
from referencing import Registry,Resource
from python.spike_core.si_workflow import REQUEST,run_si_workflow
from python.spike_core.si_network_graph import build_network_graph
from python.spike_core.si_crosstalk import analyze_crosstalk
from tests.python.test_si_network_graph import graph_fixture

ROOT=Path(__file__).resolve().parents[2]


def workflow_request(channel):
    return {"contract":REQUEST,"channel":copy.deepcopy(channel),
        "sources":[{"port":0,"resistance_ohm":50.,"capacitance_f":0.,"low_v":0.,"high_v":1.,"rise_time_s":0.,"fall_time_s":0.}],
        "receivers":[{"port":p,"resistance_ohm":50.,"capacitance_f":0.} for p in (1,2,3)],
        "bit_rate_hz":253906250.,"bit_count":128,"run_time_domain":True}


def local_validator():
    resources=[]
    for path in (ROOT/"schemas").glob("*.json"):
        schema=json.loads(path.read_text(encoding="utf-8"))
        if "$id" in schema and "$schema" in schema:
            resources.append((schema["$id"],Resource.from_contents(schema)))
    schema=json.loads((ROOT/"schemas/si-workflow-request-v1.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema,registry=Registry().with_resources(resources))


def compare_workflows(channel=None):
    channel=channel or graph_fixture()
    request=workflow_request(channel);local_validator().validate(request)
    graph=run_si_workflow(request)
    equivalent={**channel["nodes"][0]["channel"],"length_m":.07}
    single=run_si_workflow(workflow_request(equivalent))
    transfer_error=max(float(np.max(np.abs(np.array([complex(v["real"],v["imag"]) for v in a["trace"]])-
        np.array([complex(v["real"],v["imag"]) for v in b["trace"]])))) for a,b in zip(graph["loaded_transfers"],single["loaded_transfers"]))
    waveform_error=max(float(np.max(np.abs(np.array([v["voltage_v"] for v in a["waveform"]])-
        np.array([v["voltage_v"] for v in b["waveform"]])))) for a,b in zip(graph["time_domain"]["receivers"],single["time_domain"]["receivers"]))
    noise_error=float(np.max(np.abs(np.asarray(graph["noise"]["thermal_rms_v_by_port"])-single["noise"]["thermal_rms_v_by_port"])))
    return request,graph,{"graph_status":graph["status"],"equivalent_status":single["status"],
        "loaded_transfer_max_error":transfer_error,"prbs_waveform_max_error_v":waveform_error,
        "thermal_noise_max_error_v":noise_error,"production_qualified":False}


class NetworkGraphWorkflowTests(unittest.TestCase):
    def test_schema_and_complete_workflow_equivalence(self):
        _,graph,metrics=compare_workflows()
        self.assertEqual(graph["status"],"completed")
        self.assertEqual(graph["time_domain"]["status"],"completed")
        self.assertLess(metrics["loaded_transfer_max_error"],1e-12)
        self.assertLess(metrics["prbs_waveform_max_error_v"],1e-12)
        self.assertLess(metrics["thermal_noise_max_error_v"],1e-15)
        self.assertEqual(graph["extraction"]["contract"],"spike/si-network-graph-evidence/v1")

    def test_standalone_loaded_response_matches_full_workflow(self):
        raw=graph_fixture();network,_=build_network_graph(raw)
        standalone=analyze_crosstalk(network,port_map={"aggressor_near":0,"victim_near":1,"aggressor_far":2,"victim_far":3},termination_ohm=[50.]*4)
        result=run_si_workflow(workflow_request(raw))
        for label,port in (("next",1),("fext",3)):
            a=standalone["frequency_response"][label]["trace"]
            b=next(v for v in result["loaded_transfers"] if v["observed_port"]==port)["trace"]
            np.testing.assert_allclose([complex(v["real"],v["imag"]) for v in a],
                [complex(v["real"],v["imag"]) for v in b],atol=1e-13)

    def test_budget_and_nonfinite_reject_before_acquisition(self):
        for value in (float("nan"),float("inf"),-1.,True):
            raw=graph_fixture();raw["reference_impedance_ohm"]=value
            with patch("python.spike_core.si_network_graph.acquire_network") as acquire:
                with self.assertRaises(ValueError):build_network_graph(raw)
                acquire.assert_not_called()
        with patch("python.spike_core.si_network_graph.MAX_DENSE_WORK",1),patch("python.spike_core.si_network_graph.acquire_network") as acquire:
            with self.assertRaisesRegex(ValueError,"budget"):build_network_graph(graph_fixture())
            acquire.assert_not_called()
