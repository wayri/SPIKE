"""Executable parser capability probes; acceptance is never numerical qualification."""
import hashlib
import platform
import tempfile
from pathlib import Path
from .netlist import parse_netlist

BASE='V1 in 0 1\nR1 in out 1k\nR2 out 0 1k\n'

def deck(body=BASE,analysis='.op'):
    return 'SPIKES capability probe\n'+body+analysis+'\n.end\n'

CASES=[
 ('language.parameters',deck('.param r=1k\nV1 in 0 1\nR1 in 0 {r*2}\n')),
 ('language.functions',deck('.func double(x) {2*x}\nV1 in 0 1\nR1 in 0 {double(500)}\n')),
 ('language.subcircuit_parameters',deck('.subckt cell a b params: r=1k\nR1 a b {r}\n.ends\nV1 in 0 1\nX1 in 0 cell r=2k\n')),
 ('language.scoped_models',deck('.subckt cell a b\n.model local D(IS=1e-12 N=1)\nD1 a b local\n.ends\nV1 in 0 .1\nX1 in 0 cell\n')),
 ('language.model_parameters',deck('.subckt cell a b params: isat=1p\n.model local D(IS={isat*2} N={1+.1})\nD1 a b local\n.ends\nV1 in 0 .1\nX1 in 0 cell isat=2p\n')),
 ('language.global_nodes',deck('.global rail\nV1 rail 0 1\nR1 rail 0 1k\n')),
 ('language.include',deck('.include "cell.inc"\nV1 in 0 1\nX1 in 0 cell\n')),
 ('language.library_section',deck('.lib "cell.lib" typical\nV1 in 0 1\nX1 in 0 cell\n')),
 ('language.measure',deck(BASE,'.tran 1u 10u\n.measure tran output FIND v(out) AT=5u')),
 ('language.step',deck('.param r=1k\nV1 in 0 1\nR1 in 0 {r}\n','.step param r list 1k 2k\n.op')),
 ('language.initial_conditions',deck('V1 in 0 1\nR1 in out 1k\nC1 out 0 1u IC=0\n','.tran 1u 10u uic')),
 ('source.dc',deck()),
 ('source.pulse',deck('V1 in 0 PULSE(0 1 0 1n 1n 1u 2u)\nR1 in 0 1k\n','.tran 10n 5u')),
 ('source.pwl',deck('V1 in 0 PWL(0 0 1u 1 2u 0)\nR1 in 0 1k\n','.tran 10n 2u')),
 ('source.sin',deck('V1 in 0 SIN(0 1 1k)\nR1 in 0 1k\n','.tran 1u 1m')),
 ('source.exp',deck('V1 in 0 EXP(0 1 1u 1u 5u 1u)\nR1 in 0 1k\n','.tran 1u 10u')),
 ('source.sffm',deck('V1 in 0 SFFM(0 1 1k 2 100)\nR1 in 0 1k\n','.tran 1u 1m')),
 ('source.vcvs',deck(BASE+'E1 e 0 in 0 2\nR3 e 0 1k\n')),
 ('source.vccs',deck(BASE+'G1 g 0 in 0 .001\nR3 g 0 1k\n')),
 ('source.cccs',deck(BASE+'F1 f 0 V1 2\nR3 f 0 1k\n')),
 ('source.ccvs',deck(BASE+'H1 h 0 V1 1000\nR3 h 0 1k\n')),
 ('source.behavioral',deck(BASE+'B1 b 0 V=sin(V(in))+V(out)^2\nR3 b 0 1k\n')),
 ('device.diode_static',deck('V1 in 0 .1\nD1 in 0 dm\n.model dm D(IS=1e-12 N=1)\n')),
 ('device.diode_charge',deck('V1 in 0 .1\nD1 in 0 dm\n.model dm D(IS=1e-12 CJO=10p TT=5n)\n','.tran 1n 10n')),
 ('device.bjt',deck('V1 c 0 1\nV2 b 0 .6\nQ1 c b 0 qm\n.model qm NPN(IS=1e-14 BF=100)\n')),
 ('device.jfet',deck('V1 d 0 1\nJ1 d 0 0 jm\n.model jm NJF(VTO=-2 BETA=.001)\n')),
 ('device.mos_level1',deck('V1 d 0 1\nV2 g 0 2\nM1 d g 0 0 mm W=10u L=1u\n.model mm NMOS(LEVEL=1 VTO=1 KP=1m)\n')),
 ('device.bsim4',deck('V1 d 0 1\nV2 g 0 2\nM1 d g 0 0 mm W=10u L=1u\n.model mm NMOS(LEVEL=54)\n')),
 ('device.transmission_line',deck('V1 in 0 1\nT1 in 0 out 0 Z0=50 TD=1n\nR1 out 0 50\n','.tran .1n 10n')),
 ('device.coupled_inductors',deck('V1 in 0 1\nL1 in 0 1m\nL2 out 0 1m\nR1 out 0 100\nK1 L1 L2 .99\n','.tran 1u 10u')),
 ('analysis.op',deck()),('analysis.dc',deck(BASE,'.dc V1 0 1 .1')),
 ('analysis.transient',deck(BASE,'.tran 1u 10u')),
 ('analysis.transient_start_max',deck(BASE,'.tran 1u 10u 2u .5u')),
 ('analysis.ac',deck('V1 in 0 DC 0 AC 1\nR1 in out 1k\nC1 out 0 1u\n','.ac dec 10 1 1meg')),
 ('analysis.noise',deck(BASE,'.noise V(out) V1 dec 10 1 1meg')),
 ('analysis.transfer',deck(BASE,'.tf V(out) V1')),
 ('analysis.pole_zero',deck(BASE,'.pz in 0 out 0 vol pz')),
 ('analysis.sensitivity',deck(BASE,'.sens V(out)')),
 ('analysis.distortion',deck(BASE,'.disto dec 10 1 1meg')),
 ('analysis.fourier',deck(BASE,'.tran 1u 10u\n.four 1k V(out)')),
 ('analysis.temperature',deck('.temp 50\n'+BASE)),
]

# These sentinel decks must reject rather than silently drop physical terms.
REJECTION_CASES=[
 ('diagnostics.unknown_directive',deck(BASE,'.teleport 1')),
 ('diagnostics.unknown_diode_parameter',deck('V1 in 0 .1\nD1 in 0 d\n.model d D(IS=1e-12 MADEUP=1)\n')),
 ('diagnostics.unknown_source_waveform',deck('V1 in 0 MAGIC(1 2)\nR1 in 0 1k\n')),
]

def run_capability_audit():
    rows=[]
    with tempfile.TemporaryDirectory(prefix='spikes-capability-') as folder:
        root=Path(folder)
        (root/'cell.inc').write_text('.subckt cell a b\nR1 a b 1k\n.ends\n',encoding='utf-8')
        (root/'cell.lib').write_text('.lib typical\n.subckt cell a b\nR1 a b 1k\n.ends\n.endl typical\n',encoding='utf-8')
        for ident,text in CASES+REJECTION_CASES:
            row={'id':ident,'deck_sha256':hashlib.sha256(text.encode()).hexdigest(),
                 'deck':text,'parser':'rejected','native_implementation':'not_established_by_this_probe',
                 'numerical_verification':'not_tested','cross_engine_qualification':'not_tested'}
            try:
                project=parse_netlist(text,source_name=str(root/'probe.cir'),native_extensions=True)
                row.update(parser='accepted',elements=len(project.elements))
            except ValueError as error:row['diagnostic']=str(error)
            rows.append(row)
    negatives=[row for row in rows if row['id'].startswith('diagnostics.')]
    return {'contract':'spikes/capability-audit/v1','host':platform.platform(),
            'scope':'One representative grammar probe per listed feature; not exhaustive SPICE grammar or numerical coverage',
            'full_spice_parity':False,'features':rows,
            'summary':{'positive_probes':len(CASES),'accepted':sum(r['parser']=='accepted' for r in rows[:len(CASES)]),
                       'rejected':sum(r['parser']=='rejected' for r in rows[:len(CASES)]),
                       'strict_rejection_sentinels_passed':all(r['parser']=='rejected' for r in negatives)}}
