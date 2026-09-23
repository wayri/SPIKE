"""Generic logical IC interfaces, not manufacturer package pinouts.

Numbering is local logical numbering. Geometry does not qualify a model.
"""
import math


def pin_contract(record):
    family=record['family'];p=record['parameters']
    inputs=[];outputs=[];power=['VDD','GND']
    if family in ('and','or','nand','nor','xor','xnor'):inputs=['A','B'];outputs=['Y']
    elif family=='not':inputs=['A'];outputs=['Y']
    elif family=='mux2':inputs=['D0','D1','SEL'];outputs=['Y']
    elif family=='d_flipflop':inputs=['D','CLK'];outputs=['Q','Q_N']
    elif family=='counter':inputs=['CLK','RESET','EN'];outputs=[f'Q{i}' for i in range(max(1,math.ceil(math.log2(p['modulus']))))]
    elif family=='adc':inputs=['AIN','CLK','VREF'];outputs=[f'D{i}' for i in range(int(p['bits']))]
    elif family=='dac':inputs=[f'D{i}' for i in range(int(p['bits']))]+['VREF'];outputs=['AOUT']
    elif family in ('opamp_one_pole','comparator_ic'):inputs=['IN+','IN-'];outputs=['OUT'];power=['V+','V-']
    elif family=='schmitt':inputs=['IN'];outputs=['OUT']
    elif family=='level_translator':inputs=['IN'];outputs=['OUT'];power=['VCCA','VCCB','GND']
    elif family=='isolation_amplifier':inputs=['IN+','IN-'];outputs=['OUT'];power=['VDD1','GND1','VDD2','GND2']
    else:return None
    pins=[]
    for role,names,side in [('input',inputs,'west'),('output',outputs,'east'),('power',power,'west')]:
        for name in names:pins.append({'number':str(len(pins)+1),'name':name,'role':role,'side':side})
    return {'pins':pins,'numbering':'generic logical order; NOT package pin numbers',
            'execution':record['status'],'power_behavior':'declared interface only; not coupled to circuit MNA'}


def preview_height(record):
    contract=pin_contract(record)
    if contract is None:return 210
    return max(240,110+28*max(sum(p['side']==s for p in contract['pins']) for s in ('west','east')))
