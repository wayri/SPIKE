"""Original generic engineering presets, not a collection of qualified vendor models.

Native recipes are explicitly separate from sampled/equation bench models.
Every variant changes a declared physical parameter, not just a part number.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
import re
import numpy as np

CONTRACT='spikes/component-catalog/v1'
# Family, sweep parameter, base value, unit. 50 logarithmically spaced presets
# cover 0.1..10 x base; bounded/discrete parameters use explicit grids below.
FAMILIES={
 'Passives':[('resistor','r',1000,'ohm'),('capacitor','c',1e-6,'F'),('inductor','l',1e-3,'H'),('supercapacitor','c',10,'F'),('ntc','r',10000,'ohm'),('ptc','r',100,'ohm'),('linear_thermistor','r',1000,'ohm'),('fuse','rating',1,'A'),('cable','r',.1,'ohm'),('crystal_equivalent','frequency',1e6,'Hz')],
 'Discrete':[('diode','is',1e-12,'A'),('photodiode','responsivity',.5,'A/W'),('npn','beta',100,'1'),('pnp','beta',100,'1'),('nmos_enhancement','k',.1,'A/V2'),('pmos_enhancement','k',.1,'A/V2'),('nmos_depletion','k',.1,'A/V2'),('jfet','idss',.01,'A'),('mesfet','idss',.01,'A'),('diac','breakover',30,'V')],
 'Active':[('gan_channel','k',2,'A/V2'),('sic_channel','k',1,'A/V2'),('igbt_channel','r',.1,'ohm'),('thyristor','holding',.01,'A'),('triac','holding',.02,'A'),('led','is',1e-20,'A'),('optocoupler','ctr',.5,'1'),('analog_switch','r',1,'ohm'),('efuse','rating',2,'A'),('load_switch','r',.05,'ohm')],
 'Analog':[('gain','gain',10,'1'),('buffer','gain',1,'1'),('comparator','threshold',1,'V'),('limiter','limit',5,'V'),('integrator','gain',100,'1/s'),('differentiator','gain',.001,'s'),('transconductance','gain',.001,'A/V'),('sample_hold','period',.001,'s'),('precision_rectifier','gain',1,'1'),('lookup_table','gain',1,'1')],
 'Digital':[('and','vdd',3.3,'V'),('or','vdd',3.3,'V'),('not','vdd',3.3,'V'),('nand','vdd',3.3,'V'),('nor','vdd',3.3,'V'),('xor','vdd',3.3,'V'),('xnor','vdd',3.3,'V'),('d_flipflop','vdd',3.3,'V'),('counter','modulus',16,'1'),('mux2','vdd',3.3,'V')],
 'Basic RF':[('rc_lowpass','frequency',1000,'Hz'),('rc_highpass','frequency',1000,'Hz'),('rlc_lowpass','frequency',1e6,'Hz'),('rlc_highpass','frequency',1e6,'Hz'),('bandpass','frequency',1e6,'Hz'),('notch','frequency',1e6,'Hz'),('attenuator','loss_db',10,'dB'),('termination','r',50,'ohm'),('line_lumped_section','delay',1e-9,'s'),('envelope_detector','frequency',1000,'Hz')],
 'Integrated IC':[('opamp_one_pole','gain',1e5,'1'),('comparator_ic','threshold',1.65,'V'),('adc','bits',12,'bit'),('dac','bits',12,'bit'),('timer_astable','frequency',1000,'Hz'),('schmitt','threshold',1.65,'V'),('level_translator','vdd',3.3,'V'),('isolation_amplifier','gain',1,'1'),('voltage_reference','voltage',2.5,'V'),('oscillator','frequency',1e6,'Hz')],
 'Basic PMIC':[('buck_averaged','efficiency',.9,'1'),('boost_averaged','efficiency',.9,'1'),('buck_boost_averaged','efficiency',.9,'1'),('linear_regulator','voltage',3.3,'V'),('voltage_supervisor','threshold',3,'V'),('current_limiter','rating',1,'A'),('battery_charger_cccv','rating',1,'A'),('soft_start','period',.01,'s'),('uvlo','threshold',8,'V'),('pwm_controller','frequency',100000,'Hz')],
 'Energy':[('battery_liion','capacity_ah',2,'Ah'),('battery_lifepo4','capacity_ah',20,'Ah'),('battery_leadacid','capacity_ah',40,'Ah'),('battery_nimh','capacity_ah',2,'Ah'),('battery_nicd','capacity_ah',1,'Ah'),('battery_alkaline','capacity_ah',2,'Ah'),('solar_cell','photocurrent',1,'A'),('wind_turbine','area',1,'m2'),('hydro_turbine','efficiency',.8,'1'),('generator','ke',.1,'V/(rad/s)')],
 'Electromechanical':[('dc_motor','kt',.1,'N m/A'),('bldc_averaged','kt',.1,'N m/A'),('stepper_torque','kt',.1,'N m/A'),('solenoid','gradient',.01,'H/m'),('spring','stiffness',100,'N/m'),('mass_damper','mass',1,'kg'),('fan','coefficient',1e-5,'N m/(rad/s)2'),('pump','efficiency',.8,'1'),('ideal_transformer','ratio',1,'1'),('saturating_inductor','l',.001,'H')],
}
NATIVE={'resistor','capacitor','inductor','supercapacitor','cable','diode','led','rc_lowpass','rc_highpass','termination','line_lumped_section','voltage_reference','attenuator'}
BATTERY_VOLTAGES={'battery_liion':(3.,4.2),'battery_lifepo4':(2.5,3.65),'battery_leadacid':(10.5,12.8),'battery_nimh':(1.,1.4),'battery_nicd':(1.,1.4),'battery_alkaline':(.8,1.6)}
COMMON_LIMITATION='Original generic approximation; not fitted to a named product, not safety-qualified. No package parasitics, thermal network, aging, statistical spread or breakdown unless explicitly stated. Pin/input units are SI.'


def catalog():
    records=[]
    for category,families in FAMILIES.items():
        for family,param,base,unit in families:
            for i in range(50):
                value=base*10**(-1+2*i/49)
                if param=='efficiency':value=.5+i*.49/49
                if param=='bits':value=2+i%25
                if param=='modulus':value=2+i
                params={param:value}
                if param=='bits':params['vref']=1.8 if i<25 else 5.
                if family=='lookup_table':params.update(x=[-1.,0.,1.],y=[-value,0.,value])
                if family in BATTERY_VOLTAGES:params.update(r=.05,soc_initial=.8)
                ident=f'generic.{family}.{i+1:03d}'
                records.append({'id':ident,'category':category,'family':family,'name':family.replace('_',' ').title()+f' · {value:.5g} {unit}'+(f" · Vref={params['vref']:g}V" if 'vref' in params else ''),
                    'parameters':params,'parameter_unit':unit,'status':'native_subcircuit' if family in NATIVE else 'equation_bench_only',
                    'manufacturer':None,'fidelity':'generic_reduced_order','license':'Original SPIKES project contribution; repository license',
                    'limitations':COMMON_LIMITATION+(' Equation bench only: not connected to circuit MNA.' if family not in NATIVE else ' Native recipe uses R/L/C, independent sources or static Shockley diode only.'),
                    'qualification':'unqualified_presets','origin':'deterministic engineering parameter grid v1'})
    return {'contract':CONTRACT,'version':'1.0.0','records':records,
            'counts':dict(Counter(r['category'] for r in records)),
            'archetype_count':sum(map(len,FAMILIES.values())),
            'notice':'500 presets per category from 10 archetypes each; NOT 500 distinct validated component models per category.'}


def validate_record(record):
    if not isinstance(record,dict) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',record.get('id','')):raise ValueError('Invalid catalog ID')
    if record.get('family') not in {f[0] for rows in FAMILIES.values() for f in rows}:raise ValueError('Unknown model family')
    params=record['parameters']
    if len(params)>32:raise ValueError('Too many model parameters')
    for name,value in params.items():
        values=value if isinstance(value,list) else [value]
        if not values or len(values)>4096 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('Parameters must be bounded finite numbers')
    family=record['family'];key=next(row[1] for rows in FAMILIES.values() for row in rows if row[0]==family)
    allowed={key}|({'x','y'} if family=='lookup_table' else {'r','soc_initial'} if family in BATTERY_VOLTAGES else {'vref'} if key=='bits' else set())
    if set(params)!=allowed:raise ValueError('Parameter names must exactly match this archetype: '+', '.join(sorted(allowed)))
    if params[key]<=0:raise ValueError('Primary parameter must be positive')
    if key=='efficiency' and params[key]>1:raise ValueError('Efficiency must be <= 1')
    if key in ('bits','modulus') and (params[key]!=int(params[key]) or params[key]>64):raise ValueError('Bit width/modulus must be an integer <= 64')
    if family in BATTERY_VOLTAGES and (params['r']<=0 or not 0<=params['soc_initial']<=1):raise ValueError('Battery R must be positive and initial SOC in [0,1]')
    if key=='bits' and params['vref']<=0:raise ValueError('Converter reference must be positive')
    if family=='lookup_table':
        if len(params['x'])!=len(params['y']) or len(params['x'])<2 or any(b<=a for a,b in zip(params['x'],params['x'][1:])):raise ValueError('LUT x coordinates must strictly increase and match y')


def native_recipe(record):
    validate_record(record);f=record['family'];p=record['parameters']
    if f not in NATIVE:raise ValueError('Equation bench model: native circuit stamping is not implemented for this family')
    pins=['P','N'];lines=[]
    if f in ('resistor','cable','termination'):lines=[f"R1 P N {p['r']:.17g}"]
    elif f in ('capacitor','supercapacitor'):
        lines=[f"C1 P N {p['c']:.17g}"]
        if f=='supercapacitor':lines=['R_ESR P internal 0.02',f"C1 internal N {p['c']:.17g}",'R_LEAK internal N 1Meg']
    elif f=='inductor':lines=[f"L1 P N {p['l']:.17g}"]
    elif f in ('diode','led'):lines=[f".model DJ D(IS={p['is']:.17g} N={2 if f=='led' else 1})",'D1 P N DJ']
    elif f=='voltage_reference':lines=[f"V1 internal N {p['voltage']:.17g}",'R1 internal P 1']
    elif f in ('rc_lowpass','rc_highpass'):
        pins=['IN','OUT','REF'];c=1/(2*math.pi*1000*p['frequency'])
        lines=['R1 IN OUT 1000',f'C1 OUT REF {c:.17g}'] if f=='rc_lowpass' else [f'C1 IN OUT {c:.17g}','R1 OUT REF 1000']
    elif f=='attenuator':
        pins=['IN','OUT','REF'];ratio=10**(-p['loss_db']/20);lines=[f'R1 IN OUT {1000*(1/ratio-1):.17g}','R2 OUT REF 1000']
    elif f=='line_lumped_section':
        pins=['IN','OUT','REF'];lines=[f"L1 IN OUT {50*p['delay']:.17g}",f"C1 OUT REF {p['delay']/50:.17g}"]
    name='SPK_'+record['id'].replace('.','_')
    prelude=''
    if f in ('diode','led'):
        prelude=lines.pop(0).replace('DJ',name+'_DJ')+'\n';lines=[line.replace('DJ',name+'_DJ') for line in lines]
    return {'name':name,'pins':pins,'source':prelude+f'.subckt {name} '+ ' '.join(pins)+'\n'+'\n'.join(lines)+f'\n.ends {name}\n'}


def evaluate(record,inputs=None,state=None,dt=1e-4):
    """Explicit sampled bench evaluation, finite inputs/state and returned SI units.

    Ideal stateful blocks use sampled updates, not implicit circuit DAE stamping.
    """
    validate_record(record);u=dict(inputs or {});s=dict(state or {});p=record['parameters'];f=record['family']
    if not math.isfinite(dt) or not 0<dt<=1:raise ValueError('Bench step must be in (0,1] seconds')
    for values in (u,s):
        if len(values)>64 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values.values()):raise ValueError('Inputs/state must be finite scalar SI values')
    v=u.get('voltage',0.);i=u.get('current',0.);x=u.get('x',0.);t=u.get('time_s',0.);out={};alerts=[]
    def emit(name,value,unit):
        if not math.isfinite(value):raise ValueError('Model produced a nonfinite result; outside validity envelope')
        out[name]={'value':float(value),'unit':unit}
    if f in ('resistor','cable','termination'):emit('current',v/p['r'],'A')
    elif f in ('capacitor','supercapacitor'):s['voltage']=s.get('voltage',0.)+i*dt/p['c'];emit('voltage',s['voltage'],'V')
    elif f in ('inductor','saturating_inductor'):
        if f=='saturating_inductor':
            # Flux as the state; monotonic bounded incremental inductance.
            s['flux']=s.get('flux',0.)+v*dt;current=s['flux']/p['l'];emit('current',current+.1*current**3,'A');emit('flux_linkage',s['flux'],'Wb turn')
        else:s['current']=s.get('current',0.)+v*dt/p['l'];emit('current',s['current'],'A')
    elif f in ('ntc','ptc','linear_thermistor'):
        temp=u.get('temperature_k',298.15)
        if not 100<=temp<=600:raise ValueError('Thermistor bench envelope: 100..600 K')
        r=p['r']*(math.exp(3950*(1/temp-1/298.15)) if f=='ntc' else 1+.00385*(temp-298.15))
        if r<=0:raise ValueError('Linear temperature approximation gave nonpositive R')
        emit('resistance',r,'ohm');emit('current',v/r,'A')
    elif f in ('fuse','efuse'):
        s['i2t']=s.get('i2t',0.)+i*i*dt;s['tripped']=float(bool(s.get('tripped',0)) or (s['i2t']>=p['rating']**2 if f=='fuse' else abs(i)>p['rating']))
        emit('open',s['tripped'],'bool');emit('i2t',s['i2t'],'A2 s')
        if s['tripped']:alerts.append('TRIPPED: generic threshold model, not a certified protection curve')
    elif f in ('diode','led'):
        exponent=v/((2 if f=='led' else 1)*.02569)
        if exponent>40:raise ValueError('Static exponential bench exceeds 40 thermal voltages; use a qualified series-resistance model')
        emit('current',p['is']*math.expm1(max(-80,exponent)),'A')
    elif f=='photodiode':emit('photocurrent',max(0,u.get('optical_w',0))*p['responsivity'],'A')
    elif f in ('npn','pnp'):emit('collector_current',(1 if f=='npn' else -1)*p['beta']*max(0,u.get('base_current',0)),'A')
    elif f in ('nmos_enhancement','pmos_enhancement','nmos_depletion','gan_channel','sic_channel'):
        sign=-1 if f=='pmos_enhancement' else 1;over=max(0,sign*u.get('vgs',0)-(-2 if f=='nmos_depletion' else 2));vd=abs(v);channel=p['k']*(over*vd-.5*vd*vd if vd<over else .5*over**2)
        emit('drain_current',math.copysign(channel,v),'A')
    elif f in ('jfet','mesfet'):emit('drain_current',math.copysign(p['idss']*max(0,min(1,1+u.get('vgs',0)/4))**2,v),'A')
    elif f in ('diac','thyristor','triac'):
        on=abs(v)>p.get('breakover',30) if f=='diac' else bool(u.get('gate',0)) or bool(s.get('on',0)) and abs(i)>p['holding']
        s['on']=float(on);emit('on',s['on'],'bool')
    elif f in ('igbt_channel','analog_switch','load_switch'):emit('current',v/p['r'] if u.get('gate',0)>2 else v/1e9,'A')
    elif f=='optocoupler':emit('collector_current',max(i,0)*p['ctr'],'A')
    elif f in ('gain','buffer','isolation_amplifier','transconductance','precision_rectifier'):
        emit('output',p['gain']*(abs(x) if f=='precision_rectifier' else x),'A' if f=='transconductance' else 'V')
    elif f in ('comparator','comparator_ic','voltage_supervisor','uvlo','schmitt'):
        threshold=p['threshold'];h=.05*threshold if f in ('schmitt','uvlo') else 0
        s['on']=float(x>threshold-h if s.get('on',0) else x>threshold+h);emit('output',3.3*s['on'],'V')
    elif f=='limiter':emit('output',max(-p['limit'],min(p['limit'],x)),'V')
    elif f=='integrator':s['output']=s.get('output',0)+p['gain']*x*dt;emit('output',s['output'],'V')
    elif f=='differentiator':emit('output',p['gain']*(x-s.get('previous',x))/dt,'V');s['previous']=x
    elif f=='sample_hold':
        if t>=s.get('next',0):s['held']=x;s['next']=t+p['period']
        emit('output',s.get('held',0),'V')
    elif f=='lookup_table':emit('output',float(np.interp(x,p['x'],p['y'])),'V')
    elif f in {row[0] for row in FAMILIES['Digital']}:
        supply=p.get('vdd',3.3);a=u.get('a',0)>supply/2;b=u.get('b',0)>supply/2;clk=u.get('clock',0)>supply/2
        if f in ('d_flipflop','counter'):
            if clk and not s.get('clock',0):s['value']=float(a) if f=='d_flipflop' else (s.get('value',0)+1)%int(p['modulus'])
            s['clock']=float(clk);emit('output',s.get('value',0)*(supply if f=='d_flipflop' else 1),'V' if f=='d_flipflop' else 'count')
        else:
            result={'and':a and b,'or':a or b,'not':not a,'nand':not(a and b),'nor':not(a or b),'xor':a!=b,'xnor':a==b,'mux2':b if u.get('select',0)>supply/2 else a}[f];emit('output',supply*result,'V')
    elif f in ('adc','dac'):
        top=2**int(p['bits'])-1;ref=p['vref'];emit('code' if f=='adc' else 'voltage',round(max(0,min(1,x/ref))*top) if f=='adc' else max(0,min(top,round(x)))*ref/top,'count' if f=='adc' else 'V')
    elif f in ('timer_astable','oscillator','pwm_controller'):
        duty=max(0,min(1,u.get('duty',.5)));emit('output',3.3*float((t*p['frequency'])%1<duty),'V')
    elif f=='level_translator':emit('output',p['vdd']*float(x>1.65),'V')
    elif f=='voltage_reference':emit('voltage',p['voltage'],'V')
    elif f=='opamp_one_pole':
        target=max(-15,min(15,p['gain']*x));alpha=-math.expm1(-dt*2*math.pi*1e6/p['gain']);s['output']=s.get('output',0)+alpha*(target-s.get('output',0));emit('output',s['output'],'V')
    elif f in ('buck_averaged','boost_averaged','buck_boost_averaged'):
        duty=u.get('duty',.5)
        if not 0<=duty<.99:raise ValueError('Averaged converter duty envelope: 0 <= D < .99')
        vo=v*(duty if f=='buck_averaged' else 1/(1-duty) if f=='boost_averaged' else -duty/(1-duty));emit('voltage',vo,'V');emit('input_power',abs(vo*i)/p['efficiency'],'W')
    elif f=='linear_regulator':
        vo=max(0,min(p['voltage'],v-.3));emit('voltage',vo,'V');emit('dissipation',max(0,v-vo)*max(i,0),'W')
    elif f in ('current_limiter','battery_charger_cccv'):emit('current',max(0,min(p['rating'],(4.2-v)*10)) if f=='battery_charger_cccv' else max(-p['rating'],min(p['rating'],i)),'A')
    elif f=='soft_start':emit('output',min(1,max(0,t/p['period'])),'1')
    elif f in BATTERY_VOLTAGES:
        soc=s.get('soc',p['soc_initial'])-i*dt/(3600*p['capacity_ah']);s['soc']=max(0,min(1,soc));lo,hi=BATTERY_VOLTAGES[f]
        emit('voltage',lo+(hi-lo)*s['soc']-i*p['r'],'V');emit('soc',s['soc'],'1')
        if not 0<soc<1:alerts.append('SOC boundary reached; linear OCV model excludes chemistry and thermal runaway')
    elif f=='solar_cell':emit('current',p['photocurrent']*max(0,u.get('irradiance',1000))/1000-1e-10*math.expm1(max(-80,min(40,v/.04))),'A')
    elif f=='wind_turbine':emit('power',.5*1.225*p['area']*max(0,u.get('speed',0))**3*.4,'W')
    elif f=='hydro_turbine':emit('power',1000*9.80665*max(0,u.get('head',0))*max(0,u.get('flow',0))*p['efficiency'],'W')
    elif f=='generator':emit('voltage',p['ke']*u.get('speed',0),'V');emit('torque',p['ke']*i,'N m')
    elif f in ('dc_motor','bldc_averaged','stepper_torque'):
        torque=p['kt']*i*(math.sin(u.get('angle',0)) if f=='stepper_torque' else 1);emit('torque',torque,'N m');emit('back_emf',p['kt']*u.get('speed',0),'V')
    elif f=='solenoid':emit('force',.5*i*i*p['gradient'],'N')
    elif f=='spring':emit('force',-p['stiffness']*x,'N')
    elif f=='mass_damper':s['velocity']=s.get('velocity',0)+(u.get('force',0)-s.get('velocity',0))*dt/p['mass'];s['position']=s.get('position',0)+s['velocity']*dt;emit('position',s['position'],'m');emit('velocity',s['velocity'],'m/s')
    elif f=='fan':emit('torque',p['coefficient']*u.get('speed',0)*abs(u.get('speed',0)),'N m')
    elif f=='pump':emit('input_power',u.get('pressure',0)*u.get('flow',0)/p['efficiency'],'W')
    elif f=='ideal_transformer':emit('secondary_voltage',v*p['ratio'],'V');emit('primary_current',i*p['ratio'],'A')
    else:
        # Linear frequency-domain bench, not a time-domain RF transient model.
        frequency=u.get('frequency_hz',1000)
        if frequency<0:raise ValueError('Frequency must be nonnegative')
        w=frequency/p.get('frequency',1e6);z=1j*w
        if f in ('rc_lowpass','envelope_detector'):h=1/(1+z)
        elif f=='rc_highpass':h=z/(1+z)
        elif f=='rlc_lowpass':h=1/(1+z+z*z)
        elif f=='rlc_highpass':h=z*z/(1+z+z*z)
        elif f=='bandpass':h=z/(1+z+z*z)
        elif f=='notch':h=(1+z*z)/(1+z+z*z)
        elif f=='attenuator':h=complex(10**(-p['loss_db']/20))
        elif f=='line_lumped_section':h=complex(np.exp(-2j*math.pi*frequency*p['delay']))
        elif f=='crystal_equivalent':h=1/(1+1j*1000*(w-1/max(w,1e-12)))
        else:raise ValueError('Unimplemented bench family '+f)
        emit('magnitude',abs(h),'1');emit('phase',math.degrees(math.atan2(h.imag,h.real)),'degree')
    if any(not math.isfinite(v) for v in s.values()):raise ValueError('Nonfinite model state')
    return {'outputs':out,'state':s,'alerts':alerts,'domain':'sampled_equation_bench','not_circuit_coupled':True,'limitations':record['limitations']}


def materialize(path):
    from .document import write_json
    payload=catalog();write_json(path,payload);return payload
