# SPDX-License-Identifier: Apache-2.0
"""Import the converter carrier and explicitly mate all 34 physical terminals."""
from pathlib import Path
import json,sys,tempfile,shutil
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from python.spike_core.project_package import read_project,write_spike_package
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.harness_authoring import discover_connectors,validate_harness_connections
from scripts.build_arduino_shield_acceptance import _pin_mapping,_pin_center,_frame,_transform_xy
OUT=ROOT/'output/promo-planar-magnetics-20261023/assembly'
def main():
    (OUT/'.tmp').mkdir(exist_ok=True);tempfile.tempdir=str(OUT/'.tmp')
    project=OUT/'converter-and-stacked-transformer.spike'
    shutil.copy2(OUT/'stacked-planar-transformer.spike',project)
    carrier=ROOT/'examples/promo_showcase/planar_magnetics/converter/carrier.kicad_pcb'
    opened=read_project(project)
    response=handle_project_request('import_into_assembly_project',{'project_path':str(project),'source_paths':[str(carrier)],'expected_manifest_payload_sha256':opened.manifest['manifest_payload_sha256']},request_id='planar-carrier',application_version='source')
    assert response and response['ok'],response
    opened=read_project(project,include_members=True);payload=dict(opened.payload);raw=payload['assembly_ir'];designs={d['design_id']:d for d in payload['assembly_designs']['designs']}
    cboard=raw['boards'][-1];cd=designs[cboard['design_id']]
    t1=next(c for c in cd['components'] if c['reference']=='T1')
    # Canonical component position is the pad centroid, not the footprint anchor.
    # Recover the authored module origin from its explicit P1 local coordinates.
    pin1=_pin_center(cd,'T1','1');cx,cy=pin1[0]+20,pin1[1]+1.27
    cboard['frame']['transform']=_frame(-cx,-cy,-6.6);cboard['name']='48 V to 1.8 V carrier - study geometry, unrated power layout'
    winding_boards=raw['boards'][:-1]
    a=AssemblyIRV1.from_dict(raw);inventory=discover_connectors(a,designs)
    mappings=[_pin_mapping(cboard['id'],'T1',tuple(str(i) for i in range(1,35)),inventory,cd)]
    used=set();links=[];evidence=[]
    for board in winding_boards:
        d=designs[board['design_id']]
        for component in d['components']:
            ref=component['reference'];pins=[str(p['number']) for p in d['pins'] if p['component_id']==component['id']]
            if not pins:continue
            mappings.append(_pin_mapping(board['id'],ref,tuple(pins),inventory,d));pinmap={}
            for pin in pins:
                point=_transform_xy(board['frame']['transform'],_pin_center(d,ref,pin))
                candidates=[]
                for carrier_pin in map(str,range(1,35)):
                    target=_transform_xy(cboard['frame']['transform'],_pin_center(cd,'T1',carrier_pin))
                    error=((point[0]-target[0])**2+(point[1]-target[1])**2)**.5
                    # Header rotations serialize on KiCad's nanometre grid.
                    if error<1e-5:candidates.append((carrier_pin,target,error))
                assert len(candidates)==1,(ref,pin,point,candidates)
                matched,target,error=candidates[0];assert matched not in used;used.add(matched);pinmap[pin]=matched
                evidence.append({'board':board['id'],'connector':ref,'pin':pin,'carrier_T1_pin':matched,'xy_error_mm':error,'winding_position_mm':point,'carrier_position_mm':target})
            links.append({'id':'mate-'+board['id']+'-'+ref,'kind':'connector-mate','name':'Explicit terminal-bank mating '+ref,
              'data':{'endpoint_a':board['id']+'::'+ref,'endpoint_b':cboard['id']+'::T1','pin_map':pinmap}})
    assert used==set(map(str,range(1,35))),used
    raw['connector_mappings']=mappings+links;validate_harness_connections(AssemblyIRV1.from_dict(raw))
    write_spike_package(project,payload,preserved_members=opened.members,application_version='source')
    final=read_project(project);validate_harness_connections(AssemblyIRV1.from_dict(final.payload['assembly_ir']))
    expected=AssemblyIRV1.from_dict(raw).to_dict()['connector_mappings']
    assert json.loads(json.dumps(final.payload['assembly_ir']['connector_mappings']))==json.loads(json.dumps(expected))
    (OUT/'carrier-assembly-verification.json').write_text(json.dumps({'status':'passed','boards':3,'parts':2,'explicit_mated_pins':len(used),'placement':evidence,'coupled_simulation_executed':False,'production_qualified':False},indent=2)+'\n')
    print(project)
if __name__=='__main__':main()
