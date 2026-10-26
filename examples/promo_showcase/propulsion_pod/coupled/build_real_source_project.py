# SPDX-License-Identifier: Apache-2.0
"""Build a native source-geometry project, explicitly pending coupled results.

This does not package a completed loop. Native CAD/ECAD identity is independent
of solver convergence and the scene exposes the unresolved mounting adapter.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from python.spike_core.service_project import import_design
from python.spike_core.project_package import write_spike_package, read_project, _source_member_name
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.assembly_frames import IDENTITY
from examples.promo_showcase.colocate_kicad_sources import colocate_tree


def main():
    out=ROOT/'output/promo-propulsion-pod-20261023/real_geometry'
    assets=out/'assets';manifest=json.loads((assets/'asset-manifest.json').read_text())
    for name,sha in manifest['files'].items():
        if hashlib.sha256((assets/name).read_bytes()).hexdigest()!=sha:raise ValueError('Viewport asset drift: '+name)
    board=ROOT/'output/promo-esc-20261023/source/bldc-hardware-f1c65014d0caab5d99d888fc3025377861ac6ae2/design/BLDC_4.kicad_pcb'
    sha=hashlib.sha256(board.read_bytes()).hexdigest()
    project=out/'real-source-pod-assembly-pending-simulation.spike'
    if project.exists():raise ValueError('Retained source project already exists; choose a new revision')
    scratch=ROOT/'output/.tmp';scratch.mkdir(exist_ok=True);previous=tempfile.tempdir
    try:
        tempfile.tempdir=str(scratch)
        design=import_design(str(board),with_report=True)['design']
        design['source']['artifact_path']='package:'+_source_member_name(board.name,sha)
        package=write_spike_package(project,{'project':{'name':'OpenMotor / ENOLA source assembly — coupled simulation pending'},
            'design_ir':design},source_artifacts={board.name:board.read_bytes()},application_version='source')
        prop=list(IDENTITY)
        # Proposed common shaft: source propeller +y becomes motor +z. Translation
        # is a declared assembly scenario, not a measured compatible adapter.
        prop[:12]=[1.,0.,0.,0.,0.,0.,-1.,0.,0.,1.,0.,60.]
        exchange=out/'real-source-pod.spikeassembly'
        items=[('motor','OpenMotor125_25 original source visual','OpenMotor125_25.glb',list(IDENTITY)),
            ('propeller','ENOLA Casalino +5deg original facets; proposed mounting datum','ENOLA_Casalino_plus5.gltf',prop)]
        with zipfile.ZipFile(exchange,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('assembly.json',json.dumps({'contract':'spike/assembly-exchange/v1','units':'mm',
                'name':'Real source motor and propeller — adapter unresolved',
                'occurrences':[{'id':key,'kind':'part','name':name,'part_type':'other','asset':file,'transform':transform,
                    'metadata':{'scope':'Source inspection / proposed coaxial placement; not a validated assembly'}}
                    for key,name,file,transform in items]}))
            for _,_,file,_ in items:archive.write(assets/file,file)
        response=handle_project_request('import_into_assembly_project',{'project_path':str(project),
            'source_paths':[str(exchange)],'expected_manifest_payload_sha256':package['manifest_payload_sha256']},
            request_id='real-source-pod',application_version='source')
        if not response or not response.get('ok'):raise ValueError(response)
        reopened=read_project(project,include_members=True);payload=reopened.payload
        position=list(IDENTITY);position[3]=100.;position[7]=100.;position[11]=-20.
        payload['assembly_ir']['boards'][0]['frame']['transform']=position
        payload['assembly_ir']['boards'][0]['name']='VESC exact KiCad source — averaged bridge binding remains separate'
        payload.setdefault('extensions',{})['spike.propulsion-real-source-preparation']={
            'contract':'spike/propulsion-real-source-preparation/v1','state':'geometry_prepared_simulation_pending',
            'complete_loop':False,'gui_verified':False,'source_board_sha256':sha,
            'asset_manifest':manifest,'mounting_adapter_qualified':False,
            'shaft_constraint':'Proposed common fixed axis +z; only shaft angular motion is solved in the headless loop.',
            'limitations':['Motor/propeller composition is not a measured hardware pair.',
                'Propeller mounting translation60mm is a declared scene datum; shaft adapter remains unresolved.',
                'VESC source board is exact ECAD context; no firmware/switching qualification is inferred.',
                'Motor/CFD load convergence and real coupled result remain pending.']}
        write_spike_package(project,payload,preserved_members=reopened.members,
            report_artifacts={'real-source-assets.json':json.dumps(manifest,indent=2).encode()},application_version='source')
        final=read_project(project,include_members=True)
        if final.payload['extensions']['spike.propulsion-real-source-preparation']['complete_loop'] is not False:
            raise ValueError('Preparation package must not imply completed simulation')
        colocate_tree(out)
        print(json.dumps({'project':str(project),'assembly_parts':len(final.payload['assembly_ir']['parts']),
            'complete_loop':False,'gui_verified':False,'native_reopen_passed':True}))
    finally:tempfile.tempdir=previous


if __name__=='__main__':main()
