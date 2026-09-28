# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent modal circuit checks for the bounded two-line SI implementation.

No field-extraction or measured-coupon qualification is inferred from these
analytical network and discrete-convolution comparisons.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from python.spike_core.si_coupled_channel import multiconductor_rlgc_network,crosstalk_report
from python.spike_core.si_channel import _fft_convolve_prefix
from python.spike_core.si_workflow import _loaded_response
from python.spike_core.si_crosstalk import analyze_crosstalk


def line_fixture(coupled=True):
    c=np.array([[120.,-20.],[-20.,120.]])*1e-12 if coupled else np.eye(2)*120e-12
    # Homogeneous medium LC=1/v^2 I; both propagation velocities are equal.
    inductance=np.linalg.inv(c)/(1.7e8)**2
    return {"geometry":{"length_m":.075,"design_id":"analytic-two-line"},
            "geometry_digest":"analytic-fixture", "rlgc_per_m":{
                "resistance_ohm_per_m":(np.eye(2)*.3).tolist(),
                "inductance_h_per_m":inductance.tolist(),"capacitance_f_per_m":c.tolist(),
                "loss_tangent":.003}}


def independent_modal_s(extraction,frequencies,zref=50.):
    """Even/odd scalar transmission-line ABCD oracle, no matrix exponential."""
    q=np.array([[1.,1.],[1.,-1.]])/np.sqrt(2)
    transform=np.zeros((4,4));transform[:2,:2]=q;transform[2:,2:]=q
    raw=extraction["rlgc_per_m"]
    modes=[np.diag(q.T@np.asarray(raw[k])@q) for k in (
        "resistance_ohm_per_m","inductance_h_per_m","capacitance_f_per_m")]
    length=extraction["geometry"]["length_m"]
    results=[]
    for frequency in frequencies:
        matrix=np.zeros((4,4),complex)
        for mode in range(2):
            omega=2*np.pi*frequency
            z=modes[0][mode]+1j*omega*modes[1][mode]
            y=omega*(raw["loss_tangent"]+1j)*modes[2][mode]
            if frequency==0:
                a,d,b,c=1.,1.,z*length,0.
            else:
                gamma=np.sqrt(z*y);zc=np.sqrt(z/y)
                a=d=np.cosh(gamma*length)
                b=zc*np.sinh(gamma*length);c=np.sinh(gamma*length)/zc
            den=a+b/zref+c*zref+d
            refl=(a+b/zref-c*zref-d)/den
            matrix[mode,mode]=matrix[mode+2,mode+2]=refl
            matrix[mode,mode+2]=matrix[mode+2,mode]=2/den
        results.append(transform@matrix@transform.T)
    return np.asarray(results)


def run_benchmarks():
    frequencies=np.linspace(0,2e9,129)
    records={}
    for coupled in (False,True):
        fixture=line_fixture(coupled)
        network=multiconductor_rlgc_network(fixture,frequencies,50.)
        actual=network.s_parameters();expected=independent_modal_s(fixture,frequencies)
        transfer,_,_=_loaded_response(network,np.ones((len(frequencies),4))/50,
            np.broadcast_to(np.array([[1/50],[0],[0],[0]]),(len(frequencies),4,1)),
            25.,np.zeros((len(frequencies),4)))
        expected_loaded=(actual[:,:,0]+np.array([1,0,0,0]))/2
        records["coupled" if coupled else "uncoupled"]={
            "modal_oracle_max_error":float(np.max(np.abs(actual-expected))),
            "reciprocity_max_error":float(np.max(np.abs(actual-actual.transpose(0,2,1)))),
            "maximum_singular_value":float(np.max(np.linalg.svd(actual,compute_uv=False))),
            "matched_loaded_voltage_error":float(np.max(np.abs(transfer[:,:,0]-expected_loaded))),
            "next_max_magnitude":float(np.max(np.abs(actual[:,1,0]))),
            "fext_max_magnitude":float(np.max(np.abs(actual[:,3,0])))}
    wave=np.tile([0.,1.,1.,0.,1.,0.,0.],31)
    impulse=np.array([.0,.2,-.1,.03,.0,.005])
    records["independent_discrete_convolution_error"]=float(np.max(np.abs(
        _fft_convolve_prefix(wave,impulse)-np.convolve(wave,impulse)[:len(wave)])))
    # Exercise the complete report using a direct Fourier sum and direct FIR sum.
    model_s=independent_modal_s(line_fixture(),frequencies)
    loaded=analyze_crosstalk(network,port_map={"aggressor_near":0,"victim_near":1,
        "aggressor_far":2,"victim_far":3},termination_ohm=[50.]*4,waveform_v=wave.tolist())
    count=2*len(frequencies)-1
    harmonic=np.exp(2j*np.pi*np.outer(np.arange(count),np.arange(1,len(frequencies)))/count)
    errors=[]
    for name,port in (("next",1),("fext",3)):
        h=model_s[:,port,0]/2
        impulse=(h[0].real+2*np.real(harmonic@h[1:]))/count
        expected=np.convolve(wave,impulse)[:len(wave)]
        errors.append(float(np.max(np.abs(expected-loaded["time_domain"][f"{name}_v"]))))
    records["loaded_report_independent_transient_error"]=max(errors)
    passed=all(v["modal_oracle_max_error"]<1e-10 and v["reciprocity_max_error"]<1e-10
        and v["maximum_singular_value"]<=1+1e-10 and v["matched_loaded_voltage_error"]<1e-12
        for v in (records["coupled"],records["uncoupled"]))
    passed &= records["uncoupled"]["next_max_magnitude"]<1e-12 and records["uncoupled"]["fext_max_magnitude"]<1e-12
    passed &= records["independent_discrete_convolution_error"]<1e-12
    passed &= records["loaded_report_independent_transient_error"]<1e-11
    return {"contract":"spike/si-crosstalk-analytical-benchmark/v1","passed":bool(passed),
            "port_order":["aggressor.near","victim.near","aggressor.far","victim.far"],
            "metrics":records,"production_qualified":False,
            "limitations":["network oracle uses synthetic RLGC, not geometry extraction",
                "equal scalar terminations are not even/odd modal matches",
                "convolution comparison validates discrete arithmetic, not continuous-time bandwidth sufficiency"]}


def loaded_example():
    frequencies=np.linspace(0,8e9,513)
    network=multiconductor_rlgc_network(line_fixture(),frequencies,50.)
    dt=1/((2*len(frequencies)-1)*(frequencies[1]-frequencies[0]))
    time=np.arange(512)*dt
    # Explicit finite-rise 1 V pulse, 0.5 ns 0-100% edges, 4 ns plateau.
    wave=np.minimum(np.clip((time-2e-9)/.5e-9,0,1),np.clip((6.5e-9-time)/.5e-9,0,1))
    return analyze_crosstalk(network,port_map={"aggressor_near":0,"victim_near":1,
        "aggressor_far":2,"victim_far":3},termination_ohm=[50.]*4,waveform_v=wave.tolist())


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path)
    parser.add_argument("--example-output",type=Path);parser.add_argument("--plot-output",type=Path)
    args=parser.parse_args();report=run_benchmarks()
    payload=json.dumps(report,indent=2,allow_nan=False)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(payload,encoding="utf-8")
    if args.example_output or args.plot_output:
        example=loaded_example()
        if args.example_output:
            args.example_output.parent.mkdir(parents=True,exist_ok=True)
            args.example_output.write_text(json.dumps(example,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        if args.plot_output:
            if args.plot_output.suffix.lower()!=".svg":
                raise ValueError("Dependency-free plot output must have .svg extension")
            samples=example["time_domain"];time=np.asarray(samples["time_s"])*1e9
            next_v=np.asarray(samples["next_v"])*1e3;fext_v=np.asarray(samples["fext_v"])*1e3
            scale=max(np.max(np.abs(next_v)),np.max(np.abs(fext_v)),1e-12)
            parts=['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="480" viewBox="0 0 900 480">',
                '<rect width="900" height="480" fill="white"/>',
                '<g font-family="sans-serif" font-size="14" fill="#17202a">',
                '<text x="60" y="25">Synthetic RLGC: loaded NEXT/FEXT, 50-ohm terminations</text>',
                '<text x="60" y="48">Finite-band circuit reference; not measured or field-qualified</text>',
                '<text x="60" y="78">Thevenin source, 0 to 1 V</text>',
                f'<text x="60" y="235">Victim voltage, +/- {scale:.5g} mV</text>',
                '<text x="630" y="235" fill="#145a32">NEXT</text><text x="710" y="235" fill="#b03a2e">FEXT</text>',
                f'<text x="60" y="455">0 ns</text><text x="750" y="455">{time[-1]:.5g} ns</text>',
                '<path d="M60 90V200H840 M60 255V435H840 M60 345H840" fill="none" stroke="#aaa"/>']
            for values,base,height,color in ((np.asarray(samples["source_v"]),200,110,"#1f618d"),
                    (next_v/scale,345,85,"#145a32"),(fext_v/scale,345,85,"#b03a2e")):
                points=" ".join(f"{60+780*t/time[-1]:.4f},{base-height*v:.4f}" for t,v in zip(time,values))
                parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.5"/>')
            parts.append('</g></svg>')
            args.plot_output.parent.mkdir(parents=True,exist_ok=True)
            args.plot_output.write_text("\n".join(parts)+"\n",encoding="utf-8")
    print(payload,end="")
    raise SystemExit(0 if report["passed"] else 1)
