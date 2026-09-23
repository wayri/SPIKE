"""Explicit linear frequency-response analyzer; not switching loop injection."""
from dataclasses import replace
import math
from .analyses import AcSweep, AcExcitation, run_transfer_function
from .contracts import ProbeDescriptor
from .netlist import parse_netlist


def analyze(source, excitation, output, start_hz=1., stop_hz=1e6, points=301):
    if type(points) is not int or not 2<=points<=10000:raise ValueError('FRA requires 2..10000 points')
    if not all(math.isfinite(v) and v>0 for v in (start_hz,stop_hz)) or start_hz>=stop_hz:raise ValueError('Invalid FRA frequency range')
    project=parse_netlist(source,native_extensions=True,transient_capture='rolling')
    nodes={n for e in project.elements for n in (e.positive_node,e.negative_node,e.control_positive_node,e.control_negative_node) if n not in (None,'0')}
    if len(nodes)+sum(e.kind in ('inductor','voltage_source','vcvs','ccvs') for e in project.elements)>256:raise ValueError('FRA limited to 256 linear MNA unknowns')
    if project.steps:raise ValueError('Select one .step instance before FRA')
    probe=ProbeDescriptor.parse(output)
    project=replace(project,probes=tuple(p for p in project.probes if p.name!=probe.name)+(probe,))
    result=run_transfer_function(project,AcSweep(start_hz,stop_hz,points,'log'),AcExcitation(excitation),probe)
    result['fra']={'contract':'spikes/fra/v1','excitation':excitation,'output':output,
        'backend':'Python linear complex MNA, not native switching FRA',
        'interpretation':'Output divided by selected ideal source phasor; not automatically loop gain',
        'limitations':['No periodic operating-point linearization','No automatic loop breaking or stability certification']}
    return result
