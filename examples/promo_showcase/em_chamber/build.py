# SPDX-License-Identifier: Apache-2.0
"""Retain native virtual chamber setup and execute its registered EMI screen."""
from pathlib import Path
import hashlib,json,sys,tempfile
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.script_runtime import run_python_script
from python.spike_core.service_project_handlers import handle_project_request
HERE=Path(__file__).parent;OUT=ROOT/'output/promo-em-chamber-20261023/screening'

def save(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'.tmp').mkdir(exist_ok=True);tempfile.tempdir=str(OUT/'.tmp')
    source=ROOT/'examples/emerge/antenna_example.kicad_pcb'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest=='f8fd038633c5b49a3867c8f09dc4fb3341b9be5a4a3cd961a088dbde6a77a2f0'
    design=json.loads(json.dumps(import_kicad_design(str(source)).to_dict()))
    setup=json.loads((ROOT/'examples/emerge/virtual_emi_setup.json').read_text())
    code='''# SPDX-License-Identifier: Apache-2.0
import spike
import json
SETUP = '''+repr(setup)+'''
assert spike.design is not None, "Open the supplied antenna board first"
assert spike.design["design_id"] == '''+repr(design['design_id'])+''', "Selected design is not this pinned example"
preflight=spike.analysis.run("emi_preflight", {"design":spike.design,"setup":SETUP})
result=spike.analysis.run("emi_screen", {"design":spike.design,"setup":SETUP})
print("PREFLIGHT_JSON="+json.dumps(preflight))
print("SCREENING_JSON="+json.dumps(result))
spike.publish_table("Virtual EM review: model boundaries",["Item","Meaning"],[
 ["EMI risk screen", "Ranks supplied metrics; not a field calculation"],
 ["One selected candidate", "No comparative ranking; zero score is not low radiation"],
 ["Chamber", "Placement visualization; absorbers/antenna/room are not EM meshed"],
 ["Radiation", "Open saved EMerge result separately: relative pattern, unvalidated"],
 ["Radiated immunity", "Unsupported: no incident-field/loaded-board susceptibility run"]],
 provenance="Actual EMI worker execution; explicit scope, no compliance claim")
'''
    (HERE/'01_emi_screen_gui.py').write_text(code,encoding='utf-8')
    execution=run_python_script({'code':code,'design':design,'timeout_seconds':120})
    save(OUT/'python-workspace-execution.json',execution)
    assert execution['status']=='completed',execution
    lines=execution['stdout'].splitlines()
    preflight=json.loads(next(x.split('=',1)[1] for x in lines if x.startswith('PREFLIGHT_JSON=')))
    result=json.loads(next(x.split('=',1)[1] for x in lines if x.startswith('SCREENING_JSON=')))
    save(OUT/'preflight.json',preflight);save(OUT/'screening.json',result);save(OUT/'setup.json',setup)
    snapshot={'format':'spike-project-package/v2','project':{'name':'virtual-em-chamber.spike'},
      'design':{'source_file':source.name,'source_format':'kicad_pcb','source_board':source.read_text(encoding='utf-8')},
      'analysis':{'mode':'DC IR Drop','pi_setup':{},'view_mode':'3D','show_models':False,'em_chamber_open':True},
      'emi':{'setup':setup,'preflight':preflight,'screening':result,'field_result':None},'studies':[]}
    path=OUT/'virtual-em-chamber.spike'
    response=handle_project_request('write_project_package',{'path':str(path),'snapshot':snapshot,'generate_geometry_tables':False},request_id='chamber-example',application_version='source')
    assert response and response['ok'],response
    reopened=handle_project_request('read_project_package',{'path':str(path)},request_id='chamber-example',application_version='source')
    assert reopened['ok'],reopened
    assert reopened['result']['project']['emi']==snapshot['emi']
    assert reopened['result']['project']['design']['source_board']==snapshot['design']['source_board']
    save(OUT/'verification.json',{'status':'passed','native_emi_roundtrip':'exact setup/preflight/screen/source',
      'python_workspace_execution':execution['status'],'source_board_sha256':digest,
      'template_sha256':hashlib.sha256(code.encode()).hexdigest(),'radiated_immunity_executed':False,
      'chamber_em_mesh':False,'production_qualified':False})
    print('Native chamber setup + real GUI Python EMI screen passed')

if __name__=='__main__':main()
