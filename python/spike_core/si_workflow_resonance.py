# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Opt-in, declared single-RLC fits of matched driving-point impedance."""
import numpy as np
from .si_impedance import analyze_impedance
from .si_resonance import fit_single_rlc
from .sparameters import NetworkData


def validate_resonance_requests(raw,port_count=None):
    if not isinstance(raw,list) or len(raw)>16:
        raise ValueError("resonance_requests must contain at most 16 requests")
    seen=set()
    for item in raw:
        if not isinstance(item,dict) or set(item)!={"port","model","frequency_min_hz","frequency_max_hz"}:
            raise ValueError("Resonance request requires exactly port, model and explicit frequency bounds")
        if type(item["port"]) is not int or not 0<=item["port"]<16 or (port_count is not None and item["port"]>=port_count):
            raise ValueError("Resonance port must be a valid zero-based port below 16")
        if item["model"] not in ("series_rlc","parallel_rlc"):
            raise ValueError("Resonance model must be explicitly series_rlc or parallel_rlc")
        for key in ("frequency_min_hz","frequency_max_hz"):
            value=item[key]
            if type(value) not in (float,int) or not 0<value<=1e100:
                raise ValueError("Resonance frequency bounds must be positive finite numbers")
        if item["frequency_min_hz"]>=item["frequency_max_hz"]:
            raise ValueError("Resonance frequency band must have positive width")
        key=tuple(item[k]for k in ("port","model","frequency_min_hz","frequency_max_hz"))
        if key in seen:
            raise ValueError("Duplicate resonance requests are unsupported")
        seen.add(key)
    return raw


def workflow_resonance_reports(network,requests):
    validate_resonance_requests(requests,network.port_count)
    reports=[]
    for item in requests:
        selected=(network.frequencies_hz>=item["frequency_min_hz"])&(network.frequencies_hz<=item["frequency_max_hz"])
        report={"request":dict(item),"termination_definition":"Driving port un-terminated; all OTHER edited-channel ports matched to their real reference impedance. Workflow endpoint/passive loads are NOT applied to this fit."}
        try:
            if np.count_nonzero(selected)<16:
                raise ValueError("Explicit band contains fewer than 16 samples")
            band=NetworkData(network.frequencies_hz[selected],network.s_parameters()[selected],network.reference_impedance_ohm)
            response=analyze_impedance(band,ports=[item["port"]],trace_limit=16384)
            rows=response["ports"][0]["trace"]
            if any(row["status"]!="finite" for row in rows):
                raise ValueError("Explicit band contains open/pole or unresolved impedance; no samples were dropped")
            report["fit"]=fit_single_rlc(band.frequencies_hz,[complex(row["real_ohm"],row["imag_ohm"])for row in rows],model=item["model"])
        except ValueError as exc:
            report["fit"]={"contract":"spike/single-rlc-resonance-fit/v1","status":"not_qualified","model":item["model"],"reasons":[str(exc)],"production_qualified":False,"physical_resonance_qualified":False}
        reports.append(report)
    return reports
