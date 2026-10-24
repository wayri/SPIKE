# SPDX-License-Identifier: Apache-2.0
"""Prepare source-bound native EBrake thermal examples without changing solvers."""
from pathlib import Path
import copy, hashlib, json, sys, tempfile
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.service_project_handlers import handle_project_request

OUT=ROOT/'output/promo-showcase-20261023/boards'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def call(method,**params):
    r=handle_project_request(method,params,request_id='promo-boards',application_version='promo-source')
    if not r or not r.get('ok'):raise RuntimeError(r)
    return r['result']

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'.tmp').mkdir(exist_ok=True);tempfile.tempdir=str(OUT/'.tmp')
    source=ROOT/'app/public/demo/ebrake1.kicad_pcb'
    wrapper=json.loads((ROOT/'examples/thermal/ebrake1_layered_transient.json').read_text())
    assert sha(source)==wrapper['source']['board_sha256']
    design=import_kicad_design(str(source))
    base=wrapper['request'];base['transient']['output_stride']=2
    sink=json.loads((ROOT/'examples/thermal/ebrake1_layered_virtual_heatsink.json').read_text())['request']['virtual_heatsinks']
    variants={'01-ebrake-transient':copy.deepcopy(base),'02-ebrake-transient-virtual-sink':{**copy.deepcopy(base),'virtual_heatsinks':sink}}
    rows=[]
    for name,request in variants.items():
        folder=OUT/name;folder.mkdir(exist_ok=True)
        prior_request=folder/'request.json';prior_result=folder/'result.json'
        previous=json.loads(prior_result.read_text()) if prior_result.exists() and prior_request.exists() and json.loads(prior_request.read_text())==request else {}
        result=previous if previous.get('status')=='completed' else run_board_thermal(design,request)
        save(folder/'request.json',request);save(folder/'result.json',result)
        if result.get('status') not in ('completed','approximate','ok'):
            raise RuntimeError(f'{name}: {result.get("status")} {result.get("issues")}')
        frames=result.get('transient',[])
        assert isinstance(frames,list) and len(frames)>1
        # Retain exact solver arrays; no rendered or invented result frame is added.
        snapshot={'format':'spike-project-package/v2','project':{'name':name+'.spike'},
          'design':{'source_file':source.name,'source_format':'kicad_pcb','source_board':source.read_text(encoding='utf-8')},
          'analysis':{'mode':'DC IR Drop','pi_setup':{},'view_mode':'3D','show_models':False},
          'thermal':{'scenario':{'mode':'board','board_thermal_request':request,'board_thermal_result':result}},
          'studies':[]}
        path=folder/(name+'.spike')
        call('write_project_package',path=str(path),snapshot=snapshot,generate_geometry_tables=False)
        opened=call('read_project_package',path=str(path))
        restored=opened['project']['thermal']['scenario']
        assert restored['board_thermal_request']==request
        assert restored['board_thermal_result']==result
        assert opened['project']['design']['source_board']==source.read_text(encoding='utf-8')
        rows.append({'id':name,'project':str(path.relative_to(OUT)),'status':result['status'],'summary':result.get('summary'),'result_sha256':sha(folder/'result.json'),'native_roundtrip':'passed','saved_frames':len(frames)})
        print(name,'saved and reopened',flush=True)
    a,b=[rows[i]['summary'] for i in range(2)]
    assert b['maximum_board_temperature_c']<a['maximum_board_temperature_c'],(a,b)
    source_copy=OUT/source.name;source_copy.write_bytes(source.read_bytes())
    save(OUT/'manifest.json',{'schema':'spike/promo-project-examples/v1','license':'Apache-2.0','source_board_sha256':sha(source),'source_provenance':'docs/DEMO_BOARD_PROVENANCE.md','assumptions':wrapper['assumptions'],'projects':rows,'no_new_solver_code':True,'production_qualified':False,'generator_sha256':sha(Path(__file__))})

if __name__=='__main__':main()
