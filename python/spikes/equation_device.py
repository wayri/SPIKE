# SPDX-License-Identifier: Apache-2.0
"""Inert constitutive I/Q models lowered to owned native MNA primitives.

No material-family dispatch and no Python numerical execution. See
docs/SPIKES_EQUATION_DEVICES.md for charge transformation and boundaries.
"""
from __future__ import annotations

import ast
import math
import re
from collections.abc import Mapping

from .behavioral import compile_behavioral_expression

CONTRACT = 'spikes/equation-device/v1'
_ID = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,47}\Z')


def _identifier(value, label):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(label + ' must be an ASCII identifier of at most 48 characters')
    return value


def _number(value, label):
    if isinstance(value, (bool, str, bytes)) or not isinstance(value, (int, float)):
        raise ValueError(label + ' must be a finite SI number')
    result = float(value)
    if not math.isfinite(result):raise ValueError(label + ' must be finite')
    return result


def build(spec: Mapping) -> dict:
    """Validate and compose a library subcircuit; import never executes code.

    Each branch declares current in A and/or conservative branch charge in C.
    Expressions use V(pin,pin), parameters and the supported bounded functions.
    A reference capacitor converts Q to an auxiliary voltage, with its sensed
    native current copied to the actual terminal pair. No finite differencing
    or Python callbacks occur during simulation.
    """
    if not isinstance(spec, Mapping):raise ValueError('device must be a mapping')
    if set(spec)-{'contract','name','pins','parameters','branches','material','notes'}:
        raise ValueError('Unknown equation-device fields')
    if spec.get('contract') != CONTRACT:raise ValueError('Unsupported equation-device contract')
    name=_identifier(spec.get('name'),'name')
    pins=spec.get('pins')
    if not isinstance(pins, list) or not 2 <= len(pins) <= 32:raise ValueError('Require 2..32 ordered pins')
    pins=[_identifier(pin,'pin') for pin in pins]
    if len({p.lower() for p in pins}) != len(pins):raise ValueError('Duplicate pins')
    allowed={p.lower() for p in pins}
    parameters=spec.get('parameters',{})
    if not isinstance(parameters, Mapping) or len(parameters)>64:raise ValueError('Require at most 64 parameters')
    values={};resolved={}
    for key,item in parameters.items():
        _identifier(key,'parameter')
        if key.lower() in values or key.lower() in {'time','pi','e'}:raise ValueError('Duplicate or reserved parameter')
        if not isinstance(item,Mapping) or set(item)!={'value','unit'}:raise ValueError('Parameter requires value and unit')
        unit=item['unit']
        if not isinstance(unit,str) or not unit.strip() or len(unit)>64:raise ValueError('Parameter requires SI unit metadata')
        value=_number(item['value'],key);values[key.lower()]=value
        resolved[key]=dict(value=value,unit=unit)
    branches=spec.get('branches')
    if not isinstance(branches,list) or not 1<=len(branches)<=64:raise ValueError('Require 1..64 branches')
    lines=['* Original user-defined unqualified constitutive model',f'.subckt {name} '+ ' '.join(pins)]
    used=set();normalized=[]

    def expression(text):
        if not isinstance(text,str) or not text.strip() or len(text)>4096 or any(c in text for c in '\r\n;{}'):
            raise ValueError('Expression must be one bounded line without directives')
        compiled=compile_behavioral_expression(text,parameters=values)
        if any(isinstance(node,ast.Constant) and not math.isfinite(float(node.value)) for node in ast.walk(compiled.tree)):
            raise ValueError('Expression constants must be finite')
        result=compiled.normalized
        for index in range(len(compiled.signals)-1,-1,-1):
            signal=compiled.signals[index]
            if signal.kind!='v' or signal.first not in allowed or signal.second not in allowed:
                raise ValueError('Use differential V(pin,pin) on declared device pins only')
            result=re.sub(rf'\b__s{index}\b',f'V({signal.first},{signal.second})',result)
        # Validation only: no evaluation of a user equation at an invented bias.
        return result

    for index,branch in enumerate(branches):
        if not isinstance(branch,Mapping) or set(branch)-{'name','positive','negative','current_a','charge_c','charge_scale_f'}:
            raise ValueError('Unknown branch fields')
        label=_identifier(branch.get('name'),'branch name')
        if label.lower() in used:raise ValueError('Duplicate branch name')
        used.add(label.lower())
        p=branch.get('positive');n=branch.get('negative')
        if p not in pins or n not in pins or p==n:raise ValueError('Branch needs two distinct declared pins')
        if 'current_a' not in branch and 'charge_c' not in branch:raise ValueError('Branch needs current or charge')
        record=dict(name=label,positive=p,negative=n)
        if 'current_a' in branch:
            current=expression(branch['current_a']);record['current_a']=current
            lines.append(f'BI{index} {p} {n} I={{{current}}}')
        if 'charge_c' in branch:
            charge=expression(branch['charge_c'])
            scale=_number(branch.get('charge_scale_f',1e-9),'charge_scale_f')
            if not 1e-18<=scale<=1:raise ValueError('charge_scale_f must be in [1e-18,1] F')
            # Internal auxiliary nodes cannot collide with a public pin.
            drive=f'__qdrive{index}';store=f'__qstore{index}'
            if drive.lower() in allowed or store.lower() in allowed:raise ValueError('Reserved auxiliary pin name')
            lines.extend((f'BQ{index} {drive} 0 V={{({charge})/{scale:.17g}}}',
                          f'VQ{index} {drive} {store} 0',f'CQ{index} {store} 0 {scale:.17g}',
                          f'BT{index} {p} {n} I={{I(VQ{index})}}'))
            record.update(charge_c=charge,charge_scale_f=scale)
        elif 'charge_scale_f' in branch:raise ValueError('charge_scale_f requires charge_c')
        normalized.append(record)
    lines.append(f'.ends {name}')
    for key in ('material','notes'):
        if key in spec and (not isinstance(spec[key],str) or len(spec[key])>4096):raise ValueError(key+' must be bounded text')
    return dict(contract=CONTRACT,name=name,pins=pins,parameters=resolved,branches=normalized,
                material=spec.get('material','user-defined'),notes=spec.get('notes',''),
                source='\n'.join(lines)+'\n',backend='native',model_status='user_defined_unqualified',
                supported_analyses=['op','transient_backward_euler','transient_bdf2'],
                limitations=['Lumped electrical constitutive equations, not TCAD or material qualification.',
                             'Unit metadata is retained; automatic dimensional proof is not implemented.',
                             'No inferred thermal, trapping, recovery, breakdown, noise or aging physics.',
                             'Charge transformation adds auxiliary unknowns; stiff/discontinuous equations need convergence tests.',
                             'Hybrid integration, AC/noise and arbitrary internal-state equations are not qualified by this builder.'])
