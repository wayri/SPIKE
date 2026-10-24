# SPDX-License-Identifier: Apache-2.0
"""Collect the actual virtual chamber example without inventing RI results."""
from pathlib import Path
import hashlib,json,shutil,zipfile,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from examples.promo_showcase.colocate_kicad_sources import colocate_tree
OUT=ROOT/'output/promo-em-chamber-20261023';PACK=OUT/'READY_TO_OPEN'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)
def main():
    PACK.mkdir(parents=True,exist_ok=True)
    for area in ('screening','radiation'):
        assert json.loads((OUT/area/'verification.json').read_text())['status']=='passed'
        for p in (OUT/area).rglob('*'):
            relative=p.relative_to(OUT/area)
            if p.is_file() and not any(x.startswith('.') or x=='__pycache__' for x in relative.parts):
                copy(p,PACK/('radiation' if area=='radiation' else 'EVIDENCE/screening')/relative)
    for p in (HERE/'radiation').glob('*'):
        if p.is_file():copy(p,PACK/'radiation'/p.name)
    for name in ('START_HERE.md','01_emi_screen_gui.py','ri-scenario-not-executable.json'):
        copy(HERE/name,PACK/name)
    copy(OUT/'screening/virtual-em-chamber.spike',PACK/'virtual-em-chamber.spike')
    copy(ROOT/'examples/emerge/antenna_example.kicad_pcb',PACK/'antenna_example.kicad_pcb')
    for name in ('LICENSE','NOTICE','THIRD_PARTY_NOTICES.md'):
        copy(ROOT/name,PACK/'LICENSES'/name)
    for name in ('emi-chamber-workflow.md','VIRTUAL_EMI_EMERGE_TUTORIAL.md','EMI_WORKFLOW.md'):
        copy(ROOT/'docs'/name,PACK/'EVIDENCE'/name)
    colocate_tree(PACK)
    files=[{'path':p.relative_to(PACK).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
           for p in sorted(PACK.rglob('*')) if p.is_file() and p.name!='SHA256.json']
    (PACK/'SHA256.json').write_text(json.dumps(files,indent=2)+'\n')
    archive=OUT/'SPIKE-virtual-EM-chamber-example-20261023.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PACK.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(PACK).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for item in files:assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
    print(json.dumps({'archive':str(archive),'files':len(files),'bytes':archive.stat().st_size,
                      'integrity':'passed','ri_status':'blocked','chamber_em_mesh':False}))
if __name__=='__main__':main()
