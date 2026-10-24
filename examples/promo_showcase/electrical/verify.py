# SPDX-License-Identifier: Apache-2.0
"""Run original electrical showcase examples without changing physics."""
from pathlib import Path
import sys,json,hashlib,copy,time,tempfile
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]
from python.spike_core.em_machines import run_machine
from python.spike_core.magnetic_machine_study import run_magnetic_machine
from spikes_studio.run_control import native_batch, InteractiveRun
from spikes_studio.document import Document
from spikes_studio.controller_block import Controller
HERE=Path(__file__).parent
OUT=ROOT/'output/promo-showcase-20261023/electrical'
OUT.mkdir(parents=True,exist_ok=True)
tempfile.tempdir=str(OUT)
LIB=ROOT/'app/src-tauri/resources/worker/spike-circuit-worker/_internal/spikes/spikes_c_api.dll'
def save(name,value): (OUT/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
for name in ('02_rc_startup','03_rl_startup','gate_miller_ringing'):
    result=native_batch((HERE/'studio'/f'{name}.cir').read_text(),str(LIB))
    save(name+'-result.json',result)
    assert result['status']=='completed',result
    checks.append({'example':name,'passed':True,'status':result['status']})
for name in ('motor','electromagnet','electromagnet-air'):
    request=json.loads((HERE/'magnetics'/f'{name}.json').read_text())
    result=run_machine(request);save(name+'-result.json',result)
    assert result['status']=='completed' and result['production_qualified'] is False
    checks.append({'example':name,'passed':True,'request_sha256':result['request_sha256'],'summary':result['summary']})
for name in ('planar_pm_fem','planar_solenoid_fem'):
    request=json.loads((HERE/'magnetics'/f'{name}.json').read_text())
    result=run_magnetic_machine(request);save(name+'-result.json',result)
    assert result['production_qualified'] is False
    checks.append({'example':name,'passed':True,'request_sha256':result['request_sha256'],'summary':result['summary']})
# Exact copied native interactive controller project, embedded C source.
doc=Document.load(HERE/'studio/two_wheeler_dashboard.spksch')
controller=Controller(doc.data['controller_setup'],trusted=True); session=None
try:
    session=InteractiveRun(doc.data['source'],str(LIB),controller=controller,speed_ratio=10,capacity=2000)
    session.set_source('VTHROTTLE',.3)
    def advance(target):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            r=session.snapshot()
            if session.state=='failed': raise RuntimeError(session.error)
            if r and r['data']['time_s'][-1]>=target:return r
            time.sleep(.02)
        raise TimeoutError('Interactive motor did not reach target virtual time')
    result=advance(.12);d=result['data']['node_voltage_v']
    assert d['current'][-1]>0 and d['omega'][-1]>0
    save('motor-controller-throttle-result.json',result)
    session.set_source('VBRAKE',1)
    result=advance(result['data']['time_s'][-1]+.12)
    assert result['data']['node_voltage_v']['current'][-1]<0
    save('motor-controller-brake-result.json',result)
    checks.append({'example':'two_wheeler_dashboard','passed':True,'checks':['positive throttle current and acceleration','negative brake current']})
finally:
    if session: session.stop();session.thread.join(5)
    controller.close()
sources=[p for p in HERE.rglob('*') if p.is_file()]
save('verification.json',{'production_qualified':False,'checks':checks,'native_library':{'path':str(LIB.relative_to(ROOT)),'sha256':sha(LIB)},'pack_sources':[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sha(p)} for p in sources]})
print(json.dumps(checks,indent=2))
