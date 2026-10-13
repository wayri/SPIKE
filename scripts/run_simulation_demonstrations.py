# SPDX-License-Identifier: Apache-2.0
"""Reproducible, supplied-model Arduino studies through the SPIKE worker."""
from pathlib import Path
import sys,json,copy,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from python.spike_core.project_package import read_project
from python.spike_core.headless import run_request
from python.spike_core.multiboard_circuit import compile_multiboard_circuit
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.harness_authoring import validate_harness_connections, discover_connectors
from scripts.build_arduino_shield_acceptance import _pin_mapping
OUT=ROOT/'output/simulation-demonstrations-20261009'
BASE=ROOT/'build/curated-multiboard-20261005/arduino'
def save(path,value): path.write_text(json.dumps(value,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8')
def el(id,t,p,n,**kw):return dict(id=id,type=t,positive_node=p,negative_node=n,**kw)
def circuit(a,domain):
 boards=a['boards'];models=[];links=[];first=boards[0]['id']
 for b in boards:
  bid=b['id'];uno='uno' in bid;p,g,s=('JANALOG:5','JANALOG:6','JDIGITAL:6') if uno else ('POWER0:5','POWER0:6','JLOW0:6')
  elements=[]
  if domain=='pi':
   if bid==first:elements += [el('supply','voltage_source','supply-node',g,dc_value=5),el('source-resistance','resistor','supply-node',p,resistance_ohm=.05)]
   elements += [el('operating-load' if uno else 'relay-bank-load','resistor',p,g,resistance_ohm=25/.35 if uno else 25),el('gpio-bias','resistor',s,g,resistance_ohm=1e6)]
  else:
   if bid==first:elements += [el('gpio-drive','voltage_source','driver-node',g,dc_value=0,ac_magnitude=1),el('driver-resistance','resistor','driver-node',s,resistance_ohm=33)]
   else:elements += [el('input-load','resistor',s,g,resistance_ohm=1000),el('input-capacitance','capacitor',s,g,capacitance_f=10e-12)]
   if len(boards)==1:elements += [el('input-load','resistor',s,g,resistance_ohm=1000),el('input-capacitance','capacitor',s,g,capacitance_f=10e-12)]
   elements += [el('power-bias','resistor',p,g,resistance_ohm=1e6)]
  if not uno and a.get('harnesses'):
   elements += [el('harness-power-path','resistor',p,'JANALOG0:1',resistance_ohm=.02),el('harness-return-path','resistor',g,'JANALOG0:2',resistance_ohm=.02),el('harness-signal-path','resistor',s,'JANALOG0:5',resistance_ohm=.02)]
  models.append({'board_id':bid,'elements':elements})
 for m in a.get('connector_mappings',[]):
  if m['kind']!='connector-mate':continue
  pins=m['data']['pin_map'];digital='digital' in m['id']
  links.append({'link_id':m['id'],'kind':'mate','pins':[{'source_pin':k,'target_pin':v,'resistance_ohm':.02 if digital else .01,'inductance_h':5e-9 if digital else 2e-9} for k,v in pins.items()]})
 for h in a.get('harnesses',[]):
  digital='signal' in h['id'];pins=[]
  for k,v in h['pin_map'].items():
   row={'source_pin':k,'target_pin':v,'resistance_ohm':.0172*.3/.205,'contact_a_resistance_ohm':.01,'contact_b_resistance_ohm':.01,'inductance_h':200e-9}
   if digital:row.update(capacitance_f=30e-12,reference={'board_id':first,'node':'JANALOG:6'})
   pins.append(row)
  links.append({'link_id':h['id'],'kind':'harness','pins':pins})
 return {'contract':'spike/multiboard-circuit-request/v1','domain':domain,'assembly':a,'board_models':models,'link_models':links,'ground':{'board_id':first,'node':'JANALOG:6'},'analysis':{'mode':'operating_point'} if domain=='pi' else {'mode':'ac','start_hz':1e3,'stop_hz':100e6,'points':81,'scale':'log'}}
def native_single(req):
 return {'contract':'spike/native-mna-request/v1','elements':req['board_models'][0]['elements'],'ground_node':'JANALOG:6','analysis':req['analysis'],'resource_limits':{'linear_backend':'scipy-superlu'}}
def check(native,result):
 data=result['data'];freqs=data.get('frequency_hz',[0]);nodes=sorted({e[k] for e in native['elements'] for k in ['positive_node','negative_node']} - {native['ground_node']});idx={n:i for i,n in enumerate(nodes)}
 branches=[e for e in native['elements'] if e['type'] in ['voltage_source','inductor']];maxerr=0.;residual=0.
 for q,f in enumerate(freqs):
  size=len(nodes)+len(branches);a=np.zeros((size,size),complex);z=np.zeros(size,complex);w=2*np.pi*f
  for e in native['elements']:
   p=idx.get(e['positive_node']);n=idx.get(e['negative_node']);t=e['type']
   if t in ['resistor','capacitor']:
    y=1/e['resistance_ohm'] if t=='resistor' else 1j*w*e['capacitance_f']
    for i,j,sgn in [(p,p,1),(n,n,1),(p,n,-1),(n,p,-1)]:
     if i is not None and j is not None:a[i,j]+=sgn*y
   else:
    k=len(nodes)+branches.index(e)
    for i,sgn in [(p,1),(n,-1)]:
     if i is not None:a[i,k]+=sgn;a[k,i]+=sgn
    if t=='inductor':a[k,k]=-1j*w*e['inductance_h']
    else:z[k]=e.get('dc_value',0) if not f else e.get('ac_magnitude',0)*np.exp(1j*np.deg2rad(e.get('ac_phase_deg',0)))
  x=np.linalg.solve(a,z);residual=max(residual,float(np.max(np.abs(a@x-z))))
  for node,i in idx.items():
   v=data['node_voltage_v'][node];actual=v if not f else complex(v['real'][q],v['imaginary'][q]);maxerr=max(maxerr,abs(actual-x[i]))
 assert maxerr<1e-8 and residual<1e-9,(maxerr,residual)
 return {'reference':'Independent NumPy dense complex MNA assembly from the explicit request; not a geometry/hardware qualification','max_node_voltage_error_v':maxerr,'max_kcl_constraint_residual':residual,'samples_checked':len(freqs),'passed':True}
def prepare():
 OUT.mkdir(parents=True,exist_ok=True);opened=read_project(BASE/'arduino-r4-relay-shield.spike',include_members=True);base=copy.deepcopy(opened.payload['assembly_ir']);base['extensions']={};designs=opened.payload['assembly_designs'];
 configs={};single=copy.deepcopy(base);single['assembly_id']='demo-single';single['boards']=single['boards'][:1]
 for field in ['connector_mappings','harnesses','thermal_contacts','parts','electrical_bonds']:single[field]=[]
 configs['single-board']=single;configs['stacked-boards']=copy.deepcopy(base);multi=copy.deepcopy(base);multi['assembly_id']='demo-two-stacks'
 for b in base['boards']:
  row=copy.deepcopy(b);row['id']+='-b';row['name']+=' (stack B)';row['frame']['frame_id']=row['id']+'-frame';row['frame']['transform']=list(row['frame']['transform']);row['frame']['transform'][3]+=180;multi['boards'].append(row)
 for field in ['connector_mappings','thermal_contacts']:
  for old in base[field]:
   row=copy.deepcopy(old);row['id']+='-b'
   for obj in [row,row.get('data',{})]:
    for key in ['board_id','endpoint_a','endpoint_b']:
     if key in obj:
      val=obj[key];obj[key]=val.replace('uno-r4-minima','uno-r4-minima-b').replace('relay-shield','relay-shield-b')
   multi[field].append(row)
 multi['harnesses']=[{'id':'power-harness','name':'300 mm AWG24 power and return','endpoint_a':'relay-shield::JANALOG0','endpoint_b':'relay-shield-b::JANALOG0','length_mm':300,'pin_map':{'1':'1','2':'2'}}, {'id':'signal-harness','name':'300 mm supplied RLC signal','endpoint_a':'relay-shield::JANALOG0','endpoint_b':'relay-shield-b::JANALOG0','length_mm':300,'pin_map':{'5':'5'}}]
 inventory=discover_connectors(AssemblyIRV1.from_dict(multi),{d['design_id']:d for d in designs['designs']})
 shield_design=next(d for d in designs['designs'] if any(c['reference']=='POWER0' for c in d['components']))
 for board in ['relay-shield','relay-shield-b']:
  multi['connector_mappings'].append(_pin_mapping(board,'JANALOG0',('1','2','5'),inventory,shield_design))
 configs['harness-stacks']=multi
 for slug,a in configs.items():
  folder=OUT/slug;folder.mkdir(exist_ok=True);AssemblyIRV1.from_dict(a);validate_harness_connections(AssemblyIRV1.from_dict(a))
  save(folder/'assembly.json',a);save(folder/'designs.json',designs);save(folder/'source-provenance.json',json.loads((BASE/'source-provenance.json').read_text(encoding='utf-8')))
  reqs={d:circuit(a,d) for d in ['pi','si']};scenario={'id':slug,'name':{'single-board':'Single Arduino UNO R4 Minima','stacked-boards':'Arduino UNO R4 Minima + relay shield stack','harness-stacks':'Two Arduino/shield stacks with power, return and signal harnesses'}[slug],'board_ids':[b['id'] for b in a['boards']],'stack_pairs':[['uno-r4-minima','relay-shield']]+([['uno-r4-minima-b','relay-shield-b']] if slug=='harness-stacks' else []) if slug!='single-board' else [],'thermal_contact_ids':[c['id'] for c in a.get('thermal_contacts',[])],'execution':'SPIKE current source worker via supervised headless API, not native GUI verified','single_board':slug=='single-board','board_elements':reqs['pi']['board_models'],'assumptions':['5 V source, explicit 50 mOhm source resistance','UNO operating-load resistance 25/.35 ohm, relay load25ohm; not extracted from board component operating points','SI1V small signal ideal driver with33ohm impedance; each receiver1kohm +10pF','Connector R/L and cable R/L/C are supplied reduced models; no routed copper extraction, distributed delay, mutual coupling or EMI radiation','Cable: AWG24 area .205mm2, copper resistivity .0172ohm mm2/m at20C, length .3m, two10mohm contacts per wire, explicit200nH and30pF signal capacitance','Thermal is one-way PI dissipation deposition with explicit RC/contact/radiosity assumptions, not iterative temperature feedback or3D FEA/CFD']}
  save(folder/'scenario.json',scenario)
  for d,req in reqs.items():save(folder/f'{d}-request.json',native_single(req) if slug=='single-board' else req)
 print('Fixtures ready',flush=True)
def run():
 for folder in [OUT/s for s in ['single-board','stacked-boards','harness-stacks']]:
  scenario=json.loads((folder/'scenario.json').read_text());valid={}
  for domain in ['pi','si']:
   req=json.loads((folder/f'{domain}-request.json').read_text());method='run_native_mna' if scenario['single_board'] else 'run_multiboard_circuit';envelope=run_request({'method':method,'params':{'request':req}},timeout_seconds=180);save(folder/f'{domain}-worker-envelope.json',envelope)
   if not envelope.get('ok'):raise RuntimeError(envelope)
   result=envelope['result'];assert result['status']=='completed',result;save(folder/f'{domain}-result.json',result)
   native=req if scenario['single_board'] else compile_multiboard_circuit(req)['native_request'];save(folder/f'{domain}-native-request.json',native);valid[domain]=check(native,result if scenario['single_board'] else result['native_result'])
   print(folder.name,domain,'completed',flush=True)
  pi=json.loads((folder/'pi-result.json').read_text());raw=pi if scenario['single_board'] else pi['native_result'];pw=raw['data']['element_power_w'];source=sum(-v for v in pw.values() if v<0);loss=sum(v for v in pw.values() if v>0);valid['pi']['power_input_w']=source;valid['pi']['power_dissipated_w']=loss;valid['pi']['power_balance_error_w']=abs(source-loss);assert abs(source-loss)<1e-9
  save(folder/'electrical-validation.json',valid)
if __name__=='__main__':
 prepare();run()
