# SPDX-License-Identifier: Apache-2.0
"""Retain executed machine studies in real portable SPIKE v3 projects."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from python.spike_core.contracts import SpiDeR
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.project_package import write_spike_package,read_project
from python.spike_core.service_project import frontend_project_payload
HERE=Path(__file__).parent; OUT=ROOT/'output/promo-showcase-20261023/electrical'
records=[]
for name in ('planar_pm_fem','planar_solenoid_fem','electromagnet','electromagnet-air','motor'):
    request=json.loads((HERE/'magnetics'/f'{name}.json').read_text())
    result=json.loads((OUT/f'{name}-result.json').read_text())
    baseline=json.loads((HERE/'magnetics/motor.json').read_text())
    study={'request':baseline,'result':None,'fieldStudy':{'request':request,'result':result}} if name.startswith('planar_') else {'request':request,'result':result}
    design=SpiDeRV2.from_v1(SpiDeR(design_id='showcase-'+name,name='Original generated machine workspace',source_format='generated',source_path='')).to_dict()
    project={'id':'showcase-'+name,'name':name}
    legacy={'format':'spike-project-package/v2','contract':'spike/project/v2','project':project,'design':SpiDeRV2.from_dict(design).to_v1().to_dict(),'analysis':{},'emi':{'setup':{'machine_study':study}}}
    payload={'project':project,'design_ir':design,'extensions':{'legacy':legacy},'audit':[{'event':'original_showcase_study_packaged','request_sha256':result['request_sha256']}]}
    path=HERE/'magnetics'/f'{name}.spike'
    manifest=write_spike_package(path,payload)
    opened=read_project(path)
    saved=opened.payload['extensions']['legacy']['emi']['setup']['machine_study']
    assert frontend_project_payload(opened.payload)['emi']['setup']['machine_study']==saved
    assert (saved['fieldStudy'] if name.startswith('planar_') else saved)['result']['request_sha256']==result['request_sha256']
    records.append({'project':str(path.relative_to(ROOT)).replace('\\','/'),'manifest_payload_sha256':manifest['manifest_payload_sha256'],'package_readback':'passed','retained_request_sha256':result['request_sha256'],'ui_run':'not_executed'})
(OUT/'package-verification.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps(records,indent=2))
