# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from python.spike_core.native_airflow import run_native_cavity
from python.spike_core.laminar_channel_cht import solve_laminar_channel_cht
OUT=ROOT/'output/promo-showcase-20261023/thermal_flow';OUT.mkdir(parents=True,exist_ok=True)
def write(name,v):(OUT/name).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
cfd={'n':16,'reynolds':100.,'max_steps':100000,'steady_tolerance':1e-7,'length_m':1.,'lid_velocity_m_s':1.,'density_kg_m3':1.}
r=run_native_cavity(cfd,timeout_s=180);assert r['status']=='converged';write('native-cavity.request.json',cfd);write('native-cavity.result.json',r)
p=json.loads((ROOT/'examples/thermal/laminar_channel_cht_request.json').read_text());r=solve_laminar_channel_cht(p);assert r['status']=='completed';assert abs(r['energy']['residual_w'])<1e-8;write('channel-cht.request.json',p);write('channel-cht.result.json',r)
write('flow-verification.json',{'status':'passed','native_cavity_converged':True,'cht_energy_residual_w':r['energy']['residual_w'],'native_ui_status':{'cavity':'Manual setup in Native CFD cavity benchmark: grid16, Re100; no JSON importer','cht':'Request-only research API; native GUI does not expose this exact channel CHT owner'},'production_qualified':False})
print('native cavity + channel CHT executed and checked')
