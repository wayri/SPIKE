# SPDX-License-Identifier: Apache-2.0
"""Create the portable original planar-magnetics demo collection."""
from pathlib import Path
import hashlib,json,shutil,zipfile,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from examples.promo_showcase.colocate_kicad_sources import colocate_tree
OUT=ROOT/'output/promo-planar-magnetics-20261023';PACK=OUT/'READY_TO_OPEN'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)
def allowed(p,relative):
    return p.is_file() and not any(x.startswith('.') or x=='__pycache__' for x in relative.parts) and p.suffix.lower() not in {'.pdf','.exe','.dll','.obj','.pyc','.kicad_prl','.lck'}
def main():
    PACK.mkdir(parents=True,exist_ok=True)
    for area in ('windings','converter'):
        for p in (HERE/area).rglob('*'):
            rel=p.relative_to(HERE/area)
            if allowed(p,rel):copy(p,PACK/'KiCad'/area/rel)
    for area in ('core','windings','converter','assembly','aircore'):
        assert (OUT/area/'verification.json').is_file(),area
        for p in (OUT/area).rglob('*'):
            rel=p.relative_to(OUT/area)
            # Exclude stock-header exports: full module uses only original pin geometry.
            if area=='windings' and p.name in {'primary.step','secondary.step','aircore_inductor.step'}:continue
            if allowed(p,rel):copy(p,PACK/'EVIDENCE'/area/rel)
    for name in ('original-planar-module-full.step','original-nominal-elp32-core-pair.step','original-pin34-terminals.step',
                 'n97-core-material.json','generic-ferrite-project-material.json','generic-ferrite-material-snapshot.json','source-manifest.json','README.md'):
        copy(OUT/'core'/name,PACK/'core'/name)
    for p in (OUT/'assembly').glob('*.spike'):copy(p,PACK/'SPIKE'/p.name)
    for p in (OUT/'core').glob('*.spike'):copy(p,PACK/'SPIKE'/p.name)
    copy(OUT/'aircore/pcb-aircore-inductor.spike',PACK/'SPIKE/pcb-aircore-inductor.spike')
    copy(HERE/'converter/converter.spksch',PACK/'Studio/converter.spksch')
    for p in (HERE/'converter').glob('*.cir'):copy(p,PACK/'Studio'/p.name)
    for p in HERE.glob('*.py'):copy(p,PACK/'Python'/p.name)
    for p in (HERE/'core').glob('*.py'):copy(p,PACK/'Python/core'/p.name)
    copy(HERE/'START_HERE.md',PACK/'START_HERE.md')
    copy(ROOT/'docs/validation/PLANAR_MAGNETICS_DEMO_20261023.md',PACK/'EVIDENCE/independent-numerical-review.md')
    for name in ('LICENSE','NOTICE','THIRD_PARTY_NOTICES.md'):copy(ROOT/name,PACK/'LICENSES'/name)
    proof={'target':{'input_v':48,'output_v':1.8,'output_w':50,'output_a':50/1.8},
      'core':'2 x TDK B66287G0000X197 ELP32/6/20 N97',
      'procurement_url':'https://www.digikey.com/en/products/detail/tdk/B66287G0000X197/3914613',
      'whole_coupled_em_electrical_thermal':'not implemented',
      'completed':['native winding and converter CAD checks','retained STEP and SPIKE assemblies','material evidence assignment',
                   'air-core native PEEC extraction','ideal fixed-duty native converter','separate supplied-heat core transients'],
      'failed_or_blocked':['eight-turn primary PEEC nonpassive matrix','native PEEC Python full-result overlay binding',
                           '3D nonlinear winding/core solve','core-loss feedback','physical device/driver solve','CPU load regulation and qualified high-current layout'],
      'redistribution':'Original assets Apache-2.0; referenced stock libraries retain their own terms; supplier PDFs and stock-header STEP exports excluded',
      'gui_recorded':False,'production_qualified':False}
    (PACK/'scope-and-provenance.json').write_text(json.dumps(proof,indent=2)+'\n')
    colocate_tree(PACK)
    files=[{'path':p.relative_to(PACK).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
           for p in sorted(PACK.rglob('*')) if p.is_file() and p.name!='SHA256.json']
    (PACK/'SHA256.json').write_text(json.dumps(files,indent=2)+'\n')
    archive=OUT/'SPIKE-planar-magnetics-48V-1V8-50W-examples-20261023.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PACK.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(PACK).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for item in files:assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
    print(json.dumps({'archive':str(archive),'files':len(files),'bytes':archive.stat().st_size,'integrity':'passed'}))
if __name__=='__main__':main()
