# SPDX-License-Identifier: Apache-2.0
"""Configurable standard-value passives, not invented manufacturer SKUs."""
import math
from python.spikes.passive_models import build_model, impedance

MODEL_TYPE='lumped_passive_rlc_v1'
PACKAGES=('01005','0201','0402','0603','0805','1206','1210','1808','1812','1825','2010','2220','2512','Custom / nonstandard')
TOLERANCES=(.05,.1,.25,.5,1.,2.,5.,10.)
CONSTRUCTIONS={'resistor':('Unspecified','Thin film','Thick film','Metal film','Wirewound','Shunt'),
              'kelvin_shunt':('Four-terminal shunt',),
              'capacitor':('Unspecified','C0G / NP0','X7R','X5R','Film','Electrolytic','Polymer'),
              'inductor':('Unspecified','Air core','Ferrite','Powder core','Planar','Wirewound')}
E24=(10,11,12,13,15,16,18,20,22,24,27,30,33,36,39,43,47,51,56,62,68,75,82,91)
# Independent logarithmic construction; IEC's 920 exception is retained.
E192=tuple(920 if (n:=round(100*10**(i/192)))==919 else n for i in range(192))
SERIES={'E3':E24[::8],'E6':E24[::4],'E12':E24[::2],'E24':E24,
        'E48':E192[::4],'E96':E192[::2],'E192':E192}
LIMITATIONS=('Configurable original lumped passive, not a manufacturer model. Package and construction are labels only; '
             'they do not generate parasitics, ratings or thermal coefficients. Zero parasitics are explicitly omitted. '
             'Tolerance corner and temperature are static at model compilation, not dynamic self-heating. '
             'No dielectric bias/aging, frequency-dependent losses, magnetic saturation, skin effect, breakdown or qualification.')


def preferred_values(series,minimum,maximum):
    if series not in SERIES:raise ValueError('Choose E3, E6, E12, E24, E48, E96 or E192')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (minimum,maximum)) or minimum>maximum:
        raise ValueError('Preferred-value range must be finite, positive and ordered')
    low=math.floor(math.log10(minimum));high=math.ceil(math.log10(maximum))
    if low < -18 or high > 15 or high-low>24:raise ValueError('Preferred-value range exceeds supported decades')
    bases=SERIES[series];divisor=10 if series in ('E3','E6','E12','E24') else 100
    values={float(f'{base/divisor*10**decade:.12g}') for decade in range(low,high+1) for base in bases}
    return sorted(v for v in values if minimum<=v<=maximum)


def nearest(value,series='E24'):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise ValueError('Enter a positive finite value')
    decade=math.floor(math.log10(value));values=preferred_values(series,10**(decade-1),10**(decade+1))
    chosen=min(values,key=lambda v:(abs(v-value),v))
    return {'value':chosen,'relative_error_percent':100*(chosen/value-1),'series':series}


def make_record(kind,value,*,ident=None,package='0603',construction=None,tolerance_percent=1.,**overrides):
    if kind not in CONSTRUCTIONS:raise ValueError('Unknown passive kind')
    family='resistor' if kind=='kelvin_shunt' else kind;key={'resistor':'r','capacitor':'c','inductor':'l'}[family]
    parameters={key:value,'series_resistance_ohm':0.,'series_inductance_h':0.,'parallel_capacitance_f':0.,
                'leakage_resistance_ohm':0.,'contact_resistance_ohm':0.,'tolerance_percent':tolerance_percent,
                'corner':0.,'temperature_c':25.,'reference_temperature_c':25.,'tc1_per_k':0.,'tc2_per_k2':0.}
    if set(overrides)-set(parameters):raise ValueError('Unknown passive parameter')
    parameters.update(overrides)
    ident=ident or 'standard.custom.'+kind
    unit={'resistor':'ohm','capacitor':'F','inductor':'H'}[family]
    record={'id':ident,'category':'Passives','family':family,'passive_kind':kind,'model_type':MODEL_TYPE,
            'package_code':package,'construction':construction or CONSTRUCTIONS[kind][0],
            'name':f'Configurable {kind.replace("_"," ")} - {value:.7g} {unit}',
            'parameters':parameters,'parameter_unit':unit,'status':'native_subcircuit',
            'manufacturer':None,'fidelity':'generic_reduced_order','license':'Apache-2.0 original SPIKES contribution',
            'limitations':LIMITATIONS,'qualification':'unqualified_presets',
            'origin':'IEC preferred values with independently authored configurable RLC recipe; no manufacturer SKU'}
    validate_record(record);return record


def validate_record(record):
    import re
    if record.get('model_type')!=MODEL_TYPE or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',record.get('id','')):
        raise ValueError('Invalid passive model identity')
    kind=record.get('passive_kind');family='resistor' if kind=='kelvin_shunt' else kind
    if kind not in CONSTRUCTIONS or record.get('family')!=family or record.get('category')!='Passives':raise ValueError('Invalid passive family')
    if record.get('package_code') not in PACKAGES or record.get('construction') not in CONSTRUCTIONS[kind]:raise ValueError('Unknown package/construction label')
    key={'resistor':'r','capacitor':'c','inductor':'l'}[family]
    expected={key,'series_resistance_ohm','series_inductance_h','parallel_capacitance_f','leakage_resistance_ohm',
              'contact_resistance_ohm','tolerance_percent','corner','temperature_c','reference_temperature_c','tc1_per_k','tc2_per_k2'}
    if not isinstance(record.get('parameters'),dict) or set(record['parameters'])!=expected:raise ValueError('Passive parameters do not match the model contract')
    if record.get('status')!='native_subcircuit' or record.get('parameter_unit')!={'resistor':'ohm','capacitor':'F','inductor':'H'}[family]:raise ValueError('Invalid passive execution/unit metadata')
    if record.get('manufacturer') is not None or record.get('qualification')!='unqualified_presets' or record.get('fidelity')!='generic_reduced_order':raise ValueError('Configurable standard-value templates cannot claim manufacturer qualification')
    model(record) # Numerical boundary performs finite/range checks.


def model(record):
    p=dict(record['parameters']);kind=record['passive_kind']
    key={'resistor':'r','kelvin_shunt':'r','capacitor':'c','inductor':'l'}[kind]
    value=p.pop(key)
    if p['leakage_resistance_ohm']==0:p['leakage_resistance_ohm']=None
    return build_model(kind,value,name='SPK_'+record['id'].replace('.','_'),**p)


def records():
    result=[]
    for kind,series,lo,hi in [('resistor','E192',.001,1e9),('capacitor','E24',1e-12,1.),
                              ('inductor','E24',1e-9,10.),('kelvin_shunt','E24',.001,1.)]:
        for i,value in enumerate(preferred_values(series,lo,hi)):
            result.append(make_record(kind,value,ident=f'standard.{kind}.{series}.{i+1:04d}'))
    return result


def evaluate(record,inputs=None):
    if record['passive_kind']=='kelvin_shunt':raise ValueError('Kelvin devices require native circuit analysis, not a two-terminal bench')
    frequency=(inputs or {}).get('frequency_hz',1000.)
    z=impedance(model(record),frequency)
    if not math.isfinite(z.real) or not math.isfinite(z.imag):raise ValueError('Open-circuit impedance at this frequency; use native circuit analysis')
    return {'outputs':{'impedance_real':{'value':z.real,'unit':'ohm'},'impedance_imag':{'value':z.imag,'unit':'ohm'}},
            'state':{},'alerts':[],'domain':'linear_frequency_reference','not_circuit_coupled':True,'limitations':LIMITATIONS}
