# SPDX-License-Identifier: Apache-2.0
"""Original functional HC package models; not vendor electrical models.

Pin numbering and Boolean functions are factual data from TI datasheets.
Transport delay is supplied by the caller, not inferred from the part name.
"""
from copy import deepcopy
import math
import re

from .digital import DigitalKernel

CONTRACT = 'spikes/standard-logic/v1'
FUNCTIONS = {'00': 'nand', '02': 'nor', '04': 'not', '08': 'and',
             '10': 'nand', '11': 'and', '20': 'nand', '21': 'and',
             '32': 'or', '86': 'xor'}
LIMITATIONS = ('Functional four-state model only. User-specified transport delay; '
               'no manufacturer timing qualification, voltage thresholds, output drive, '
               'supply current, package RLC, temperature, metastability or electrical SI. '
               '54 and 74 share Boolean behavior, not electrical/temperature guarantees.')


def package(part):
    """Return an isolated 14-pin package descriptor, never guess another package."""
    match = re.fullmatch(r'SN(54|74)HC(00|02|04|08|10|11|20|21|32|86)(J|N)?', str(part).upper())
    if not match or match[3] not in (None, 'J' if match[1] == '54' else 'N'):
        raise ValueError('Supported: SN54HCxxJ / SN74HCxxN 14-pin packages only')
    series, function = match[1], match[2]
    if function in ('10', '11'):
        gates = [(('1', '2', '13'), '12'), (('3', '4', '5'), '6'),
                 (('9', '10', '11'), '8')]
    elif function in ('20', '21'):
        gates = [(('1', '2', '4', '5'), '6'), (('9', '10', '12', '13'), '8')]
    elif function == '04':
        gates = [(('1',), '2'), (('3',), '4'), (('5',), '6'),
                 (('9',), '8'), (('11',), '10'), (('13',), '12')]
    elif function == '02':
        gates = [(('2', '3'), '1'), (('5', '6'), '4'),
                 (('8', '9'), '10'), (('11', '12'), '13')]
    else:
        gates = [(('1', '2'), '3'), (('4', '5'), '6'),
                 (('9', '10'), '8'), (('12', '13'), '11')]
    pins = {'7': {'name': 'GND', 'role': 'power'}, '14': {'name': 'VCC', 'role': 'power'}}
    if function in ('20', '21'):
        pins.update({n: {'name': 'NC', 'role': 'unconnected'} for n in ('3', '11')})
    for i, (inputs, output) in enumerate(gates, 1):
        for index, pin in enumerate(inputs):
            pins[pin] = {'name': f'{i}{chr(65+index)}', 'role': 'input'}
        pins[output] = {'name': f'{i}Y', 'role': 'output'}
    return {'contract': CONTRACT, 'part': f'SN{series}HC{function}'+('J' if series == '54' else 'N'),
            'family': FUNCTIONS[function], 'package': 'CDIP-14' if series == '54' else 'PDIP-14',
            'pins': [{'number': n, **pins[n]} for n in sorted(pins, key=int)],
            'gates': [{'inputs': list(ins), 'output': out} for ins, out in gates],
            'source_url': f'https://www.ti.com/lit/ds/symlink/sn74hc{function}.pdf',
            'accessed_on': '2026-10-12', 'qualification': 'functional_tests_only',
            'limitations': LIMITATIONS}


def catalog():
    return [package(f'SN{series}HC{function}') for series in ('54', '74') for function in FUNCTIONS]


def bind(kernel, part, instance, mapping, *, delay_ticks):
    """Bind complete physical-pin mapping to an existing digital kernel.

    VCC/GND are declared interfaces, not electrical power behavior. All signals
    must already exist. Preflight rejects errors before adding any primitive.
    Delay uses the kernel's caller-defined tick unit and transport semantics.
    """
    if not isinstance(kernel, DigitalKernel):
        raise ValueError('A DigitalKernel is required')
    if not isinstance(instance, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,80}', instance):
        raise ValueError('Invalid instance identifier')
    if type(delay_ticks) is not int or not 0 <= delay_ticks <= 2**63-1:
        raise ValueError('delay_ticks must be an explicit nonnegative integer')
    descriptor = package(part)
    if not isinstance(mapping, dict) or set(mapping) != {p['number'] for p in descriptor['pins']}:
        raise ValueError('Map all 14 physical pins exactly once using string pin numbers')
    signals = {s['name'] for s in kernel.model()['signals']}
    if any(not isinstance(s, str) or s not in signals for s in mapping.values()):
        raise ValueError('Pin mapping refers to a missing digital signal')
    ids = [f'{instance}.g{i}' for i in range(1, len(descriptor['gates'])+1)]
    occupied = {p['id'] for p in kernel.model()['primitives']}
    if occupied.intersection(ids):
        raise ValueError('Digital instance already exists')
    for ident, gate in zip(ids, descriptor['gates']):
        kernel.add_primitive(ident, descriptor['family'], [mapping[p] for p in gate['inputs']],
                             mapping[gate['output']], delay_ticks=delay_ticks)
    return {**descriptor, 'instance': instance, 'mapping': deepcopy(mapping),
            'delay_ticks': delay_ticks, 'electrical_circuit_coupled': False,
            'power_behavior': 'declared_only'}


def spice_recipe(part, *, output_resistance_ohm, input_capacitance_f, transition_v):
    """Explicit unqualified smooth-gate recipe for an ngspice-compatible backend.

    No transport delay. User-selected Cout/board parasitics must be added outside
    this model. This is not an IBIS or manufacturer compact model.
    """
    values = (output_resistance_ohm, input_capacitance_f, transition_v)
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError('Rout, Cin and transition width must be explicit positive finite SI values')
    descriptor = package(part)
    name = 'SPK_FUNCTIONAL_'+descriptor['part']
    lines = ['* ORIGINAL GENERIC APPROXIMATION: NOT A VENDOR MODEL; NO DELAY',
             f'.subckt {name} '+' '.join('P'+str(i) for i in range(1, 15))]
    for pin in descriptor['pins']:
        if pin['role'] == 'input':
            lines.append(f"CIN{pin['number']} P{pin['number']} P7 {input_capacitance_f:.17g}")
    for i, gate in enumerate(descriptor['gates'], 1):
        terms = [f'(0.5*(1+tanh((v(P{p},P7)-0.5*v(P14,P7))/{transition_v:.17g})))'
                 for p in gate['inputs']]
        a = terms[0]; b = terms[-1]; family = descriptor['family']
        product = '*'.join(terms)
        complement = '*'.join(f'(1-{term})' for term in terms)
        expr = {'not': f'(1-{a})', 'and': f'({product})', 'nand': f'(1-{product})',
                'or': f'(1-{complement})', 'nor': f'({complement})',
                'xor': f'({a}+{b}-2*{a}*{b})'}[family]
        lines += [f'B{i} INTERNAL{i} P7 V=v(P14,P7)*{expr}',
                  f"R{i} INTERNAL{i} P{gate['output']} {output_resistance_ohm:.17g}"]
    lines.append(f'.ends {name}')
    return {'name': name, 'pins': [str(i) for i in range(1, 15)], 'source': '\n'.join(lines)+'\n',
            'backend': 'explicit_ngspice_compatibility', 'qualification': 'unqualified_generic',
            'limitations': LIMITATIONS+' Smooth electrical recipe has no propagation delay.'}
