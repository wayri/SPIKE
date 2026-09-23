"""Explicit series-voltage injection return ratio for linear unilateral loops."""
import math
import numpy as np
from .analyses import AcSweep,AcExcitation,run_ac_analysis
from .netlist import parse_netlist


def analyze(source,injection,start_hz=1.,stop_hz=1e6,points=301,*,assume_unilateral=False):
    if assume_unilateral is not True:raise ValueError('Voltage-injection extraction requires explicit acknowledgement of a valid unilateral injection point')
    if type(points) is not int or not 3<=points<=10000:raise ValueError('Loop gain requires 3..10000 sweep points')
    project=parse_netlist(source,native_extensions=True,transient_capture='rolling')
    if project.steps:raise ValueError('Select one step before loop-gain analysis')
    fixture=next((e for e in project.elements if e.name==injection.upper()),None)
    if fixture is None or fixture.kind!='voltage_source' or fixture.waveform or fixture.value!=0 or '0' in (fixture.positive_node,fixture.negative_node):
        raise ValueError('Insert an explicit zero-DC voltage source between forward (+) and return (-) loop nodes; neither terminal may be ground')
    nodes={n for e in project.elements for n in (e.positive_node,e.negative_node,e.control_positive_node,e.control_negative_node) if n not in (None,'0')}
    if len(nodes)+sum(e.kind in ('voltage_source','inductor','vcvs','ccvs') for e in project.elements)>256:raise ValueError('Loop-gain analysis limited to 256 MNA unknowns')
    result=run_ac_analysis(project,AcSweep(start_hz,stop_hz,points,'log'),AcExcitation(injection))
    if result['status']!='completed':raise ValueError('AC loop-gain solve failed')
    data=result['data'];f=np.asarray(data['frequency_hz'])
    def voltage(node):
        series=data['node_voltage_v'][node]
        return np.asarray(series['real'])+1j*np.asarray(series['imaginary'])
    forward=voltage(fixture.positive_node);returned=voltage(fixture.negative_node)
    if np.any(np.abs(forward)<1e-12):raise ValueError('Forward injection response too small for a reliable ratio')
    ratio=-returned/forward
    if not np.isfinite(ratio).all():raise ValueError('Nonfinite loop response')
    magnitude=20*np.log10(np.maximum(abs(ratio),1e-300));phase=np.degrees(np.unwrap(np.angle(ratio)))
    crossings=[]
    for i in range(len(f)-1):
        if magnitude[i]==0 or magnitude[i]*magnitude[i+1]<0:
            fraction=0 if magnitude[i]==0 else -magnitude[i]/(magnitude[i+1]-magnitude[i])
            angle=float(phase[i]+fraction*(phase[i+1]-phase[i]))
            crossings.append(dict(frequency_hz=float(math.exp(math.log(f[i])+fraction*math.log(f[i+1]/f[i]))),phase_deg=angle,phase_margin_deg=180+angle))
    return dict(contract='spikes/voltage-injection-loop-gain/v1',status='completed',injection=injection,
        forward_node=fixture.positive_node,return_node=fixture.negative_node,frequency_hz=f.tolist(),
        real=ratio.real.tolist(),imaginary=ratio.imag.tolist(),gain_db=magnitude.tolist(),phase_deg=phase.tolist(),unity_crossings=crossings,
        source_sha256=project.source_sha256,backend='Python linear complex MNA',
        limitations=['User-asserted unilateral fixture; no automatic impedance-condition verification',
                     'No multiloop, periodic switching or nonlinear-bias linearization',
                     'Interpolated sampled crossings and phase-unwrap convention; not a stability certificate'])
