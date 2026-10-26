# SPDX-License-Identifier: Apache-2.0
"""Package supported IRIS studies and explicitly blocked full-flight scope."""
from pathlib import Path
import hashlib, json, shutil, zipfile, sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from examples.promo_showcase.colocate_kicad_sources import colocate_tree
HERE = Path(__file__).parent
OUT = ROOT / 'output/promo-drone-20261023'
PACK = OUT / 'READY_TO_OPEN'
REV = '999dd2eb725d550889c1ffe2c09f8de0390d081b'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(a,b):
    b.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(a,b)

def main():
    PACK.mkdir(parents=True,exist_ok=True)
    for area in ('thermal','analytics'):
        assert (OUT/area/'verification.json').exists(),area
        for base,target in ((HERE/area,PACK/area),(OUT/area,PACK/'EVIDENCE'/area)):
            for p in base.rglob('*'):
                relative=p.relative_to(base)
                if p.is_file() and not any(x.startswith('.') or x=='__pycache__' for x in relative.parts):
                    copy(p,target/relative)
                    if p.suffix=='.spike': copy(p,PACK/'thermal'/p.name)
    for name in ('ProPrj_IRIS.kicad_pcb','README.md','LICENSE','BOM.csv','BOM.md',
                 'BOM_Board1_PCB1.csv','Motor1_ESC_Schematic.svg','frame_bottom.step','pcb_cover.step'):
        copy(OUT/'source'/name,PACK/'IRIS_SOURCE_GPL3'/name)
    for p in (OUT/'capability-evidence').glob('*.json'):
        copy(p,PACK/'EVIDENCE/capability-evidence'/p.name)
    for name in ('SOLVER_STATUS.md','VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md'):
        copy(ROOT/'docs'/name,PACK/'EVIDENCE/capability-evidence'/name)
    for name in ('START_HERE.md','flight-scenario.json','flight_volume_mm.stl'):
        copy(HERE/name,PACK/name)
    copy(ROOT/'LICENSE',PACK/'LICENSES/SPIKE-Apache-2.0.txt')
    provenance={'source':'https://github.com/Eugene109/IRIS','revision':REV,
        'license':'GPL-3.0 (upstream README: Everything is GNU GPL-3.0)',
        'hardware_derivatives':'retain GPL-3.0; original SPIKE scripts separately Apache-2.0',
        'source_board_sha256':sha(OUT/'source/ProPrj_IRIS.kicad_pcb'),
        'original_CAD_unchanged':True,'external_component_models_included':False,
        'excluded':['IRIS_Assembly.step: third-party motor/propeller model rights not established',
                    'LCSC footprint external 3D models','firmware source and binaries'],
        'source_warning':'Upstream warns EasyEDA-to-KiCad conversion can affect clearance and zone rules.',
        'whole_drone_flight':'blocked; no trajectory, rotor CFD or closed-loop flight run',
        'gui_recorded':False,'production_qualified':False}
    (PACK/'source-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    colocate_tree(PACK)
    manifest=[{'path':p.relative_to(PACK).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
              for p in sorted(PACK.rglob('*')) if p.is_file() and p.name!='SHA256.json']
    (PACK/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=OUT/'SPIKE-PCB-drone-supported-studies-20261023.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PACK.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(PACK).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for item in manifest:assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
    print(json.dumps({'archive':str(archive),'files':len(manifest),'bytes':archive.stat().st_size,
                      'integrity':'passed','whole_flight_status':'blocked'}))

if __name__=='__main__':main()
