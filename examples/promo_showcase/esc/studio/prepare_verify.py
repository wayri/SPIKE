# SPDX-License-Identifier: Apache-2.0
"""Prepare native graphical Studio examples and execute owned engine checks."""
from pathlib import Path
import sys,json,hashlib,math,tempfile,time
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]
from spikes_studio.document import Document
from spikes_studio.dashboard import widget
from spikes_studio.run_control import native_batch,InteractiveRun
from spikes_studio.controller_block import Controller
HERE=Path(__file__).parent;OUT=ROOT/'output/promo-esc-20261023/studio';OUT.mkdir(parents=True,exist_ok=True)
tempfile.tempdir=str(OUT)
LIB=ROOT/'app/src-tauri/resources/worker/spike-worker/_internal/spikes/spikes_c_api.dll'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):(OUT/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
checks=[]
# Packaged native library does not expose analytic SIN; use its supported PWL
# source with explicitly retained samples of the same illustrative 100 Hz input.
path=HERE/'backemf_sensing.cir'
lines=path.read_text().splitlines()
samples=' '.join(f'{i*.0001:.9g} {24*math.sin(2*math.pi*100*i*.0001):.12g}' for i in range(401))
lines=[('Vphase phase 0 PWL('+samples+')') if row.startswith('Vphase ') else row for row in lines]
path.write_text('\n'.join(lines)+'\n')
for name,probes in [('backemf_sensing',['V(phase)','V(divided)','V(adc)']),('current_sensing',['V(shunt)','V(adc)','I(Rshunt)']),('gate_miller_ringing',['V(gate)','V(drain)','I(Lpackage)'])]:
    source=(HERE/f'{name}.cir').read_text();doc=Document.from_netlist(source)
    # Source-authoritative terminal routes: each star joins identical existing nets.
    nets={}
    for part in doc.data['components']:
        for pin,node in enumerate(part['nodes']):nets.setdefault(node,[]).append([part['id'],pin])
    for node,ends in nets.items():
        for end in ends[1:]:doc.connect(ends[0],end)
    widgets=[]
    for i,expression in enumerate(probes):
        doc.add_probe(expression)
        w=widget('Scope',expression);w.update(title=expression,x=i*500,y=0,width=480,height=280);widgets.append(w)
    note=widget('Note');note.update(title='Model scope',x=0,y=300,width=900,height=160,expression='Original illustrative sensing/linear transient, not VESC firmware or a qualified three-phase motor controller.')
    widgets.append(note);doc.data['dashboard']={'version':1,'widgets':widgets}
    doc.data['metadata']['example_limitations']='Explicit ideal supplied excitation, linear sensing or gate RLC; no vendor transistor, ADC, commutation, switching-loss, field or thermal coupling.'
    doc.validate();doc.save(HERE/f'{name}.spksch')
    assert Document.load(HERE/f'{name}.spksch').data['source']==source
    r=native_batch(source,str(LIB));save(name+'-result.json',r);assert r['status']=='completed'
    d=r['data'];t=d['time_s'];v=d['node_voltage_v']
    if name=='backemf_sensing':
        # Check settled last two cycles, exact linear divider and bounded shifted ADC.
        errors=[abs(b-a/21) for a,b in zip(v['phase'],v['divided'])]
        settled=[x for ti,x in zip(t,v['adc']) if ti>=.02]
        assert max(errors)<1e-10 and .45<min(settled)<.6 and 2.7<max(settled)<2.85
        detail={'divider_max_error_v':max(errors),'settled_adc_min_v':min(settled),'settled_adc_max_v':max(settled)}
    elif name=='current_sensing':
        peaks=max(v['shunt']);out=max(v['adc']);assert abs(peaks-.02)<1e-10 and abs(out-1)<1e-6
        detail={'shunt_peak_v':peaks,'adc_peak_v':out}
    else:
        assert max(v['gate'])>10 and min(v['drain'])<1
        detail={'gate_peak_v':max(v['gate']),'gate_minimum_v':min(v['gate'])}
    checks.append({'example':name,'passed':True,'points':len(t),'checks':detail,'graphical_wires':len(doc.data['wires']),'native_project_reopen':'passed'})
# Preserve the already verified firstparty controller project as the separate
# averaged PMDC demonstration. Its embedded source is self-contained.
doc=Document.load(HERE/'two_wheeler_dashboard.spksch')
assert doc.data['controller_setup']['source']==(HERE/'ev_current_controller.c').read_text()
controller=Controller(doc.data['controller_setup'],trusted=True);session=None
try:
    session=InteractiveRun(doc.data['source'],str(LIB),controller=controller,speed_ratio=10,capacity=2000)
    def advance(target):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            result=session.snapshot()
            if session.state=='failed':raise RuntimeError(session.error)
            if result and result['data']['time_s'][-1]>=target:return result
            time.sleep(.02)
        raise TimeoutError('Controller virtual-time capture timeout')
    session.set_source('VTHROTTLE',.3);result=advance(.12)
    d=result['data']['node_voltage_v'];assert d['current'][-1]>0 and d['omega'][-1]>0
    save('motor-controller-throttle-result.json',result)
    session.set_source('VBRAKE',1);result=advance(result['data']['time_s'][-1]+.12)
    assert result['data']['node_voltage_v']['current'][-1]<0
    save('motor-controller-brake-result.json',result)
    checks.append({'example':'averaged_pmdc_controller','passed':True,'checks':['positive throttle current and speed','negative brake current'],'native_project_reopen':'passed'})
finally:
    if session:session.stop();session.thread.join(5)
    controller.close()
save('verification.json',{'checks':checks,'controller_document_reopen':'passed','native_library_path':str(LIB.relative_to(ROOT)).replace('\\','/'),'native_library_sha256':sha(LIB),'production_qualified':False,'source_files':[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sha(p)} for p in HERE.iterdir() if p.is_file()]})
print(json.dumps(checks,indent=2))
