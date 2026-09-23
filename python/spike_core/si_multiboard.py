# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Identity-bound two-port board/connector/cable chain, not cross-board fields."""
import hashlib
import json
import math
import re
from collections.abc import Mapping
import numpy as np
from .si_network_workflow import acquire_network,renormalize_waves,cascade_networks
from .sparameters import NetworkData


def model_digest(channel):
    return hashlib.sha256(json.dumps(channel,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def _identity(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}",value):
        raise ValueError("Chain identities must be bounded literal identifiers")
    return value


def _admit(raw):
    if not isinstance(raw,Mapping) or set(raw)!={"kind","segments","reference_impedance_ohm"} or raw["kind"]!="multiboard":
        raise ValueError("Invalid multiboard channel envelope")
    z=raw["reference_impedance_ohm"]
    if type(z) not in (int,float) or not .01<=z<=1e6:
        raise ValueError("Common reference must be finite within .01..1e6 ohm")
    segments=raw["segments"]
    if not isinstance(segments,list) or not 2<=len(segments)<=16:
        raise ValueError("Multiboard chain requires 2..16 segments")
    if len(json.dumps(raw,allow_nan=False).encode("utf-8"))>8*1024**2:
        raise ValueError("Multiboard control envelope exceeds 8 MiB")
    keys={"id","role","owner_id","model_sha256","channel","input_port","output_port","reference_plane_in","reference_plane_out"}
    seen=set();boards=set();previous=None;points=0
    for segment in segments:
        if not isinstance(segment,Mapping) or set(segment)!=keys:
            raise ValueError("Incomplete or unknown segment fields")
        for key in ("id","owner_id","reference_plane_in","reference_plane_out"):_identity(segment[key])
        if segment["id"] in seen or segment["role"] not in ("board","connector","cable"):
            raise ValueError("Duplicate segment identity or unknown role")
        seen.add(segment["id"])
        if segment["role"]=="board":boards.add(segment["owner_id"])
        if type(segment["input_port"]) is not int or type(segment["output_port"]) is not int or {segment["input_port"],segment["output_port"]}!={0,1}:
            raise ValueError("Input/output must specify each two-port index exactly once")
        if segment["reference_plane_in"]==segment["reference_plane_out"] or (previous is not None and previous!=segment["reference_plane_in"]):
            raise ValueError("Adjacent reference-plane identities must match without zero-length identity loops")
        previous=segment["reference_plane_out"]
        channel=segment["channel"]
        if not isinstance(channel,Mapping) or channel.get("kind") not in ("rlgc","touchstone"):
            raise ValueError("Only explicit RLGC or Touchstone segments; no nested chains or inferred geometry")
        if model_digest(channel)!=segment["model_sha256"]:
            raise ValueError("Segment model digest mismatch")
        if channel["kind"]=="rlgc":
            if channel.get("coupled") is not False:
                raise ValueError("Multiboard chain admits explicitly uncoupled two-port RLGC only")
            count=channel.get("frequency_points",1025)
            if type(count) is not int or not 3<=count<=8193:raise ValueError("Invalid segment frequency budget")
            points+=count
    if len(boards)<2:raise ValueError("At least two distinct board owner identities required")
    if points>65536:raise ValueError("Aggregate frequency budget exceeded")
    return segments,float(z)


def build_multiboard_network(raw):
    """Serial chain with explicit reference-plane assertions and model provenance.

    All segments are acquired/admitted before interconnection; frequency grids
    must be exactly equal, without interpolation or inferred de-embedding.
    """
    segments,z=_admit(raw)
    networks=[];points=0;frequencies=None;provenance=[]
    for segment in segments:
        network,_=acquire_network(segment["channel"])
        if network.port_count!=2:raise ValueError("Every segment must have exactly two ports")
        f=np.asarray(network.frequencies_hz)
        points+=len(f)
        if points>65536:raise ValueError("Aggregate frequency budget exceeded")
        if frequencies is None:frequencies=f.copy()
        elif not np.array_equal(f,frequencies):raise ValueError("Segment frequency grids differ")
        order=[segment["input_port"],segment["output_port"]]
        s=network.s_parameters()[:,order][:,:,order]
        s=renormalize_waves(s,network.reference_impedance_ohm[order],z)
        if not np.isfinite(s).all():raise ValueError("Nonfinite normalized chain segment")
        networks.append(NetworkData(f,s,np.repeat(z,2),source=network.source))
        provenance.append({k:v for k,v in segment.items() if k!="channel"})
    total=networks[0]
    for other in networks[1:]:
        total=cascade_networks(total,other)
    identity=model_digest(raw)
    result=NetworkData(frequencies,total.s_parameters(),np.repeat(z,2),source=f"multiboard-chain:{identity}")
    return result,{"contract":"spike/si-multiboard-chain-evidence/v1","segments":provenance,
        "chain_sha256":identity,"reference_impedance_ohm":z,"frequency_points":len(frequencies),
        "aggregate_frequency_points":points,"external_reference_planes":[segments[0]["reference_plane_in"],segments[-1]["reference_plane_out"]],
        "production_qualified":False,"field_coupling_executed":False,
        "limitations":["two-port serial reduced-model chain only; not general N-port graph or coupled pair",
            "plane identities are caller assertions, not CAD reference-plane verification",
            "no inferred connector, return-current, radiation or inter-board electromagnetic coupling"]}
