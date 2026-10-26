# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Recover scattering matrices from independent incident/reflected wave runs.

Columns are experiments, rows are ports, and B=S A. No matched inactive-port
assumption, symmetry alteration, passivity projection or causality repair occurs.
Wave coordinates must share a consistent real reference and polarity per port.
"""
import numpy as np


def solve_multi_excitation(incident,reflected, *, condition_limit=1e10,residual_limit=1e-10):
    """Return (S,evidence) for finite [frequency,port,experiment] square batches."""
    for value,low,high in ((condition_limit,1.,1e12),(residual_limit,1e-15,1e-3)):
        if type(value) not in (int,float) or not np.isfinite(value) or not low<=value<=high:
            raise ValueError("Invalid multi-excitation admission threshold")
    a=np.asarray(incident,dtype=complex);b=np.asarray(reflected,dtype=complex)
    if a.ndim!=3 or a.shape!=b.shape or a.shape[1]!=a.shape[2] or not 1<=a.shape[0]<=8193 or not 2<=a.shape[1]<=16:
        raise ValueError("Expected bounded square frequency-port-experiment batches")
    if a.shape[0]*a.shape[1]**3>100_000_000 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Nonfinite waves or numerical work budget exceeded")
    condition=np.linalg.cond(a)
    if not np.isfinite(condition).all() or np.any(condition>condition_limit):
        raise ValueError("Independent incident excitations are rank deficient or ill conditioned")
    # Transpose, not conjugate transpose: solve A.T S.T=B.T for each frequency.
    s=np.linalg.solve(a.transpose(0,2,1),b.transpose(0,2,1)).transpose(0,2,1)
    norm=np.linalg.norm(b,axis=(1,2))
    residual=np.linalg.norm(s@a-b,axis=(1,2))/np.maximum(norm,np.finfo(float).tiny)
    if not np.isfinite(s).all() or not np.isfinite(residual).all() or np.any(residual>residual_limit):
        raise ValueError("Multi-excitation reconstruction residual failed")
    return s,{"contract":"spike/multi-excitation-normalization/v1","frequency_count":a.shape[0],
        "port_count":a.shape[1],"maximum_incident_condition":float(condition.max()),
        "maximum_relative_residual":float(residual.max()),"condition_limit":float(condition_limit),
        "residual_limit":float(residual_limit),"passivity_enforced":False,"reciprocity_enforced":False,
        "physical_accuracy_qualified":False}
