"""Explicit linear capacitor package model: series ESR/ESL, parallel leakage."""
import math
import re

FIELDS = ('esr_ohm', 'esl_h', 'leakage_ohm')


def validate(values):
    if not isinstance(values, dict) or set(values)-set(FIELDS): raise ValueError('Unknown capacitor parasitic')
    for key,value in values.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError(f'{key} must be finite and positive; omit to disable')


def expand(source, part, values):
    validate(values)
    if not values:return source
    if part['kind']!='capacitor' or ':' in part['ref']:
        raise ValueError('Parasitic expansion currently requires a top-level capacitor')
    ref=part['ref']; tag='SPKPAR_'+ref.upper()
    if tag.lower() in source.lower():raise ValueError('Reserved parasitic identifier collision')
    pattern=re.compile(r'(?im)^([ \t]*'+re.escape(ref)+r')[ \t]+(\S+)[ \t]+(\S+)([^\r\n]*)$')
    matches=list(pattern.finditer(source))
    if len(matches)!=1:raise ValueError('Expected one top-level capacitor record')
    m=matches[0];p,n=m[2],m[3];node=p;lines=[]
    for key,prefix in (('esr_ohm','R'),('esl_h','L')):
        if key in values:
            nxt=tag+'_'+prefix
            lines.append(f'{prefix}{tag} {node} {nxt} {values[key]:.17g}');node=nxt
    lines.append(f'{ref} {node} {n}{m[4]}')
    if 'leakage_ohm' in values:lines.append(f'R{tag}_LEAK {p} {n} {values["leakage_ohm"]:.17g}')
    return source[:m.start()]+'\n'.join(lines)+source[m.end():]


def impedance(capacitance, frequency, values):
    validate(values)
    if capacitance<=0 or frequency<=0:raise ValueError('Positive capacitance and frequency required')
    w=2*math.pi*frequency
    z=values.get('esr_ohm',0)+1j*(w*values.get('esl_h',0)-1/(w*capacitance))
    return z*values['leakage_ohm']/(z+values['leakage_ohm']) if 'leakage_ohm' in values else z
