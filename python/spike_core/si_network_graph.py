# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Bounded wave-coordinate graph elimination with explicit terminal identities.

For ideal paired internal ports a_i=C b_i, where C swaps each pair. Eliminating
internal incident waves gives S_ee+S_ei solve(I-C S_ii,C S_ie). The connection
is an ideal zero-length bond at an explicitly common reference plane; physical
connectors and distributed returns must already be included in leaf models.
"""
from collections.abc import Mapping
import json
import copy
import numpy as np
from .si_multiboard import model_digest,_identity
from .si_network_workflow import acquire_network,renormalize_waves
from .sparameters import NetworkData

MAX_DENSE_WORK=200_000_000
MAX_NUMERIC_ENTRIES=4_000_000


def _record(raw,keys,label):
    if not isinstance(raw,Mapping) or set(raw)!=set(keys):raise ValueError(f"Invalid {label} fields")


def build_network_graph(raw, *, cancel_check=None):
    _record(raw,{"kind","reference_impedance_ohm","nodes","connections","external_ports"},"graph")
    if raw["kind"]!="network_graph":raise ValueError("Expected network_graph kind")
    if len(json.dumps(raw,allow_nan=False).encode("utf-8"))>8*1024**2:raise ValueError("Graph control exceeds 8 MiB")
    reference=raw["reference_impedance_ohm"]
    if type(reference) not in (int,float) or not .01<=reference<=1e6:raise ValueError("Invalid shared real reference impedance")
    nodes=raw["nodes"];connections=raw["connections"];external=raw["external_ports"]
    if not isinstance(nodes,list) or not 1<=len(nodes)<=16:raise ValueError("Graph requires 1..16 leaf nodes")
    if not isinstance(connections,list) or len(connections)>31:raise ValueError("Too many paired connections")
    if not isinstance(external,list) or not 2<=len(external)<=16:raise ValueError("Graph requires 2..16 external ports")
    ids=set();total=0;lookup={};planes={};metadata=[]
    # Admit identities and graph topology before any matrix-exponential work.
    for node in nodes:
        _record(node,{"id","owner_id","model_sha256","channel","reference_planes"},"leaf")
        name=_identity(node["id"]);_identity(node["owner_id"])
        if name in ids:raise ValueError("Duplicate leaf identity")
        ids.add(name)
        channel=node["channel"]
        if not isinstance(channel,Mapping) or channel.get("kind") not in ("rlgc","touchstone"):raise ValueError("Only RLGC/Touchstone leaves are admitted")
        if node["model_sha256"]!=model_digest(channel):raise ValueError("Leaf model digest mismatch")
        refs=node["reference_planes"]
        if not isinstance(refs,list) or not 2<=len(refs)<=16:raise ValueError("Explicit reference plane required for each leaf port")
        for port,plane in enumerate(refs):
            _identity(plane);lookup[(name,port)]=total+port;planes[(name,port)]=plane
        total+=len(refs)
        if total>64:raise ValueError("Graph exceeds 64 total ports")
        if channel["kind"]=="rlgc":
            coupled=channel.get("coupled",True)
            if type(coupled) is not bool or len(refs)!=(4 if coupled else 2):raise ValueError("RLGC reference-plane count mismatch")
        metadata.append(copy.deepcopy({k:v for k,v in node.items() if k!="channel"}))
    def endpoint(value):
        _record(value,{"node_id","port"},"endpoint")
        if type(value["port"]) is not int or not isinstance(value["node_id"],str):raise ValueError("Endpoint needs literal node identity and integer zero-based port")
        key=(value["node_id"],value["port"])
        if key not in lookup:raise ValueError("Unknown graph terminal")
        return key
    used=set();internal=[];pairs=[]
    for connection in connections:
        _record(connection,{"a","b"},"connection")
        a=endpoint(connection["a"]);b=endpoint(connection["b"])
        if a==b or a in used or b in used:raise ValueError("Connection reuses a terminal")
        if planes[a]!=planes[b]:raise ValueError("Connected terminal reference planes differ")
        used.update((a,b));pairs.append((len(internal),len(internal)+1));internal.extend((lookup[a],lookup[b]))
    output=[];output_ids=set()
    for port in external:
        _record(port,{"id","node_id","port"},"external port")
        _identity(port["id"])
        if port["id"] in output_ids:raise ValueError("Duplicate external port identity")
        output_ids.add(port["id"]);key=endpoint({"node_id":port["node_id"],"port":port["port"]})
        if key in used:raise ValueError("External terminal already consumed")
        used.add(key);output.append(lookup[key])
    if len(used)!=total:raise ValueError("Every leaf port must be explicitly external or connected")
    acquired=[];frequencies=None;entries=0;offset=0
    for node in nodes:
        if cancel_check and cancel_check():raise ValueError("Network graph cancelled")
        # Preflight RLGC matrix-work before acquisition. Touchstone is parsed,
        # not solved; its actual dimensions are checked immediately afterwards.
        channel=node["channel"]
        if channel["kind"]=="rlgc":
            count=channel.get("frequency_points",1025)
            if type(count) is not int or not 3<=count<=8193 or count*total**3>MAX_DENSE_WORK:raise ValueError("Graph dense work budget exceeded")
        network,_=acquire_network(channel)
        count=len(network.frequencies_hz);ports=network.port_count
        if ports!=len(node["reference_planes"]):raise ValueError("Leaf port count differs from declared planes")
        entries+=count*ports**2
        if count>8193 or count*total**3>MAX_DENSE_WORK or entries>MAX_NUMERIC_ENTRIES:raise ValueError("Graph numerical resource budget exceeded")
        if frequencies is None:frequencies=network.frequencies_hz.copy()
        elif not np.array_equal(frequencies,network.frequencies_hz):raise ValueError("Graph frequency grids differ; interpolation is not inferred")
        matrices=renormalize_waves(network.s_parameters(),network.reference_impedance_ohm,reference)
        if not np.isfinite(matrices).all():raise ValueError("Nonfinite normalized leaf")
        acquired.append((offset,ports,matrices));offset+=ports
    c=np.zeros((len(internal),len(internal)))
    for a,b in pairs:c[a,b]=c[b,a]=1
    result=np.empty((len(frequencies),len(output),len(output)),complex)
    worst_condition=1.;worst_residual=0.
    for index in range(len(frequencies)):
        if cancel_check and cancel_check():raise ValueError("Network graph cancelled")
        s=np.zeros((total,total),complex)
        for offset,ports,matrices in acquired:s[offset:offset+ports,offset:offset+ports]=matrices[index]
        reduced=s[np.ix_(output,output)]
        if internal:
            system=np.eye(len(internal))-c@s[np.ix_(internal,internal)]
            rhs=c@s[np.ix_(internal,output)]
            condition=float(np.linalg.cond(system));worst_condition=max(worst_condition,condition)
            if not np.isfinite(condition) or condition>1e12:raise ValueError("Singular or ill-conditioned internal graph feedback")
            solved=np.linalg.solve(system,rhs)
            residual=float(np.linalg.norm(system@solved-rhs)/max(np.linalg.norm(rhs),1e-30));worst_residual=max(worst_residual,residual)
            if residual>1e-10:raise ValueError("Internal graph elimination residual failed")
            reduced=reduced+s[np.ix_(output,internal)]@solved
        if not np.isfinite(reduced).all():raise ValueError("Nonfinite graph response")
        result[index]=reduced
    digest=model_digest(raw)
    return NetworkData(frequencies,result,np.repeat(reference,len(output)),source=f"network-graph:{digest}"),{
        "contract":"spike/si-network-graph-evidence/v1","graph_sha256":digest,"nodes":metadata,
        "connections":copy.deepcopy(connections),"external_ports":copy.deepcopy(external),"reference_impedance_ohm":reference,
        "total_ports":total,"frequency_points":len(frequencies),"numeric_entries":entries,
        "maximum_feedback_condition":worst_condition,"maximum_elimination_relative_residual":worst_residual,
        "production_qualified":False,"field_coupling_executed":False,
        "limitations":["ideal paired zero-length port bonds; connectors/return paths belong in leaf models",
            "reference-plane identities are explicit assertions, not CAD verification",
            "no inferred junctions, nonlinear devices, grid interpolation or field coupling"]}
