# SPDX-License-Identifier: Apache-2.0
"""Existing native ideal-transformer/switch circuit, not magnetic FEM feedback."""
from pathlib import Path
import sys,json,hashlib,math
import numpy as np
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]
from spikes_studio.document import Document
from spikes_studio.dashboard import widget
from spikes_studio.run_control import native_batch
HERE=Path(__file__).parent;OUT=ROOT/'output/promo-planar-magnetics-20261023/converter';OUT.mkdir(parents=True,exist_ok=True)
LIB=ROOT/'app/src-tauri/resources/worker/spike-worker/_internal/spikes/spikes_c_api.dll'
def save(n,v):(OUT/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def deck(duty=.30606204366570683,dt=1e-7,stop=.001):
    fs=100000;period=1/fs;width=duty*period/2+500e-9;ncycles=math.ceil(stop/period)
    def wave(which):
        points=[(0,0)]
        # 100 ns source edges; primary voltage kept zero between polarities.
        edge=100e-9
        for i in range(ncycles+1):
            for shift,sign in ((period*.1,1),(period*.6,-1)):
                t=i*period+shift
                if which=='drive':level=48*sign
                elif which=='gp':level=5 if sign==1 else 0
                elif which=='pol':level=sign
                else:level=5 if sign==-1 else 0
                if which=='drive':
                    points.extend([(t+2*edge,0),(t+3*edge,level),(t+width-3*edge,level),(t+width-2*edge,0)])
                else:points.extend([(t,0),(t+edge,level),(t+width-edge,level),(t+width,0)])
        return 'PWL('+' '.join(f'{t:.12g} {v:.12g}' for t,v in points)+')'
    return '\n'.join(['.title 48 V to 1.8 V 50 W ideal-transformer PWM study',
     '* 8:1 assumed ratio pending winding contract; synthetic bridge excitation.',
     '* E/F pair conserves ideal transformer power; no native K or FEM coupling.',
     'Vbridge bridge 0 '+wave('drive'), 'Rprimary bridge pri 0.05',
     '* Dot convention: P1 positive -> S2 (SEC_B, pins19..34) positive.',
     'Lmag pri 0 364.8u','Etransform sec_b sec_a pri 0 .125','Freflect pri 0 Etransform -.125',
     'Rreference sec_a 0 1G','Vpol pol 0 '+wave('pol'),
     'Brect rect 0 V={V(pol)*V(sec_b,sec_a)}',
     'Brectload sec_b sec_a I={-V(pol)*I(Brect)}',
     'Lout rect filtered 1u','Rlout filtered out .001','Cout out 0 1m','Rload out 0 .0648',
     f'.tran {dt:.12g} {stop:.12g} uic','.end',''])
if __name__=='__main__':
    checks=[]
    for tag,step in [('base',1e-7),('refined',5e-8)]:
        source=deck(dt=step);(HERE/f'converter-{tag}.cir').write_text(source)
        r=native_batch(source,str(LIB),method='backward_euler');save(tag+'-result.json',r)
        assert r['status']=='completed',r
        d=r['data'];inds=[i for i,t in enumerate(d['time_s']) if t>=.0008]
        values=d['node_voltage_v']['out'];v=[values[i] for i in inds]
        ts=np.asarray([d['time_s'][i] for i in inds]);duration=ts[-1]-ts[0]
        def mean(values):return float(np.trapezoid(np.asarray(values)[inds],ts)/duration)
        avg=mean(values);p=mean(d['element_power_w']['RLOAD']);pin=-mean(d['element_power_w']['VBRIDGE'])
        loss=mean(d['element_power_w']['RPRIMARY'])+mean(d['element_power_w']['RLOUT'])
        transformer_error=max(abs(a+b) for a,b in zip(d['element_power_w']['ETRANSFORM'],d['element_power_w']['FREFLECT']))
        rectifier_error=max(abs(a+b) for a,b in zip(d['element_power_w']['BRECT'],d['element_power_w']['BRECTLOAD']))
        ds=np.diff(ts)
        def energy(values):return float(np.asarray(values)[inds][1:]@ds)
        source_energy=-energy(d['element_power_w']['VBRIDGE'])
        dissipated=sum(energy(d['element_power_w'][name]) for name in ('RPRIMARY','RLOUT','RLOAD','RREFERENCE'))
        stored_change=0.;numerical_dissipation=0.
        for coefficient,values in ((364.8e-6,d['element_current_a']['LMAG']),(1e-6,d['element_current_a']['LOUT']),(.001,d['node_voltage_v']['out'])):
            a=np.asarray(values)[inds]
            stored_change+=.5*coefficient*(a[-1]**2-a[0]**2)
            numerical_dissipation+=.5*coefficient*float(np.diff(a)@np.diff(a))
        energy_residual=source_energy-dissipated-stored_change-numerical_dissipation
        assert abs(energy_residual)<1e-7
        assert abs(avg-1.8)<.025 and 48<p<52 and transformer_error<1e-7 and rectifier_error<1e-7
        checks.append({'run':tag,'step_s':step,'average_voltage_v':avg,'ripple_pp_v':max(v)-min(v),'load_current_a':avg/.0648,'load_power_w':p,'input_power_w':pin,'supplied_resistive_loss_w':loss,'trapezoid_power_balance_difference_w':pin-p-loss,'backward_euler_numerical_dissipation_w':numerical_dissipation/duration,'discrete_energy_balance_residual_j':energy_residual,'maximum_ideal_transformer_power_residual_w':transformer_error,'maximum_ideal_rectifier_power_residual_w':rectifier_error,'points':len(d['time_s'])})
    save('checks.json',{'checks':checks,'status':'executed_fixed_duty_at_named_load_not_regulated','production_qualified':False,'native_library_sha256':hashlib.sha256(LIB.read_bytes()).hexdigest(),'limitations':['Prescribed bipolar full-bridge voltage, not solved primary MOSFET/gate/driver circuit.','Energy-conserving ideal dependent-source transformer plus supplied linear magnetizing L; no coupled-inductor K support.','Energy-conserving behavioral ideal synchronous rectifier and zero-voltage freewheel; not four solved device switches.','Fixed duty tuned to named resistive load, no feedback regulator or load transient.','Supplied lumped winding/filter losses; no frequency-dependent copper/core loss or thermal feedback.']})
    assert abs(checks[1]['average_voltage_v']-checks[0]['average_voltage_v'])<.001
    assert abs(checks[1]['ripple_pp_v']-checks[0]['ripple_pp_v'])/checks[1]['ripple_pp_v']<.02
    doc=Document.from_netlist(deck(dt=5e-8));
    doc.data['run_profile'].update(method='backward_euler',time_step='50n',stop_time='1m',capture_samples=50000)
    nets={}
    for part in doc.data['components']:
        for pin,node in enumerate(part['nodes']):nets.setdefault(node,[]).append([part['id'],pin])
    for ends in nets.values():
        for end in ends[1:]:doc.connect(ends[0],end)
    for i,exp in enumerate(['V(out)','I(Lout)','V(pri)']):
        doc.add_probe(exp);w=widget('Scope',exp);w.update(title=exp,x=i*500,y=0);doc.data['dashboard']['widgets'].append(w)
    doc.save(HERE/'converter.spksch')
    assert Document.load(HERE/'converter.spksch').data['source']==deck(dt=5e-8)
    print(json.dumps(checks,indent=2))
