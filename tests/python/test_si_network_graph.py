# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import copy
import unittest
import numpy as np
from python.spike_core.si_network_graph import build_network_graph
from python.spike_core.si_multiboard import model_digest
from python.spike_core.si_network_workflow import line_network,cascade_networks
from python.spike_core.sparameters import touchstone_text


def graph_fixture(coupled=True):
    count=4 if coupled else 2;half=count//2
    nodes=[]
    for node,length in (("A",.03),("B",.04)):
        channel={"kind":"rlgc","coupled":coupled,"length_m":length,"resistance_ohm_per_m":.2,
            "inductance_h_per_m":250e-9,"capacitance_f_per_m":100e-12,"loss_tangent":.002,
            "inductive_coupling":.1,"capacitive_coupling":.07,"frequency_stop_hz":2e9,"frequency_points":33,
            "reference_impedance_ohm":50.}
        planes=([f"A.in{i}" for i in range(half)]+[f"joint{i}" for i in range(half)] if node=="A" else
                [f"joint{i}" for i in range(half)]+[f"B.out{i}" for i in range(half)])
        nodes.append({"id":node,"owner_id":f"board{node}","channel":channel,
            "model_sha256":model_digest(channel),"reference_planes":planes})
    return {"kind":"network_graph","reference_impedance_ohm":50.,"nodes":nodes,
        "connections":[{"a":{"node_id":"A","port":i+half},"b":{"node_id":"B","port":i}} for i in range(half)],
        "external_ports":[{"id":f"near{i}","node_id":"A","port":i} for i in range(half)]+
            [{"id":f"far{i}","node_id":"B","port":i+half} for i in range(half)]}


class NetworkGraphTests(unittest.TestCase):
    def test_scalar_cascade_equivalence(self):
        raw=graph_fixture(False);actual,_=build_network_graph(raw)
        expected=cascade_networks(*(line_network(v["channel"]) for v in raw["nodes"]))
        np.testing.assert_allclose(actual.parameters,expected.parameters,atol=1e-13)

    def test_coupled_four_port_chain_and_passivity(self):
        raw=graph_fixture();actual,evidence=build_network_graph(raw)
        expected=line_network({**raw["nodes"][0]["channel"],"length_m":.07})
        np.testing.assert_allclose(actual.parameters,expected.parameters,atol=1e-13)
        np.testing.assert_allclose(actual.parameters,actual.parameters.transpose(0,2,1),atol=1e-13)
        self.assertLessEqual(np.linalg.svd(actual.parameters,compute_uv=False).max(),1+1e-12)
        self.assertLess(evidence["maximum_elimination_relative_residual"],1e-12)
        self.assertFalse(evidence["field_coupling_executed"])

    def test_external_permutation(self):
        raw=graph_fixture();a,_=build_network_graph(raw)
        order=[3,0,2,1];raw["external_ports"]=[raw["external_ports"][i] for i in order]
        b,_=build_network_graph(raw)
        np.testing.assert_allclose(b.parameters,a.parameters[:,order][:,:,order],atol=1e-13)

    def test_reference_renormalization_and_schema(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        raw=graph_fixture();expected,_=build_network_graph(raw)
        raw["nodes"][1]["channel"]["reference_impedance_ohm"]=75.
        raw["nodes"][1]["model_sha256"]=model_digest(raw["nodes"][1]["channel"])
        actual,evidence=build_network_graph(raw)
        np.testing.assert_allclose(actual.parameters,expected.parameters,atol=1e-13)
        schema=json.loads((Path(__file__).resolve().parents[2]/"schemas/si-network-graph-v1.schema.json").read_text())
        Draft202012Validator(schema).validate(raw)
        raw["external_ports"][0]["id"]="changed"
        self.assertNotEqual(evidence["external_ports"][0]["id"],"changed")

    def test_zero_coupling_and_ideal_lossless_dc(self):
        raw=graph_fixture()
        for node in raw["nodes"]:
            node["channel"].update(inductive_coupling=0.,capacitive_coupling=0.,loss_tangent=0.,resistance_ohm_per_m=0.)
            node["model_sha256"]=model_digest(node["channel"])
        network,_=build_network_graph(raw)
        np.testing.assert_allclose(network.parameters[:,1,0],0,atol=1e-14)
        np.testing.assert_allclose(network.parameters[:,3,0],0,atol=1e-14)
        delay=.07*np.sqrt(250e-9*100e-12)
        np.testing.assert_allclose(network.parameters[:,2,0],np.exp(-2j*np.pi*network.frequencies_hz*delay),atol=1e-13)

    def test_singular_internal_feedback_rejected(self):
        raw=graph_fixture(False);f=np.linspace(0,2e9,33)
        for node,matrix in zip(raw["nodes"],(np.diag([0.,1.]),np.diag([1.,0.]))):
            channel={"kind":"touchstone","name":"reflector.s2p","text":touchstone_text(f,np.tile(matrix,(len(f),1,1)),50.)}
            node.update(channel=channel,model_sha256=model_digest(channel))
        with self.assertRaisesRegex(ValueError,"feedback"):build_network_graph(raw)

    def test_identity_topology_grid_and_resource_rejections(self):
        variants=[]
        raw=graph_fixture();raw["nodes"][0]["channel"]["kind"]=[];variants.append(raw)
        raw=graph_fixture();raw["connections"].append(copy.deepcopy(raw["connections"][0]));variants.append(raw)
        raw=graph_fixture();raw["nodes"][1]["reference_planes"][0]="wrong";variants.append(raw)
        raw=graph_fixture();raw["nodes"][1]["model_sha256"]="0"*64;variants.append(raw)
        raw=graph_fixture();raw["external_ports"].pop();variants.append(raw)
        raw=graph_fixture();raw["nodes"][1]["channel"]["frequency_points"]=17;raw["nodes"][1]["model_sha256"]=model_digest(raw["nodes"][1]["channel"]);variants.append(raw)
        for raw in variants:
            with self.assertRaises(ValueError):build_network_graph(raw)
        with self.assertRaisesRegex(ValueError,"cancelled"):build_network_graph(graph_fixture(),cancel_check=lambda:True)
