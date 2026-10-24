# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys,json,hashlib,copy,tempfile
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.script_runtime import run_python_script
from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.service_project_handlers import handle_project_request
OUT=ROOT/'output/promo-drone-20261023/thermal';OUT.mkdir(parents=True,exist_ok=True)
SRC=ROOT/'output/promo-drone-20261023/source/ProPrj_IRIS.kicad_pcb'
HERE=Path(__file__).parent

def write(n,v):(OUT/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
 (OUT/'.tmp').mkdir(exist_ok=True);tempfile.tempdir=str(OUT/'.tmp');d=import_kicad_design(str(SRC));assert not d.stackup
 original=json.loads((ROOT/'examples/thermal/ebrake1_layered_transient.json').read_text())['request'];original['components']=[{'component_ref':ref,'power_w':power,'contact_mode':'pads','r_junction_case_k_w':2.,'r_case_board_k_w':5.} for ref,power in [('U33',.6),('U9',.2),('U15',.2)]]
 blocked=[]
 for kind in ['transient','virtual-sink']:
  q=copy.deepcopy(original)
  if kind=='virtual-sink':q.pop('transient');q['virtual_heatsinks']=[{'id':'sink','face':'top','x_mm':163.,'y_mm':121.,'width_mm':30.,'height_mm':20.,'interface_resistance_k_w':1.,'sink_to_ambient_k_w':8.}]
  try:
   outcome=run_board_thermal(d,q);assert outcome.get('status')=='blocked',outcome;blocked.append({'kind':kind,'result':outcome,'request':q})
  except ValueError as e:blocked.append({'kind':kind,'message':str(e),'request':q})
 write('blocked-transient-sink.json',{'source_stackup_missing':True,'blocked':blocked,'no_stackup_invented':True})
 code=(HERE/'drone_thermal_gui.py').read_text();execution=run_python_script({'code':code,'design':d.to_dict(),'working_directory':str(HERE.resolve()),'filename':'drone_thermal_gui.py','timeout_seconds':120});write('python-workspace-execution.json',execution)
 assert execution['status']=='completed',execution
 marker='SPIKE_DRONE_THERMAL_RESULT=';line=next(x for x in execution['stdout'].splitlines() if x.startswith(marker));r=json.loads(line[len(marker):]);q=r['provenance']['request']
 assert abs(r['summary']['total_power_w']-1.)<1e-12;assert abs(r['summary']['energy_balance_error_w'])<1e-8
 write('request.json',q);write('result.json',r)
 snapshot={'format':'spike-project-package/v2','project':{'name':'IRIS supplied-loss steady plate'},'design':{'source_file':'ProPrj_IRIS.kicad_pcb','source_format':'kicad_pcb','source_board':SRC.read_text(encoding='utf-8')},'analysis':{'mode':'DC IR Drop','pi_setup':{},'view_mode':'3D','show_models':False},'thermal':{'scenario':{'mode':'board','board_thermal_request':q,'board_thermal_result':r}},'studies':[]}
 p=OUT/'iris-steady-thermal.spike';resp=handle_project_request('write_project_package',{'path':str(p),'snapshot':snapshot,'generate_geometry_tables':False},request_id='drone-showcase',application_version='promo-source');assert resp['ok'],resp
 opened=handle_project_request('read_project_package',{'path':str(p)},request_id='drone-showcase',application_version='promo-source');assert opened['ok'];saved=opened['result']['project'];assert saved['thermal']['scenario']['board_thermal_request']==q;assert saved['thermal']['scenario']['board_thermal_result']==r;assert saved['design']['source_board']==SRC.read_text(encoding='utf-8')
 write('verification.json',{'status':'passed','native_steady_project_readback':'exact request/result/source','registered_python_api_run':'completed','actual_footprint_heat_sources':[{k:c.get(k) for k in ('reference','value','at','library')} for c in d.components if c.get('reference') in ['U33','U9','U15']],'source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'source_layer_names':[x['name'] for x in d.layers if x['name'].endswith('.Cu')],'physical_stackup':d.stackup,'source_thickness_mm':1.6,'summary':r['summary'],'transient_and_virtual_sink':'blocked: missing explicit physical stackup','production_qualified':False,'runtime_template_sha256':hashlib.sha256((HERE/'drone_thermal_gui.py').read_bytes()).hexdigest()})
 print(json.dumps(r['summary']))
if __name__=='__main__':main()



