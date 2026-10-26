# SPDX-License-Identifier: Apache-2.0
"""Prepare exact-source motor/propeller viewport assets without computer use.

GLB/glTF are display representations only, not magnetic or CFD geometry. Source
STEP/STL bytes and their independent licenses remain the engineering inputs.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from python.spike_core.mcad_tessellation import tessellate_step_to_glb, StepTessellationPolicy
from python.spike_core.mcad_importer import validate_visual_mcad_artifact


def propeller_gltf(source):
    data=source.read_bytes()
    count=int.from_bytes(data[80:84],'little')
    if not 1<=count<=200000 or len(data)!=84+50*count:
        raise ValueError('Bounded binary source STL required')
    records=np.frombuffer(data,offset=84,count=count,dtype=np.dtype([
        ('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')]))
    xyz=(records['vertices'].reshape(-1,3).astype(float)*.001).astype('<f4')
    if not np.isfinite(xyz).all():raise ValueError('Nonfinite STL position')
    # Unindexed triangles preserve every original facet and its winding.
    raw=xyz.tobytes()
    doc={'asset':{'version':'2.0','generator':'SPIKE exact-facet STL display conversion'},
        'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0,'name':'ENOLA source facets; display metres'}],
        'meshes':[{'primitives':[{'attributes':{'POSITION':0},'mode':4}]}],
        'buffers':[{'uri':'data:application/octet-stream;base64,'+base64.b64encode(raw).decode(),'byteLength':len(raw)}],
        'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(raw),'target':34962}],
        'accessors':[{'bufferView':0,'componentType':5126,'count':len(xyz),'type':'VEC3',
            'min':xyz.min(axis=0).astype(float).tolist(),'max':xyz.max(axis=0).astype(float).tolist()}]}
    payload=json.dumps(doc,separators=(',',':'),allow_nan=False).encode()
    validate_visual_mcad_artifact('gltf',payload)
    return payload,{'triangles':count,'source_units':'mm','display_units':'m',
        'preserved':'All source facets and vertex ordering; float32 display-unit conversion only',
        'bbox_m':[xyz.min(axis=0).astype(float).tolist(),xyz.max(axis=0).astype(float).tolist()]}


def main():
    src=ROOT/'examples/promo_showcase/propulsion_pod/real_hardware'
    out=ROOT/'output/promo-propulsion-pod-20261023/real_geometry/assets';out.mkdir(parents=True,exist_ok=True)
    step=src/'OpenMotor125_25/CIAG_2_28 125_25.step'
    stl=src/'ENOLA_Casalino30cm/CASALINO_D30cm_pitch+5deg.stl'
    freecad=Path('C:/Users/yawar/AppData/Local/Programs/FreeCAD 1.1/bin/freecadcmd.exe')
    temp=ROOT/'output/.tmp';temp.mkdir(exist_ok=True);old=tempfile.tempdir
    try:
        tempfile.tempdir=str(temp)
        motor=tessellate_step_to_glb(step.read_bytes(),source_name=step.name,freecad_executable=freecad,
            policy=StepTessellationPolicy(linear_deflection_mm=.5,max_vertices=5_000_000,
                max_triangles=5_000_000,max_output_bytes=128*1024**2,memory_limit_mb=4096))
    finally:tempfile.tempdir=old
    (out/'OpenMotor125_25.glb').write_bytes(motor.artifact_bytes)
    prop,receipt=propeller_gltf(stl);(out/'ENOLA_Casalino_plus5.gltf').write_bytes(prop)
    for source in (step,stl):shutil.copy2(source,out/source.name)
    shutil.copy2(src/'OpenMotor125_25/LICENSE.txt',out/'OpenMotor_CERN_OHL_W_2_LICENSE.txt')
    shutil.copy2(src/'ENOLA_Casalino30cm/LICENSE_CC_BY_SA_4.0.txt',out/'ENOLA_CC_BY_SA_4_LICENSE.txt')
    manifest={'contract':'spike/pod-real-source-viewport-assets/v1','solver_ready':False,
        'motor_tessellation':motor.to_dict(),'propeller_conversion':receipt,
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='asset-manifest.json'},
        'source_attribution':'See adjacent licenses and real_hardware/source_inventory.json for pinned source URLs, authors and revisions.',
        'scope':'Source model inspection assets only; no adapter, mounting or completed pod assembly is inferred.'}
    shutil.copy2(src/'source_inventory.json',out/'source_inventory.json')
    # Include the copied attribution in the retained manifest as well.
    manifest['files']['source_inventory.json']=hashlib.sha256((out/'source_inventory.json').read_bytes()).hexdigest()
    (out/'asset-manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'output':str(out),'motor_triangles':motor.triangle_count,'propeller_triangles':receipt['triangles'],'solver_ready':False}))


if __name__=='__main__':main()
