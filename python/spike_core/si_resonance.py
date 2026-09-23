# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Declared single-RLC fits, independently checked against sampled bandwidth.

Original scaled linear algebra; RLC duality and half-power definitions follow
MIT 6.101: https://web.mit.edu/6.101/www/s2019/handouts/L02_4.pdf
No automatic multi-mode interpretation, physical pole or confidence claim.
"""
import math
import numpy as np


def _fit(frequency, data, model):
    omega=2*np.pi*frequency
    reference=math.sqrt(float(omega[0]))*math.sqrt(float(omega[-1]))
    x=omega/reference
    transformed=data if model=="series_rlc" else 1/data
    columns=np.column_stack((x,-1/x))
    scales=np.linalg.norm(columns,axis=0)
    normalized=columns/scales
    condition=float(np.linalg.cond(normalized))
    if not math.isfinite(condition) or condition>1e6:
        raise ValueError("Ill-conditioned RLC identification band")
    coefficients=np.linalg.lstsq(normalized,transformed.imag,rcond=None)[0]/scales
    resistive=float(np.mean(transformed.real))
    a,b=(float(v)for v in coefficients)
    if not all(math.isfinite(v) and v>0 for v in (resistive,a,b)):
        raise ValueError("Single passive RLC requires positive R, L and C")
    if model=="series_rlc":
        resistance,inductance,capacitance=resistive,a/reference,1/(b*reference)
    else:
        resistance,inductance,capacitance=1/resistive,1/(b*reference),a/reference
    predicted=resistive+1j*(columns@coefficients)
    predicted_z=predicted if model=="series_rlc" else 1/predicted
    resonance=1/(2*np.pi*math.sqrt(inductance)*math.sqrt(capacitance))
    q=(2*np.pi*resonance*inductance/resistance if model=="series_rlc" else 2*np.pi*resonance*resistance*capacitance)
    parameters={"resistance_ohm":resistance,"inductance_h":inductance,"capacitance_f":capacitance,"resonance_hz":resonance,"q_factor":q}
    if not all(math.isfinite(value) and value>0 for value in parameters.values()):
        raise ValueError("Nonfinite single-RLC parameters")
    error=np.abs(predicted_z-data)/np.maximum(np.abs(data),1e-300)
    return parameters,{"maximum_point_relative_error":float(np.max(error)),"relative_l2_error":float(np.linalg.norm(predicted_z-data)/np.linalg.norm(data)),"scaled_condition_number":condition}


def fit_single_rlc(frequencies_hz,impedance_ohm,*,model):
    """Qualify a declared RLC equivalent only when independent grid checks pass.

    Complex impedance samples require the same explicitly loaded driving port.
    DC/pole masks must be removed by an explicit caller-selected positive band,
    not silently filtered here. Thresholds are fixed validation policy.
    """
    if model not in ("series_rlc","parallel_rlc"):
        raise ValueError("Explicit model must be series_rlc or parallel_rlc")
    f=np.asarray(frequencies_hz,dtype=float);z=np.asarray(impedance_ohm,dtype=complex)
    if f.ndim!=1 or z.shape!=f.shape or not 16<=len(f)<=16384 or not np.all(np.isfinite(f)) or np.any(f<=0) or np.any(np.diff(f)<=0):
        raise ValueError("Require 16..16384 positive ordered frequency/impedance pairs")
    if not np.all(np.isfinite(z)) or np.any(np.abs(z)<1e-100) or np.max(np.abs(z))>1e100:
        raise ValueError("Finite nonzero bounded complex impedance required")
    if f[0]<1e-100 or f[-1]>1e100 or f[-1]/f[0]>1e12:
        raise ValueError("Frequency scaling outside bounded fit scope")
    report={"contract":"spike/single-rlc-resonance-fit/v1","model":model,"status":"not_qualified",
        "qualification_scope":"Declared single-RLC equivalent over supplied impedance band only",
        "production_qualified":False,"physical_resonance_qualified":False,"reasons":[],
        "limits":{"maximum_point_relative_error":.01,"split_parameter_relative_change":.05,"half_power_relative_agreement":.05,"minimum_samples_inside_bandwidth":12},
        "limitations":["No multi-mode fit, parasitic topology identification, source-independent physical pole or measured correlation claim.",
            "Split-band sensitivity is not a statistical confidence interval; frequency samples may be correlated.",
            "Q is under ideal voltage drive for series RLC, ideal current drive for parallel RLC; additional loading changes Q."]}
    try:
        fit,diagnostics=_fit(f,z,model)
    except (ValueError,np.linalg.LinAlgError,FloatingPointError) as exc:
        report["reasons"].append(str(exc));return report
    report["candidate_parameters"]=fit;report["fit_diagnostics"]=diagnostics
    if diagnostics["maximum_point_relative_error"]>.01:
        report["reasons"].append("Complex impedance samples do not fit one passive RLC within 1% at every point")
    midpoint=len(f)//2
    try:
        halves=[_fit(f[:midpoint],z[:midpoint],model)[0],_fit(f[midpoint:],z[midpoint:],model)[0]]
        variation={key:max(abs(part[key]/fit[key]-1)for part in halves)for key in fit}
        report["split_band_sensitivity"]=variation
        if max(variation.values())>.05:
            report["reasons"].append("Separate lower/upper-band fits vary by more than 5%")
    except (ValueError,np.linalg.LinAlgError,FloatingPointError):
        report["reasons"].append("Separate lower/upper-band identification is unsupported or ill-conditioned")
    # Independent measured response: current power under fixed voltage for
    # series, voltage power under fixed current for parallel. Normalize before
    # squaring to avoid range overflow. No fitted R/L/C used for crossings.
    magnitude=np.abs(z)
    amplitude=np.min(magnitude)/magnitude if model=="series_rlc" else magnitude/np.max(magnitude)
    power=amplitude*amplitude
    peak=int(np.argmax(power));crossings=[]
    for i in range(len(f)-1):
        if (power[i]-.5)*(power[i+1]-.5)<0 or power[i]==.5:
            fraction=(.5-power[i])/(power[i+1]-power[i]) if power[i+1]!=power[i] else 0
            crossings.append((float(f[i]+fraction*(f[i+1]-f[i])),i))
    if len(crossings)!=2 or not crossings[0][0]<f[peak]<crossings[1][0]:
        report["reasons"].append("Band must contain exactly two resolved measured half-power crossings around one peak")
    else:
        low,high=(row[0]for row in crossings);bandwidth=high-low
        measured_f0=math.sqrt(low)*math.sqrt(high);measured_q=measured_f0/bandwidth
        inside=int(np.sum((f>low)&(f<high)))
        spacing=max(float(f[i+1]-f[i])for _,i in crossings)
        agreement={"resonance_relative_error":abs(measured_f0/fit["resonance_hz"]-1),"q_relative_error":abs(measured_q/fit["q_factor"]-1)}
        report["independent_half_power"]={"lower_hz":low,"upper_hz":high,"resonance_hz":measured_f0,"q_factor":measured_q,
            "samples_inside_bandwidth":inside,"largest_crossing_interval_hz":spacing,**agreement}
        if inside<12 or spacing>bandwidth/10:
            report["reasons"].append("Frequency grid does not resolve the measured bandwidth")
        if max(agreement.values())>.05:
            report["reasons"].append("Independent sampled half-power f0/Q disagrees with fit by more than 5%")
    if not report["reasons"]:
        report["status"]="qualified_model_fit"
        report["parameters"]=fit
    return report
