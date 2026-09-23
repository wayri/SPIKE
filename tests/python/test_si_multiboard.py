# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import copy
import unittest
import numpy as np
from python.spike_core.si_multiboard import build_multiboard_network,model_digest
from python.spike_core.si_network_workflow import line_network
from python.spike_core.sparameters import touchstone_text


def fixture():
    segments=[]
    for i,(role,length) in enumerate((("board",.03),("connector",.01),("board",.04))):
        channel={"kind":"rlgc","coupled":False,"length_m":length,"resistance_ohm_per_m":0.,
            "inductance_h_per_m":250e-9,"capacitance_f_per_m":100e-12,"loss_tangent":0.,
            "frequency_stop_hz":4e9,"frequency_points":65,"reference_impedance_ohm":50.}
        segments.append({"id":f"segment{i}","role":role,"owner_id":f"owner{i}","channel":channel,
            "model_sha256":model_digest(channel),"input_port":0,"output_port":1,
            "reference_plane_in":f"plane{i}","reference_plane_out":f"plane{i+1}"})
    return {"kind":"multiboard","segments":segments,"reference_impedance_ohm":50.}


class MultiboardChainTests(unittest.TestCase):
    def test_source_receiver_workflow_process_integration(self):
        from python.spike_core.service import handle
        result = handle({"method": "run_si_workflow", "params": {"request": {
            "contract": "spike/si-workflow-request/v1", "channel": fixture(),
            "run_time_domain": False}}})
        self.assertTrue(result["ok"], result)
        payload = result["result"]
        self.assertEqual(payload["network"]["port_count"], 2)
        self.assertFalse(payload["extraction"]["field_coupling_executed"])
        self.assertEqual(payload["network"]["impedance_response"]["status"], "completed")

    def test_total_length_and_independent_known_delay(self):
        request=fixture();network,evidence=build_multiboard_network(request)
        combined={**request["segments"][0]["channel"],"length_m":.08}
        expected=line_network(combined)
        np.testing.assert_allclose(network.parameters,expected.parameters,atol=1e-13)
        delay=.08*np.sqrt(250e-9*100e-12)
        np.testing.assert_allclose(network.parameters[:,1,0],np.exp(-2j*np.pi*network.frequencies_hz*delay),atol=1e-13)
        self.assertEqual(evidence["aggregate_frequency_points"],195)
        self.assertFalse(evidence["field_coupling_executed"])

    def test_reversed_segment_preserves_symmetric_line(self):
        request=fixture();a,_=build_multiboard_network(request)
        request["segments"][1].update(input_port=1,output_port=0)
        b,_=build_multiboard_network(request)
        np.testing.assert_allclose(a.parameters,b.parameters,atol=1e-13)

    def test_asymmetric_touchstone_orientation_changes_input_reflection(self):
        request=fixture();f=np.linspace(0,4e9,65)
        channel={"kind":"touchstone","name":"connector.s2p","text":touchstone_text(f,
            np.tile(np.array([[.1,.2],[.2,.3]],complex),(len(f),1,1)),50.)}
        request["segments"][1].update(channel=channel,model_sha256=model_digest(channel),input_port=1,output_port=0)
        network,_=build_multiboard_network(request)
        first_delay=.03*np.sqrt(250e-9*100e-12)
        np.testing.assert_allclose(network.parameters[:,0,0],.3*np.exp(-4j*np.pi*f*first_delay),atol=1e-13)

    def test_schema_accepts_example(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[2]/"schemas/si-multiboard-channel-v1.schema.json").read_text())
        Draft202012Validator(schema).validate(fixture())

    def test_digest_identity_grid_and_budget_rejections(self):
        requests=[]
        for key,value in (("id","segment0"),("reference_plane_in","wrong"),("model_sha256","0"*64),("input_port",True)):
            request=fixture();request["segments"][1][key]=value;requests.append(request)
        for key,value in (("frequency_points",33),("coupled",True),("kind","multiboard")):
            request=fixture();channel=request["segments"][1]["channel"];channel[key]=value
            request["segments"][1]["model_sha256"]=model_digest(channel);requests.append(request)
        request=fixture();request["segments"][2]["owner_id"]="owner0";requests.append(request)
        for request in requests:
            with self.assertRaises(ValueError):build_multiboard_network(request)
