# SPDX-License-Identifier: Apache-2.0
"""Existing native Studio bus/sensing workflows; no new solver or motor physics."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]
from spikes_studio.document import Document
from spikes_studio.dashboard import widget
from spikes_studio.run_control import native_batch
HERE=Path(__file__).parent;OUT=ROOT/'output/promo-propulsion-pod-20261023/electrical';OUT.mkdir(parents=True,exist_ok=True)
LIB=ROOT/'app/src-tauri/resources/worker/spike-worker/_internal/spikes/spikes_c_api.dll'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,value):(OUT/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
checks=[]
source=(HERE/'pod_bus_startup.cir').read_text()
doc=Document.from_netlist(source)
groups={}
for part in doc.data['components']:
    for pin,node in enumerate(part['nodes']):groups.setdefault(node,[]).append([part['id'],pin])
for ends in groups.values():
    for end in ends[1:]:doc.connect(ends[0],end)
for i,expression in enumerate(['V(supply)','V(bus)','I(Iload)']):
    doc.add_probe(expression);w=widget('Scope',expression);w.update(title=expression,x=i*500,y=0,width=480,height=280);doc.data['dashboard']['widgets'].append(w)
doc.data['metadata']['example_limitations']='Supplied 48V bus ramp and ideal current load. Assumed source R/L and capacitor C/ESR. No motor, inverter, propeller, battery chemistry, thermal or field coupling.'
doc.data['run_profile'].update(method='backward_euler',time_step='1u',stop_time='4m',capture_samples=20000)
doc.save(HERE/'pod_bus_startup.spksch')
assert Document.load(HERE/'pod_bus_startup.spksch').data['source']==source
for tag,step in [('base','1u'),('refined','500n')]:
    request=source.replace('.tran 1u 4m uic',f'.tran {step} 4m uic')
    r=native_batch(request,str(LIB),method='backward_euler');save(f'pod-bus-{tag}-result.json',r)
    assert r['status']=='completed',r
    t=np.asarray(r['data']['time_s']);bus=np.asarray(r['data']['node_voltage_v']['bus'])
    light=(t>=.0007)&(t<=.0009);heavy=(t>=.0017)&(t<=.0019);recovered=(t>=.0035)
    light_mean=float(bus[light].mean());heavy_mean=float(bus[heavy].mean());recovery_mean=float(bus[recovered].mean())
    assert abs(light_mean-47.98)<.005 and abs(heavy_mean-47.5)<.005 and abs(recovery_mean-47.98)<.005
    checks.append({'example':'pod_bus_startup','run':tag,'passed':True,'light_load_v':light_mean,'high_load_v':heavy_mean,'recovery_v':recovery_mean,'load_step_droop_v':light_mean-heavy_mean,'oracle':'48 V minus 0.1 ohm times supplied steady current','points':len(t)})
assert abs(checks[0]['high_load_v']-checks[1]['high_load_v'])<.001
assert abs(checks[0]['load_step_droop_v']-checks[1]['load_step_droop_v'])<.001
sense=Document.load(HERE/'current_sensing.spksch')
assert sense.data['source']==(HERE/'current_sensing.cir').read_text()
r=native_batch(sense.data['source'],str(LIB),method='backward_euler');save('current-sensing-result.json',r)
assert r['status']=='completed'
v=r['data']['node_voltage_v'];assert abs(max(v['shunt'])-.02)<1e-10 and abs(max(v['adc'])-1)<1e-6
checks.append({'example':'current_sensing','passed':True,'peak_shunt_v':max(v['shunt']),'peak_ideal_amplifier_output_v':max(v['adc']),'points':len(r['data']['time_s'])})
save('verification.json',{'checks':checks,'native_library':{'path':str(LIB.relative_to(ROOT)).replace('\\','/'),'sha256':sha(LIB)},'native_document_readback':'passed','ui_run':'not_executed','production_qualified':False,'no_new_physics':True,'limitations':['Prescribed bus voltage and load; no motor/ESC or actual pod demand.','Illustrative R/L/C/ESR and ideal current measurement; no sourced hardware ratings or ADC model.','No battery chemistry, switching losses, thrust, rotor fields, airflow or thermal coupling.']})
print(json.dumps(checks,indent=2))
