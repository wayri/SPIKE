# SPDX-License-Identifier: Apache-2.0
"""Assemble original winding PCBs and retained STEP parts in a native project."""
from pathlib import Path
import argparse,hashlib,json,sys,tempfile,zipfile
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from python.spike_core.service_project import import_design
from python.spike_core.project_package import write_spike_package,read_project,_source_member_name
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.service_material_library import assign_material_to_project
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.assembly_frames import IDENTITY
from python.spike_core.material_library import validate_snapshot
OUT=ROOT/'output/promo-planar-magnetics-20261023/assembly'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frame(x=0,y=0,z=0):
    v=list(IDENTITY);v[3],v[7],v[11]=x,y,z;return v
def call(method,**params):
    r=handle_project_request(method,params,request_id='planar-showcase',application_version='source')
    if not r or not r.get('ok'):raise RuntimeError(r)
    return r['result']
def save(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--primary',required=True,type=Path);parser.add_argument('--secondary',required=True,type=Path)
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True);(OUT/'.tmp').mkdir(exist_ok=True);tempfile.tempdir=str(OUT/'.tmp')
    primary,secondary=args.primary.resolve(),args.secondary.resolve()
    core=ROOT/'output/promo-planar-magnetics-20261023/core/original-nominal-elp32-core-pair.step'
    pins=ROOT/'output/promo-planar-magnetics-20261023/core/original-pin34-terminals.step'
    design=import_design(str(primary),with_report=True)['design']
    design['source']['artifact_path']='package:'+_source_member_name(primary.name,sha(primary))
    project=OUT/'stacked-planar-transformer.spike'
    manifest=write_spike_package(project,{'project':{'name':'Stacked planar transformer - geometry and material evidence'},'design_ir':design},source_artifacts={primary.name:primary.read_bytes()},application_version='source')
    exchange=OUT/'core-and-pins.spikeassembly'
    assets={'secondary.kicad_pcb':secondary,'core.step':core,'pins.step':pins}
    occurrences=[{'id':'secondary','kind':'board','name':'Separate secondary PCB - four parallel layers','asset':'secondary.kicad_pcb','transform':frame(z=1)},
      {'id':'core','kind':'part','name':'TDK ELP32 N97 nominal core pair (simplified CAD)','part_type':'other','asset':'core.step','transform':frame()},
      {'id':'pins','kind':'part','name':'34 illustrative Berg terminals - rating unqualified','part_type':'other','asset':'pins.step','transform':frame()}]
    with zipfile.ZipFile(exchange,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('assembly.json',json.dumps({'contract':'spike/assembly-exchange/v1','units':'mm','name':'Planar transformer components','occurrences':occurrences}))
        for name,path in assets.items():z.write(path,name)
    call('import_into_assembly_project',project_path=str(project),source_paths=[str(exchange)],expected_manifest_payload_sha256=manifest['manifest_payload_sha256'])
    opened=read_project(project,include_members=True)
    payload=dict(opened.payload);raw=payload['assembly_ir']
    raw['boards'][0]['name']='Separate primary PCB - eight series turns'
    # The active board is authored at the module origin; preserve each PCB's native coordinates.
    raw['boards'][0]['frame']['transform']=frame()
    AssemblyIRV1.from_dict(raw)
    payload.setdefault('extensions',{})['spike.planar-transformer-showcase']={
      'operating_target':{'input_v':48,'output_v':1.8,'output_w':50,'output_a':50/1.8},
      'winding_turns':{'primary':8,'secondary':1},'core_part_number':'B66287G0000X197','core_quantity':2,
      'magnetic_electrical_thermal_coupling':'unsupported; no 3D core/winding field solve or inferred loss',
      'geometry_only':True,'isolation_rating':'not established','pin_current_rating':'not established'}
    write_spike_package(project,payload,preserved_members=opened.members,application_version='source')
    opened=read_project(project)
    part=next(p for p in opened.payload['assembly_ir']['parts'] if 'core pair' in p['name'])
    material=json.loads((ROOT/'output/promo-planar-magnetics-20261023/core/generic-ferrite-project-material.json').read_text())
    assigned=assign_material_to_project({'project_path':str(project),'expected_manifest_payload_sha256':opened.manifest['manifest_payload_sha256'],'target_kind':'part','target_id':part['id'],'material':material},application_version='source')
    visual=[]
    for original in list(read_project(project).payload['assembly_ir']['parts']):
        opened=read_project(project)
        response=handle_project_request('tessellate_mcad_part_in_project',{'project_path':str(project),'expected_manifest_payload_sha256':opened.manifest['manifest_payload_sha256'],'part_id':original['id']},request_id='planar-showcase',application_version='source')
        visual.append({'part':original['name'],'response':response})
    final=read_project(project);a=AssemblyIRV1.from_dict(final.payload['assembly_ir'])
    assert len(a.boards)==2 and len(a.parts)==2
    retained=next(p for p in final.payload['assembly_ir']['parts'] if p['id']==part['id'])['extensions']['spike.material']
    validate_snapshot(retained);assert retained['record']==material
    save(OUT/'visual-tessellation.json',visual)
    save(OUT/'verification.json',{'status':'passed','native_readback':True,'boards':2,'step_parts':2,
      'material_assignment':'validated exact snapshot retained','material_digest':retained['digest'],
      'source_primary_sha256':sha(primary),'source_secondary_sha256':sha(secondary),
      'visual_tessellations_succeeded':sum(bool(v['response'] and v['response'].get('ok')) for v in visual),
      'project_sha256':sha(project),'electromagnetic_field_executed':False,'production_qualified':False})
    print(project)
if __name__=='__main__':main()
