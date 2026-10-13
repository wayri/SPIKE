# SPDX-License-Identifier: Apache-2.0
"""Package actual SI workflow results with explicitly illustrative channel artwork."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from python.spike_core.contracts import SpiDeR
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.project_package import write_spike_package,read_project
from python.spike_core.project_state_artifacts import hydrate_result_state
from python.spike_core.service_project_handlers import handle_project_request
OUT=ROOT/'output/high-speed-si/projects';OUT.mkdir(parents=True,exist_ok=True)
summary=json.loads((ROOT/'examples/high_speed_si/protocol_results/summary.json').read_text(encoding='utf-8'))
manifest=[]
for case in summary['cases']:
    result=json.loads((ROOT/f'examples/high_speed_si/protocol_results/{case["id"]}.json').read_text(encoding='utf-8'))
    board=SpiDeR(design_id='si-reference-'+case['id'],name=case['label']+' - illustrative channel',source_format='spike-normalized',
      layers=[{'name':'F.Cu','type':'copper'}],nets=[{'id':'1','name':'SIG_P'},{'id':'2','name':'SIG_N'}],
      tracks=[{'start':[0,y],'end':[80,y],'width':.25,'layer':'F.Cu','net':name} for y,name in [(0,'SIG_P'),(.75,'SIG_N')]],
      metadata={'board_bounds_mm':{'min_x':-5,'max_x':85,'min_y':-8,'max_y':8},'si_model_scope':'Illustrative artwork only. Supplied uniform differential-mode RLGC; not extracted from these traces.'})
    canonical=SpiDeRV2.from_v1(board).to_dict()
    payload={'project':{'id':'si-study-'+case['id'],'name':case['label']+' reference study'},'design_ir':canonical,
      'workspace':{'tab':'HF / SI'},
      'analyses':{'si':{'latest_channel_result':result}},
      'results':{'si_reference':{'contract':result['contract'],'request_sha256':result['request_sha256'],'production_qualified':False}},
      'audit':[{'event':'original_reference_si_study','scope':'Supplied RLGC, abstract differential-mode equivalent. Artwork illustrative only.','request_sha256':result['request_sha256']}]}
    path=OUT/(case['id']+'.spike');write_spike_package(path,payload)
    response=handle_project_request('read_project_package',{'path':str(path)},request_id='verify-'+case['id'],application_version='0.3.9')
    if not response or not response.get('ok'):raise RuntimeError(str(response))
    assert response['result']['project']['analysis']['si']['latest_channel_result']==result
    assert response['result']['project']['design']['source_format']=='spike-normalized'
    # Verify portable native result retention independently of desktop state.
    opened=read_project(path); hydrated=hydrate_result_state(opened.payload,path,opened.manifest['manifest_payload_sha256'])
    saved=hydrated['analyses']['si']['latest_channel_result']
    assert saved==result
    manifest.append({'case':case['id'],'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'saved_result_verified':True})
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
