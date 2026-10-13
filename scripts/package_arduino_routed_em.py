# SPDX-License-Identifier: Apache-2.0
"""Package the complete retained Arduino EM study and its exact source boards."""
import argparse
import hashlib
import json
import struct
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.project_package import write_spike_package,read_spike_package,_source_member_name
from python.spike_core.assembly_em_study import admit_assembly_em_study


def pin_glb(body):
    vertices=body['mesh']['vertices'];indices=[i for f in body['boundary_faces'] for i in f['vertices']]
    positions=[x for v in vertices for x in v]
    binary=struct.pack('<'+str(len(positions))+'f',*positions)+struct.pack('<'+str(len(indices))+'I',*indices)
    document={'asset':{'version':'2.0','generator':'SPIKE original specified connector mesh'},'scene':0,
      'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0}],
      'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1,'mode':4}]}],
      'buffers':[{'byteLength':len(binary)}],
      'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(positions)*4,'target':34962},
                     {'buffer':0,'byteOffset':len(positions)*4,'byteLength':len(indices)*4,'target':34963}],
      'accessors':[{'bufferView':0,'componentType':5126,'count':len(vertices),'type':'VEC3',
          'min':[min(v[a] for v in vertices) for a in range(3)],'max':[max(v[a] for v in vertices) for a in range(3)]},
          {'bufferView':1,'componentType':5125,'count':len(indices),'type':'SCALAR'}]}
    data=json.dumps(document,separators=(',',':')).encode();data+=b' '*((-len(data))%4)
    return struct.pack('<4sII',b'glTF',2,28+len(data)+len(binary))+struct.pack('<II',len(data),0x4e4f534a)+data+struct.pack('<II',len(binary),0x004e4942)+binary


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study-dir',type=Path,required=True)
    ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();tempfile.tempdir=str(ROOT/'.local')
    study=json.loads((args.study_dir/'study.json').read_text(encoding='utf-8'))
    admit_assembly_em_study(study)
    assembly=study['request']['geometry']['assembly']
    base=read_spike_package(ROOT/'output/enclosed-assembly-20261010/thermal/fan-off.spike',include_members=True)
    sources={};designs=[]
    for name,oid,filename in [('uno','uno-r4-minima','uno.kicad_pcb'),('shield','relay-shield','shield-source.kicad_pcb')]:
        source=args.prepared/name/filename;raw=source.read_bytes();sources[filename]=raw
        canonical=SpiDeRV2.from_v1(import_kicad_design(str(source))).to_dict()
        owner=next(b for b in assembly['boards'] if b['id']==oid)
        canonical['design_id']=owner['design_id']
        canonical['source']['artifact_path']='package:'+_source_member_name(filename,hashlib.sha256(raw).hexdigest())
        canonical['metadata']['retained_em_source_revision']='Native refill/outline repair derivative; original source unchanged.'
        designs.append(canonical)
    models=[m for m in base.payload['models']['models'] if m['id']=='enclosure-solid']
    artifacts={Path(k).name:v for k,v in base.members.items() if k=='models/artifacts/original-hollow-enclosure.step'}
    for body in study['request']['geometry']['bodies']:
        if not body['occurrence_id'].startswith('study-header-'):continue
        filename=body['reference_id']+'.glb';data=pin_glb(body);artifacts[filename]=data
        models.append({'id':body['reference_id'],'model_type':'glb','uri':'package:models/artifacts/'+filename,
          'digest':hashlib.sha256(data).hexdigest(),'name':'Specified idealized contact conductor'})
    payload={'project':{'name':'Arduino routed copper enclosure EM','description':'Explicit source-backed geometry with declared material/connector assumptions'},
      'workspace':{'active_tab':'EM','view_mode':'3D'},'design_ir':designs[0],'assembly_ir':assembly,
      'assembly_designs':{'contract':'spike/assembly-designs/v1','active_design_id':designs[0]['design_id'],'designs':designs},
      'models':{'contract':'spike/model-index/v1','models':models},'analyses':{'retained_assembly_em':study},
      'results':{},'reports':{},'extensions':{},'audit':[]}
    report=(args.study_dir/'geometry-evidence.json').read_bytes()
    manifest=write_spike_package(args.output,payload,source_artifacts=sources,model_artifacts=artifacts,
                                report_artifacts={'geometry-evidence.json':report})
    reopened=read_spike_package(args.output)
    assert json.dumps(reopened.payload['assembly_ir'],sort_keys=True)==json.dumps(assembly,sort_keys=True)
    assert reopened.payload['analyses']['retained_assembly_em']['result']==study['result']
    print(json.dumps({'path':str(args.output.resolve()),'bytes':args.output.stat().st_size,
                      'manifest_payload_sha256':manifest['manifest_payload_sha256'],
                      'solver_executed':bool(study['result'] and study['result'].get('solver_executed'))}))


if __name__=='__main__':main()
