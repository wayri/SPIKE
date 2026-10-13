# SPDX-License-Identifier: Apache-2.0
"""Lossless, conservative form models for single SPICE directive cards.

The form editor deliberately declines cards it cannot split without guessing.
Those cards remain editable in the raw text page.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class FormSpec:
    key: str
    label: str
    fields: tuple
    defaults: tuple
    group: str


SPECS = (
    FormSpec('tran','Transient',('Output interval [s]','Stop time [s]','Start recording [s] (optional)','Maximum solver step [s] (optional)','Flags (uic/startup, optional)'),('10u','5m','','',''),'Simulation'),
    FormSpec('ac','AC sweep',('Sweep (dec/oct/lin)','Points','Start frequency','End frequency'),('dec','20','1','1meg'),'Simulation'),
    FormSpec('dc','DC sweep',('Source','Start','Stop','Increment','Second sweep (optional)'),('V1','0','5','0.1',''),'Simulation'),
    FormSpec('op','Operating point',(),(),'Simulation'),
    FormSpec('noise','Noise',('Output expression','Input source','Sweep','Points','Start frequency','End frequency'),('V(out)','V1','dec','20','1','1meg'),'Simulation'),
    FormSpec('tf','Transfer function',('Output expression','Input source'),('V(out)','V1'),'Simulation'),
    FormSpec('pz','Pole / zero',('Input + node','Input − node','Output + node','Output − node','Transfer (vol/cur)','Find (pol/zer/pz)'),('in','0','out','0','vol','pz'),'Simulation'),
    FormSpec('sens','Sensitivity',('Output expression','AC sweep (optional)'),('V(out)',''),'Simulation'),
    FormSpec('disto','Distortion',('Sweep','Points','Start frequency','End frequency','F2/F1 ratio (optional)'),('dec','20','1','1meg',''),'Simulation'),
    FormSpec('four','Fourier',('Fundamental frequency','Output expressions'),('1k','V(out)'),'Observations'),
    FormSpec('temp','Temperature',('Temperatures [°C]',),('25',),'Simulation'),
    FormSpec('ic','Initial conditions',('Voltage assignments',),('V(out)=0',),'Initial conditions'),
    FormSpec('nodeset','Node set',('Voltage assignments',),('V(out)=0',),'Initial conditions'),
    FormSpec('param','Parameter',('Parameter assignments',),('gain=1',),'Processing'),
    FormSpec('step','Parameter sweep',('Parameter name','Mode (list/linear)','Values or start','Stop (linear)','Increment (linear)'),('gain','list','1 2 4','',''),'Processing'),
    FormSpec('options','Options',('Options',),('reltol=1e-3',),'Simulation'),
    FormSpec('measure','Measurement',('Analysis','Name','Operation / expression'),('tran','average_out','AVG V(out) FROM=1m TO=5m'),'Observations'),
)
SPEC_BY_KEY={v.key:v for v in SPECS}
TYPE_LABELS=tuple(v.label for v in SPECS)+('Raw / other',)
_KEY_ALIASES={'meas':'measure'}
_SIMPLE_TOKEN=re.compile(r'^\S+$')


@dataclass
class DirectiveForm:
    spec: FormSpec
    values: list
    original: str = ''
    original_values: tuple = ()

    def render(self):
        values=[v.strip() for v in self.values]
        if tuple(values)==self.original_values and self.original:
            return self.original
        if self.spec.key=='op':return '.op'
        required={'tran':2,'ac':4,'dc':4,'noise':6,'tf':2,'disto':4,'four':2,'temp':1,
                  'ic':1,'nodeset':1,'param':1,'step':3,'options':1,'measure':3,'pz':6,'sens':1}[self.spec.key]
        if any(not v for v in values[:required]):
            raise ValueError('Complete all required directive fields')
        if self.spec.key=='step':
            name,mode,start,stop,increment=values
            if mode.casefold()=='list':return '.step param '+name+' list '+start
            if mode.casefold()!='linear' or not stop or not increment:raise ValueError('Linear sweep requires start, stop and increment; mode is list or linear')
            return '.step param '+' '.join((name,start,stop,increment))
        if self.spec.key=='tran':
            core=values[:2]
            if values[3] and not values[2]:raise ValueError('Start time is required when maximum step is set')
            core.extend(v for v in values[2:] if v)
            values=core
        elif self.spec.key in ('dc','sens'):
            while values and not values[-1]:values.pop()
        elif self.spec.key=='disto' and not values[-1]:values.pop()
        keyword='.measure' if self.spec.key=='measure' else '.'+self.spec.key
        return keyword+' '+' '.join(values)


def _split_prefix(text, count):
    """Split count whitespace tokens and retain the unsplit remainder."""
    parts=text.split(None,count)
    if len(parts)<count+1:return None
    return parts[:count]+[parts[count]]


def parse_directive(text):
    """Return a representable DirectiveForm, or None without changing text."""
    if not isinstance(text,str) or '\n' in text or '\r' in text:return None
    match=re.match(r'^\s*\.([A-Za-z]+)(?:\s+(.*?))?\s*$',text)
    if not match:return None
    key=_KEY_ALIASES.get(match.group(1).lower(),match.group(1).lower())
    spec=SPEC_BY_KEY.get(key)
    if spec is None:return None
    body=match.group(2) or ''
    if key=='op':values=[] if not body else None
    elif key=='pz':
        values=body.split()
        if len(values)!=6:values=None
    elif key=='step':
        tokens=body.split()
        if len(tokens)>=4 and tokens[0].casefold()=='param' and tokens[2].casefold()=='list':values=[tokens[1],'list',' '.join(tokens[3:]),'','']
        elif len(tokens)==5 and tokens[0].casefold()=='param':values=[tokens[1],'linear',*tokens[2:]]
        else:values=None
    elif key in ('four','temp','ic','nodeset','param','options'):
        values=[body] if body else None
        if key=='four' and values:
            values=_split_prefix(body,1)
    elif key=='measure':values=_split_prefix(body,2)
    elif key in ('sens',):
        values=_split_prefix(body,1) if len(body.split())>1 else ([body,''] if body else None)
    else:
        counts={'tran':2,'ac':4,'dc':4,'noise':6,'tf':2,'disto':4}
        minimum=counts[key];tokens=body.split()
        if len(tokens)<minimum:values=None
        elif key=='tran':
            values=tokens[:2]+['','','']
            tail=tokens[2:]
            flags=[]
            if tail and tail[0].lower() not in ('uic','startup'):values[2]=tail.pop(0)
            if tail and tail[0].lower() not in ('uic','startup'):values[3]=tail.pop(0)
            flags=tail
            if any(v.lower() not in ('uic','startup') for v in flags):values=None
            elif values is not None:values[4]=' '.join(flags)
        elif key=='dc':values=tokens[:4]+[' '.join(tokens[4:])]
        elif key=='disto':
            values=tokens if len(tokens)<=5 else None
            if values is not None:values+=['']*(5-len(values))
        else:values=tokens
        if values is not None and len(values)!=len(spec.fields):values=None
    if values is None:return None
    # Values used as atomic tokens must not contain syntax we would re-tokenize.
    atomic={'ac':range(4),'noise':range(1,6),'tf':range(1,2),'disto':range(4)}
    if any(not _SIMPLE_TOKEN.match(values[i]) for i in atomic.get(key,())):return None
    if key in ('ac','noise','disto'):
        sweep_index=2 if key=='noise' else 0
        points_index=3 if key=='noise' else 1
        if values[sweep_index].lower() not in ('dec','oct','lin'):return None
        try:
            if int(values[points_index])<=0:return None
        except ValueError:return None
    clean=tuple(v.strip() for v in values)
    return DirectiveForm(spec,list(clean),text,clean)


def new_form(key):
    spec=SPEC_BY_KEY[key]
    return DirectiveForm(spec,list(spec.defaults))


def type_key_for(text):
    form=parse_directive(text)
    return form.spec.key if form else None
